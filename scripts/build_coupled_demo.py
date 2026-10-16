"""Create a portable coupled gearbox and panel demo without launching a GUI."""

import argparse
import hashlib
import shutil
from pathlib import Path

from build_planetary_demo import run_native

from codex_freecad import __version__
from codex_freecad.client import find_freecad_cmd
from codex_freecad.native_package import copy_native_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Existing v0.6 jointed model")
    parser.add_argument("--workspace", type=Path, required=True, help="A fresh output folder")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    original = args.source.resolve()
    source_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    shutil.copy2(original, workspace / "Input-Movable.FCStd")
    executable = Path(find_freecad_cmd())
    run_native(executable, workspace, gui=False, module="coupled_planetary", function="build")
    run_native(
        executable, workspace, gui=False, module="coupled_planetary", function="verify_reopened"
    )
    assert hashlib.sha256(original.read_bytes()).hexdigest() == source_hash
    root = Path(__file__).resolve().parents[1]
    package = workspace / "native/codex_freecad"
    copy_native_package(package)
    macro = """# Run through FreeCAD: Macro > Macros > Execute.
import sys
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
_folder = Path(__file__).resolve().parent
sys.path.insert(0, str(_folder / 'native'))
from codex_freecad import __version__, panel
if __version__ != 'DEMO_VERSION':
    raise RuntimeError('Restart FreeCAD before opening this demo; a different integration core is loaded')
_path = _folder / 'PlanetaryGearbox-Coupled.FCStd'
_doc = next((d for d in App.listDocuments().values() if d.FileName and Path(d.FileName).resolve() == _path.resolve()), None)
if _doc is None:
    _doc = App.openDocument(str(_path))
App.setActiveDocument(_doc.Name)
panel.install_command(_folder)
_dock = panel.show(_folder)
_dock.document.setCurrentIndex(_dock.document.findData(_doc.Name))
_dock.tabs.setCurrentIndex(1)
_dock.joint.setCurrentIndex(_dock.joint.findData('SunJoint'))
_dock.drag_button.setChecked(True)
Gui.getDocument(_doc.Name).activeView().viewTop()
Gui.getDocument(_doc.Name).activeView().fitAll()
"""
    macro = macro.replace("DEMO_VERSION", __version__)
    compile(macro, "OpenCoupledGearbox.FCMacro", "exec")
    (workspace / "OpenCoupledGearbox.FCMacro").write_text(macro, encoding="utf-8")
    shutil.copy2(root / "docs/PANEL_TESTING.md", workspace / "Readme.md")
    shutil.copy2(root / "LICENSE", workspace / "LICENSE")
    print(workspace / "OpenCoupledGearbox.FCMacro")


if __name__ == "__main__":
    main()
