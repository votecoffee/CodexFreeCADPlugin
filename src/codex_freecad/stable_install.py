"""Prepare and atomically select retained standalone runtimes; no host config writes."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from . import __package_version__
from .offline_setup import inventory
from .process_lifetime import ProcessSlots
from .stable_launcher import PINS, ordinary, selection, sha256, snapshot_manifest


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def atomic_bytes(path, raw):
    fd, pending = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


def default_root():
    return Path(os.environ["LOCALAPPDATA"]) / "FreeCADMCPServer"


def prepare(
    root,
    runtime,
    workspace,
    *,
    state=None,
    registry=None,
    mode="headless",
    native_target=None,
    python=None,
    profile="native",
    source_commit=None,
    app_wheel_sha256=None,
):
    """Copy reviewed wheel sources; callers review/select the returned exact hash."""
    if (
        profile not in {"native", "offline"}
        or (profile == "native" and native_target is None)
        or (profile == "offline" and native_target is not None)
    ):
        raise ValueError("Explicitly select native with a bound target, or offline without one")
    root = Path(os.path.abspath(root))
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    ordinary(ancestor)
    root.mkdir(parents=True, exist_ok=True)
    ordinary(root)
    for name in ("cwd", "launcher/snapshots", "launcher/backups", "runtimes"):
        (root / name).mkdir(parents=True, exist_ok=True)
        ordinary(root / name)
    launcher = root / "Start-Mcp.py"
    launcher_bytes = Path(__file__).with_name("stable_launcher.py").read_bytes()
    if launcher.exists() and launcher.read_bytes() != launcher_bytes:
        raise ValueError("Existing stable entry differs; retain it and review a launcher upgrade")
    if not launcher.exists():
        with launcher.open("xb") as stream:
            stream.write(launcher_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    runtime = ordinary(runtime)
    files = inventory(runtime)
    retained = root / "runtimes" / (__package_version__ + "-" + uuid.uuid4().hex)
    retained.mkdir()
    payload = retained / "runtime"
    shutil.copytree(runtime, payload)
    if inventory(payload) != files:
        raise ValueError("Retained runtime copy differs; failed preparation remains unselected")
    state = Path(state or root / "state").absolute()
    registry = Path(registry or root / "registry").absolute()
    output = retained / "connection"
    if native_target is None:
        from .offline_setup import generate

        candidate = generate(
            workspace, output, payload, python=python, state=state, registry=registry
        )
        entry = output / "offline-launch.py"
    else:
        from .native_setup import generate

        candidate = generate(
            workspace,
            output,
            payload,
            native_target=native_target,
            mode=mode,
            python=python,
            state=state,
            registry=registry,
        )
        entry = output / "native-launch.py"
    config = json.loads((output / "plugin/.mcp.json").read_bytes())["mcpServers"]["freecad"]
    route = {
        "command": candidate["python"],
        "args": ["-I", "-S", "-B", str(launcher)],
        "cwd": str(root / "cwd"),
        "env": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
    }
    plugin_config = output / "plugin/.mcp.json"
    atomic_bytes(plugin_config, encoded({"mcpServers": {"freecad": route}}))
    immutable = {
        p.relative_to(root).as_posix(): sha256(p) for p in output.rglob("*") if p.is_file()
    }
    manifest = {
        "schema_version": 1,
        "application_id": "freecad-mcp-server",
        "package_version": __package_version__,
        "source_commit": source_commit,
        "app_wheel_sha256": app_wheel_sha256,
        "profile": candidate["profile"],
        "mode": candidate.get("mode"),
        "pins": PINS,
        "python": candidate["python"],
        "python_sha256": candidate["python_sha256"],
        "python_console_sha256": sha256(Path(candidate["python"]).with_name("python.exe")),
        "runtime": payload.relative_to(root).as_posix(),
        "entry": entry.relative_to(root).as_posix(),
        "args": config["args"][4:],
        "files": immutable,
        "route": route,
        "state": str(state),
        "registry": str(registry),
        "workspace": str(Path(workspace).absolute()),
        "native_target": candidate.get("native_target"),
        "native_target_sha256": candidate.get("native_target_sha256"),
        "runtime_file_count": len(files),
        "runtime_closure_sha256": candidate["closure_sha256"],
        "stable_entry_sha256": sha256(launcher),
    }
    raw = encoded(manifest)
    revision = hashlib.sha256(raw).hexdigest()
    snapshot = root / "launcher/snapshots" / revision
    snapshot.mkdir()
    (snapshot / "manifest.json").write_bytes(raw)
    return {
        "snapshot": revision,
        "root": str(root),
        "manifest": manifest,
        "selected": False,
        "plugin": str(output / "plugin"),
        "route": route,
    }


def select(root, snapshot, *, expected_selection):
    root = ordinary(root)
    target = root / "launcher/current.json"
    # Validate the prospective record through exactly the same reader without
    # publishing a real pointer. All its immutable files must already exist.
    candidate = snapshot_manifest(root, snapshot)
    runtime = root / candidate["runtime"]
    closure_path = (root / candidate["entry"]).parent / "closure.json"
    closure = json.loads(closure_path.read_bytes())
    if Path(closure["runtime"]) != runtime or inventory(runtime) != closure["files"]:
        raise ValueError("Prospective immutable runtime changed; selection was preserved")
    lock = root / "launcher/publication-lock"
    lock.mkdir(exist_ok=True)
    ordinary(lock)
    ordinary(root / "launcher/backups")
    with ProcessSlots(lock, limit=1):
        old = ordinary(target).read_bytes() if target.exists() else None
        observed = hashlib.sha256(old).hexdigest() if old is not None else "absent"
        if observed != expected_selection:
            raise ValueError("Selection changed concurrently; previous selection was preserved")
        if old is not None:
            selection(root)  # Never replace a malformed/tampered current selection.
            backup = root / "launcher/backups" / (observed + ".json")
            if backup.exists():
                ordinary(backup)
            if backup.exists() and backup.read_bytes() != old:
                raise ValueError("Selection backup changed")
            if not backup.exists():
                with backup.open("xb") as stream:
                    stream.write(old)
                    stream.flush()
                    os.fsync(stream.fileno())
        new = encoded({"schema_version": 1, "snapshot": snapshot})
        # Cooperating writers share the OS-owned lock; detect intervening edits
        # before replacing bytes. Never restore a stale global or local pointer.
        if (target.read_bytes() if target.exists() else None) != old:
            raise ValueError("Selection changed during publication")
        snapshot_manifest(root, snapshot)
        atomic_bytes(target, new)
        selected = selection(root)
        if selected["snapshot"] != snapshot:
            raise ValueError("Selection readback differs; retain publication evidence")
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "select", "status"])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--native-target", type=Path)
    parser.add_argument("--profile", choices=["native", "offline"], default="native")
    parser.add_argument("--mode", choices=["headless", "live"], default="headless")
    parser.add_argument("--snapshot")
    parser.add_argument("--expected-selection")
    args = parser.parse_args()
    root = args.root or default_root()
    if args.action == "prepare":
        if args.runtime is None or args.workspace is None:
            parser.error("prepare requires --runtime and --workspace")
        result = prepare(
            root,
            args.runtime,
            args.workspace,
            state=args.state,
            registry=args.registry,
            mode=args.mode,
            native_target=args.native_target,
            profile=args.profile,
        )
    elif args.action == "select":
        if not args.snapshot or args.expected_selection is None:
            parser.error("select requires --snapshot and --expected-selection SHA256|absent")
        result = select(root, args.snapshot, expected_selection=args.expected_selection)
    else:
        result = {
            **selection(root),
            "health": "not-assessed",
            "note": "Selection is not a running-backend observation",
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
