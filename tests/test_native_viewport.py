import json
import subprocess
import sys
from pathlib import Path

import pytest

from codex_freecad.client import find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native


def test_native_drag_math_coupled_controller_cancel_undo_and_pending_edit_guards(tmp_path):
    try:
        executable = find_freecad_cmd()
    except CadError:
        pytest.skip("Native FreeCADCmd is not installed")
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "controller.py"
    script.write_text(
        "import sys, traceback\nfrom pathlib import Path\n"
        + f"sys.path[:0] = {[str(root / 'src'), str(root / 'examples'), str(root / 'tests')]!r}\n"
        + "try:\n    from native_drag_checks import verify\n"
        + f"    verify({str(tmp_path)!r})\n"
        + "except Exception:\n"
        + f"    Path({str(tmp_path / 'error.txt')!r}).write_text(traceback.format_exc(), encoding='utf-8')\n",
        encoding="utf-8",
    )
    startup = None
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    result = subprocess.run(
        [
            executable,
            "-u",
            str(tmp_path / "user.cfg"),
            "-s",
            str(tmp_path / "system.cfg"),
            str(script),
        ],
        capture_output=True,
        text=True,
        startupinfo=startup,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    error = tmp_path / "error.txt"
    assert not error.exists(), error.read_text(encoding="utf-8") if error.exists() else ""
    assert json.loads((tmp_path / "controller-checks.json").read_text())["passed"]
