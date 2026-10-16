"""Own an isolated FreeCAD window for panel and real mouse-drag verification."""

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

from codex_freecad.client import find_freecad_cmd
from codex_freecad.setup import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interactive", action="store_true", help="Hold until the run's stop.flag exists"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run = root / "work/panel-smoke" / uuid.uuid4().hex[:8]
    config = generate(run / "models", run / "config")
    macro = run / "panel.FCMacro"
    macro.write_text(
        "import sys\n"
        + f"sys.path.insert(0,{str(root / 'src')!r})\n"
        + f"sys.path.insert(0,{str(root / 'examples')!r})\n"
        + "from PySide import QtCore\nfrom panel_demo import boot\n"
        + f"QtCore.QTimer.singleShot(1500, lambda: boot({config['workspace']!r},{str(run)!r}))\n",
        encoding="utf-8",
    )
    startup = None
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 1 if args.interactive else 0
    with (run / "native.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                str(Path(find_freecad_cmd()).with_name("FreeCAD.exe")),
                "-u",
                str(run / "user.cfg"),
                "-s",
                str(run / "system.cfg"),
                str(macro),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            startupinfo=startup,
        )
        try:
            deadline = time.monotonic() + 90
            while not (run / "ready.json").exists():
                if (run / "error.txt").exists():
                    raise RuntimeError((run / "error.txt").read_text(encoding="utf-8"))
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Panel did not start; inspect " + str(run / "native.log"))
                time.sleep(0.1)
            report = json.loads((run / "ready.json").read_text(encoding="utf-8"))
            print(json.dumps({"run": str(run), "pid": process.pid, **report}, indent=2), flush=True)
            if not args.interactive:
                (run / "stop.flag").touch()
            process.wait(timeout=3600 if args.interactive else 30)
        finally:
            (run / "stop.flag").touch()
            if process.poll() is None:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
    assert process.returncode == 0


if __name__ == "__main__":
    main()
