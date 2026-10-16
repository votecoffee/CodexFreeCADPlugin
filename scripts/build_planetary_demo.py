"""Build and render the planetary gearbox using isolated native FreeCAD processes."""

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from codex_freecad.client import find_freecad_cmd


def run_native(executable, workspace, *, gui):
    root = Path(__file__).resolve().parents[1]
    runtime = workspace / ".runtime" / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    function = "present" if gui else "build"
    code = (
        "import sys, json, traceback\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(root / 'src')!r})\n"
        f"sys.path.insert(0, {str(root / 'examples')!r})\n"
        "import FreeCAD as App\n"
        f"from planetary_gearbox import {function}\n"
        "def run_demo():\n"
        "    try:\n"
        f"        {function}({str(workspace)!r})\n"
        f"        Path({str(runtime / 'done.json')!r}).write_text(json.dumps({{'done': True}}))\n"
        "    except Exception:\n"
        f"        Path({str(runtime / 'error.txt')!r}).write_text(traceback.format_exc(), encoding='utf-8')\n"
    )
    if gui:
        code += (
            "    finally:\n"
            "        for name in list(App.listDocuments()):\n"
            "            App.closeDocument(name)\n"
            "        import FreeCADGui as Gui\n"
            "        Gui.getMainWindow().close()\n"
            "from PySide import QtCore\n"
            "QtCore.QTimer.singleShot(1500, run_demo)\n"
        )
    else:
        code += "run_demo()\n"
    script = runtime / ("render.FCMacro" if gui else "build.py")
    script.write_text(code, encoding="utf-8")
    startup = None
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    with (runtime / "native.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            [
                str(executable),
                "-u",
                str(runtime / "user.cfg"),
                "-s",
                str(runtime / "system.cfg"),
                str(script),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            startupinfo=startup,
            cwd=runtime,
            timeout=900,
            check=True,
        )
    error = runtime / "error.txt"
    if error.exists():
        raise RuntimeError(error.read_text(encoding="utf-8"))
    if not (runtime / "done.json").exists():
        raise RuntimeError("Native demo did not complete; inspect " + str(runtime / "native.log"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("models/PlanetaryDemo"))
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Render the already-built demo instead of rebuilding",
    )
    parser.add_argument("--freecad-cmd")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    executable = Path(find_freecad_cmd(args.freecad_cmd))
    if not args.render_only:
        if (workspace / "PlanetaryGearbox.FCStd").exists():
            raise RuntimeError("Choose a new workspace for rebuilding, or use --render-only")
        run_native(executable, workspace, gui=False)
    run_native(executable.with_name("FreeCAD.exe"), workspace, gui=True)
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "assembled": str(workspace / "PlanetaryGearbox-Showcase.FCStd"),
                "exploded": str(workspace / "PlanetaryGearbox-Exploded.FCStd"),
                "preview": str(workspace / "PlanetaryGearbox.png"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
