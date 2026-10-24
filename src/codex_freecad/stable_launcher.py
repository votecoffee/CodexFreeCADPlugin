"""Retained stdlib-only entry, copied verbatim to an app-owned installation.

Run with the reviewed paired pythonw.exe -I -S -B. Selection never installs,
discovers a newer directory, repairs a cache, or changes profile after failure.
"""

import ctypes
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

MAX_JSON = 8 * 1024 * 1024
PINS = {"mcp": "2.3.0", "universal-codex-tools": "0.20.0"}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ordinary(path):
    """Check original components before resolution can hide a reparse point."""
    path = Path(os.path.abspath(path))
    for component in (path, *path.parents):
        info = component.stat(follow_symlinks=False)
        if component.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked/reparse installation path refused")
    return path


def inside(root, name):
    relative = PurePosixPath(name.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
        raise ValueError("Invalid retained payload path")
    path = ordinary(root.joinpath(*relative.parts))
    if not path.is_relative_to(root):
        raise ValueError("Retained payload escapes the installation")
    return path


def read_json(path):
    with ordinary(path).open("rb") as stream:
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError("Launcher JSON exceeds its bound")
    return raw, json.loads(raw)


def selection(root):
    root = ordinary(root).resolve(strict=True)
    raw, pointer = read_json(root / "launcher/current.json")
    if (
        set(pointer) != {"schema_version", "snapshot"}
        or type(pointer["schema_version"]) is not int
        or pointer["schema_version"] != 1
    ):
        raise ValueError("Unsupported launcher selection")
    revision = pointer["snapshot"]
    manifest = snapshot_manifest(root, revision)
    return {
        "installation_root": str(root),
        "selection_sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot": revision,
        "manifest": manifest,
    }


def snapshot_manifest(root, revision):
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ValueError("Invalid launcher snapshot identity")
    manifest_raw, manifest = read_json(root / "launcher/snapshots" / revision / "manifest.json")
    if hashlib.sha256(manifest_raw).hexdigest() != revision:
        raise ValueError("Selected launcher snapshot changed")
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
        or manifest.get("application_id") != "freecad-mcp-server"
        or manifest.get("pins") != PINS
    ):
        raise ValueError("Selected application or reviewed pins differ")
    if manifest.get("profile") not in {"direct-standalone-native", "direct-standalone-offline"}:
        raise ValueError("Unreviewed selected profile")
    if not isinstance(manifest.get("files"), dict) or not 2 <= len(manifest["files"]) <= 64:
        raise ValueError("Invalid snapshot file inventory")
    for name, expected in manifest["files"].items():
        if (
            not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or sha256(inside(root, name)) != expected
        ):
            raise ValueError("Selected launcher payload changed")
    entry = manifest["entry"]
    if entry not in manifest["files"] or not entry.startswith("runtimes/"):
        raise ValueError("Selected entry is not a retained runtime")
    if not isinstance(manifest.get("package_version"), str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", manifest["package_version"]
    ):
        raise ValueError("Invalid selected package version")
    if not isinstance(manifest.get("runtime"), str) or not manifest["runtime"].startswith(
        "runtimes/"
    ):
        raise ValueError("Runtime is not a retained application payload")
    args = manifest.get("args")
    if (
        not isinstance(args, list)
        or len(args) > 128
        or any(not isinstance(a, str) or "\0" in a or len(a) > 32768 for a in args)
    ):
        raise ValueError("Invalid reviewed argument list")
    inside(root, manifest["runtime"])
    inside(root, "cwd")
    if sha256(ordinary(root / "Start-Mcp.py")) != manifest["stable_entry_sha256"]:
        raise ValueError("Stable entry bytes differ from the selected review")
    return manifest


def deployment_info():
    """Selection is an installation observation, never a health inference."""
    root = os.environ.get("FREECAD_STABLE_ROOT")
    result = {
        "stable_launcher": bool(root),
        "running_package_version": None,
        "selected_package_version": None,
        "health": "not-assessed",
    }
    if not root:
        return result
    try:
        selected = selection(Path(root))
        result.update(
            selected_package_version=selected["manifest"]["package_version"],
            selected_snapshot=selected["snapshot"],
            running_snapshot=os.environ.get("FREECAD_STABLE_SNAPSHOT"),
            selection_sha256=selected["selection_sha256"],
        )
    except (OSError, ValueError, KeyError, TypeError):
        result["selection_state"] = "unavailable-or-invalid"
    return result


def error(message):
    """pythonw may have None streams before the verified backend reconstructs them."""
    raw = ("FreeCAD launcher refused: " + str(message)[:800] + "\n").encode("utf-8", "replace")
    if sys.stderr is not None:
        sys.stderr.write(raw.decode("utf-8", "replace"))
        sys.stderr.flush()
    elif os.name == "nt":
        from ctypes import wintypes as w

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetStdHandle.argtypes, api.GetStdHandle.restype = [w.DWORD], w.HANDLE
        api.WriteFile.argtypes, api.WriteFile.restype = (
            [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p],
            w.BOOL,
        )
        written = w.DWORD()
        api.WriteFile(
            api.GetStdHandle(w.DWORD(-12).value), raw, len(raw), ctypes.byref(written), None
        )


def main(root=None):
    root = ordinary(root or Path(__file__).parent).resolve(strict=True)
    if len(sys.argv) != 1:
        raise ValueError(
            "Stable entry takes no overrides; update the reviewed selection explicitly"
        )
    if os.name != "nt" or not (
        sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    ):
        raise ValueError("Use the reviewed windowless interpreter with -I -S -B")
    selected = selection(root)
    manifest = selected["manifest"]
    interpreter = ordinary(manifest["python"])
    if (
        not os.path.samefile(interpreter, sys.executable)
        or interpreter.name.lower() != "pythonw.exe"
        or sha256(interpreter) != manifest["python_sha256"]
    ):
        raise ValueError("The reviewed real windowless interpreter differs")
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"):
        os.environ.pop(name, None)
    os.environ.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        PYTHONIOENCODING="utf-8",
        FREECAD_STABLE_ROOT=str(root),
        FREECAD_STABLE_SNAPSHOT=selected["snapshot"],
    )
    os.chdir(inside(root, "cwd"))
    entry = inside(root, manifest["entry"])
    code = entry.read_bytes()
    if hashlib.sha256(code).hexdigest() != manifest["files"][manifest["entry"]]:
        raise ValueError("Selected entry changed before execution")
    sys.argv = [str(entry), *manifest["args"]]
    # No wrapper child: this exact surviving pythonw process owns its native job,
    # shared admission locks, original inherited wire and durable owner identity.
    exec(compile(code, str(entry), "exec"), {"__name__": "__main__", "__file__": str(entry)})


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        try:
            error(
                str(exc)
                if isinstance(exc, (ValueError, OSError))
                else "Invalid or unavailable reviewed selection"
            )
        finally:
            os._exit(1)
