"""Explicit Windows installation from a clean commit and reviewed wheel closure.

Used by Install.cmd only. Serving a connection never builds, downloads or installs.
"""

import argparse
import base64
import csv
import hashlib
import io
import json
import shutil
import stat
import subprocess
import sys
import tarfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from . import __package_version__
from .client import find_freecad_cmd
from .stable_install import atomic_bytes, default_root, encoded, prepare, select
from .stable_launcher import ordinary, selection, sha256


def wheel_files(path, expected_sha256):
    if sha256(ordinary(path)) != expected_sha256:
        raise ValueError("Wheel differs from its reviewed SHA-256: " + path.name)
    with zipfile.ZipFile(path) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        names = [i.filename for i in infos]
        if (
            len(names) != len(set(names))
            or len(names) > 20000
            or sum(i.file_size for i in infos) > 256 * 1024 * 1024
        ):
            raise ValueError("Wheel duplicates or budget exceeded")
        for info in infos:
            relative = PurePosixPath(info.filename)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or ":" in info.filename
                or "\\" in info.filename
                or stat.S_ISLNK(info.external_attr >> 16)
            ):
                raise ValueError("Unsafe wheel member")
        records = [n for n in names if n.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise ValueError("Wheel needs exactly one RECORD")
        rows = list(csv.reader(io.StringIO(archive.read(records[0]).decode("utf-8"))))
        indexed = {r[0]: r for r in rows if len(r) == 3}
        if len(indexed) != len(rows) or set(indexed) != set(names):
            raise ValueError("Wheel file set differs from RECORD")
        result = {}
        for name, row in indexed.items():
            data = archive.read(name)  # CRC checked by ZipFile.
            if name == records[0]:
                if row[1:] != ["", ""]:
                    raise ValueError("Invalid self RECORD entry")
            elif row[1] != "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(data).digest()
            ).rstrip(b"=").decode() or row[2] != str(len(data)):
                raise ValueError("Wheel RECORD bytes differ")
            result[name] = data
        return result


def extract_wheel(path, expected, output):
    files = wheel_files(path, expected)
    for name, data in files.items():
        target = output.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            raise ValueError("Conflicting runtime wheel member: " + name)
        if not target.exists():
            target.write_bytes(data)
    return {"wheel": path.name, "sha256": expected, "record_files_verified": len(files)}


def git(project, *args):
    return subprocess.check_output(["git", "-C", str(project), *args])


def build_wheel(project, destination):
    if git(project, "status", "--porcelain", "--untracked-files=normal").strip():
        raise ValueError("Build a clean committed source tree; retain uncommitted work")
    commit = git(project, "rev-parse", "HEAD").decode().strip()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(destination),
            str(project),
        ],
        check=True,
        stdout=sys.stderr,
    )
    paths = list(destination.glob("codex_freecad-*.whl"))
    if len(paths) != 1:
        raise ValueError("Expected one built application wheel")
    wheel = paths[0]
    content = wheel_files(wheel, sha256(wheel))
    expected = {}
    with tarfile.open(
        fileobj=io.BytesIO(git(project, "archive", "HEAD", "src/codex_freecad"))
    ) as archive:
        for member in archive.getmembers():
            if member.isfile():
                expected[member.name.removeprefix("src/")] = archive.extractfile(member).read()
    packaged = {n: data for n, data in content.items() if n.startswith("codex_freecad/")}
    if any(expected.get(n) != data.replace(b"\r\n", b"\n") for n, data in packaged.items()) or set(
        packaged
    ) != {n for n in expected if n.endswith((".py", ".md", ".json"))}:
        raise ValueError("Built application package differs from canonical committed text")
    if (
        git(project, "rev-parse", "HEAD").decode().strip() != commit
        or git(project, "status", "--porcelain").strip()
    ):
        raise ValueError("Source changed during package preparation")
    newline_variations = [name for name, data in packaged.items() if expected[name] != data]
    return wheel, commit, newline_variations


def legacy_binding(project):
    path = project / ".local/standalone-native/active.json"
    if not path.exists():
        return None
    active = json.loads(path.read_bytes())
    connection = Path(active["target"]) / "connection"
    candidate = json.loads((connection / "candidate.json").read_bytes())
    route = json.loads((connection / "plugin/.mcp.json").read_bytes())["mcpServers"]["freecad"]
    args = route["args"]
    return {
        "state": active["shared_state"],
        "registry": active["shared_registry"],
        "workspace": args[args.index("--workspace") + 1],
        "mode": candidate["mode"],
        "native_target": candidate["native_target"],
        "native_target_sha256": candidate["native_target_sha256"],
        "source_selection_path": str(path),
        "source_selection_sha256": sha256(path),
        "wheelhouse": Path(active["target"]) / "packages",
    }


def install(
    project,
    root,
    *,
    wheelhouse=None,
    framework_wheel=None,
    workspace=None,
    mode=None,
    native_target=None,
):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13) or sys.maxsize <= 2**32:
        raise ValueError("This reviewed runtime closure requires Windows x64 Python 3.13")
    project, root = Path(project).absolute(), Path(root).absolute()
    if root == Path(root.anchor) or root.is_relative_to(project) or project.is_relative_to(root):
        raise ValueError("Use a dedicated persistent installation outside the development checkout")
    components = [p.lower() for p in root.parts]
    if any(components[i : i + 2] == ["plugins", "cache"] for i in range(len(components) - 1)):
        raise ValueError("A disposable plugin cache cannot own the stable installation")
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    ordinary(ancestor)
    root.mkdir(parents=True, exist_ok=True)
    ordinary(root)
    before = selection(root) if (root / "launcher/current.json").exists() else None
    expected_selection = before["selection_sha256"] if before else "absent"
    legacy = legacy_binding(project) if before is None else None
    previous = before["manifest"] if before else legacy or {}
    if before and previous["profile"] != "direct-standalone-native":
        raise ValueError(
            "Preserve the selected offline profile; use its explicit preparation workflow"
        )
    workspace = Path(workspace or previous.get("workspace") or root / "models").absolute()
    workspace.mkdir(parents=True, exist_ok=True)
    mode = mode or previous.get("mode") or "headless"
    target = native_target or (
        previous.get("native_target") if previous.get("mode") == mode else None
    )
    if mode == "live" and not target:
        raise ValueError(
            "Live selection needs an explicit existing bridge descriptor; no GUI is started"
        )
    target = target or find_freecad_cmd()
    target = Path(target).absolute()
    if (
        not target.is_file()
        or (mode == "headless" and target.name.lower() != "freecadcmd.exe")
        or (mode == "live" and target.suffix.lower() != ".json")
    ):
        raise ValueError("Bind an existing explicit FreeCADCmd.exe or live bridge JSON")
    if (
        native_target is None
        and previous.get("native_target_sha256")
        and sha256(target) != previous["native_target_sha256"]
    ):
        raise ValueError(
            "Previous native binding changed; explicitly review the new target before installing"
        )
    state, registry = previous.get("state"), previous.get("registry")
    packages = root / "packages"
    packages.mkdir(exist_ok=True)
    ordinary(packages)
    (root / ".staging").mkdir(exist_ok=True)
    ordinary(root / ".staging")
    stage = root / ".staging" / uuid.uuid4().hex
    stage.mkdir()
    dependencies = json.loads(Path(__file__).with_name("runtime-windows-py313.json").read_bytes())
    sources = [Path(wheelhouse)] if wheelhouse else []
    if legacy:
        sources.append(legacy["wheelhouse"])
    sources.append(packages)
    framework_wheel = Path(framework_wheel) if framework_wheel else None
    for item in dependencies["wheels"]:
        output = packages / item["file"]
        candidates = [directory / item["file"] for directory in sources]
        if item["name"] == "universal-codex-tools" and framework_wheel is not None:
            candidates.insert(0, framework_wheel)
        if output.exists():
            if sha256(output) != item["sha256"]:
                raise ValueError("Retained dependency wheel changed: " + output.name)
            continue
        source = next((p for p in candidates if p.is_file()), None)
        if source is not None:
            if sha256(ordinary(source)) != item["sha256"]:
                raise ValueError("Dependency wheel differs from reviewed hash: " + source.name)
            shutil.copyfile(source, output)
        else:
            if item["name"] == "universal-codex-tools":
                raise ValueError(
                    "Supply the reviewed framework 0.20.0 wheel with -FrameworkWheel and -FrameworkSha256"
                )
            requirement = stage / "download.txt"
            requirement.write_text(
                f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}\n",
                encoding="utf-8",
                newline="\n",
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "--no-deps",
                    "--require-hashes",
                    "-r",
                    str(requirement),
                    "-d",
                    str(packages),
                ],
                check=True,
                stdout=sys.stderr,
            )
            if not output.is_file() or sha256(output) != item["sha256"]:
                raise ValueError("Downloaded reviewed wheel is missing or changed")
    build = stage / "build"
    build.mkdir()
    wheel, commit, newline_variations = build_wheel(project, build)
    app_wheel = packages / wheel.name
    if app_wheel.exists() and sha256(app_wheel) != sha256(wheel):
        # Wheel ZIP timestamps can differ. Keep every reviewed build by content.
        app_wheel = packages / (sha256(wheel) + "-" + wheel.name)
    if not app_wheel.exists():
        shutil.copyfile(wheel, app_wheel)
    runtime = stage / "runtime"
    runtime.mkdir()
    audits = [
        extract_wheel(packages / item["file"], item["sha256"], runtime)
        for item in dependencies["wheels"]
    ]
    audits.append(extract_wheel(app_wheel, sha256(app_wheel), runtime))
    prepared = prepare(
        root,
        runtime,
        workspace,
        state=state,
        registry=registry,
        mode=mode,
        native_target=target,
        source_commit=commit,
        app_wheel_sha256=sha256(app_wheel),
    )
    # Reviewable before selection; retained payloads stay available after refusal.
    receipt = {
        "source_commit": commit,
        "package_version": __package_version__,
        "app_wheel_sha256": sha256(app_wheel),
        "git_text_policy": "CRLF-to-LF comparison only; exact wheel/runtime bytes retain their SHA-256/RECORD identities",
        "source_newline_variations": newline_variations,
        "app_wheel": str(app_wheel),
        "snapshot": prepared["snapshot"],
        "wheel_audits": audits,
        "plugin": prepared["plugin"],
        "route": prepared["route"],
        "previous_selection_sha256": expected_selection,
        "selected": False,
        "native_started": False,
        "shared_settings_written": False,
    }
    receipt_path = root / "launcher" / ("prepared-" + prepared["snapshot"] + ".json")
    atomic_bytes(receipt_path, encoded(receipt))
    if (
        legacy
        and sha256(Path(legacy["source_selection_path"])) != legacy["source_selection_sha256"]
    ):
        raise ValueError(
            "Legacy selection changed during preparation; retained snapshot remains unselected"
        )
    selected = select(root, prepared["snapshot"], expected_selection=expected_selection)
    receipt.update(selected=True, selection_sha256=selected["selection_sha256"])
    atomic_bytes(root / "installation.json", encoded(receipt))
    # Only successful, verified staging copies are disposable. No live runtime,
    # receipt, selected payload or previous generation is removed.
    ordinary(stage)
    if not stage.resolve().is_relative_to(
        (root / ".staging").resolve()
    ) or not stage.resolve().is_relative_to(root.resolve()):
        raise ValueError("Staging cleanup escaped its installation root")
    shutil.rmtree(stage)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--framework-wheel", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--mode", choices=["headless", "live"])
    parser.add_argument("--native-target", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            install(
                args.project,
                args.root or default_root(),
                wheelhouse=args.wheelhouse,
                framework_wheel=args.framework_wheel,
                workspace=args.workspace,
                mode=args.mode,
                native_target=args.native_target,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
