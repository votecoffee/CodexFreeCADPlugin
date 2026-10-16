"""Build a portable jointed gearbox demo from the existing editable static demo."""

import argparse
import shutil
from pathlib import Path

from build_planetary_demo import run_native

from codex_freecad.client import find_freecad_cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, required=True, help="Corrected static showcase FCStd"
    )
    parser.add_argument("--workspace", type=Path, default=Path("models/MovablePlanetary"))
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / "PlanetaryGearbox.FCStd"
    if source.exists():
        raise ValueError("Choose a fresh workspace; this builder preserves existing inputs")
    shutil.copy2(args.source, source)
    executable = Path(find_freecad_cmd())
    run_native(
        executable.with_name("FreeCAD.exe"),
        workspace,
        gui=True,
        module="movable_planetary",
        function="build_and_render",
    )
    run_native(executable, workspace, gui=False, module="movable_planetary", function="verify")
    run_native(
        executable.with_name("FreeCAD.exe"),
        workspace,
        gui=True,
        module="movable_planetary",
        function="smoke_player",
    )
    print(workspace / "PlanetaryGearbox-Movable.FCStd")


if __name__ == "__main__":
    main()
