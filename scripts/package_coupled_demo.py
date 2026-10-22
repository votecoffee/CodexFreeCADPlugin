"""Package the headless-verified portable demo from a clean committed source tree."""

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from mcp import Client

from codex_freecad import __package_version__, __version__
from codex_freecad.client import HeadlessClient
from codex_freecad.server import create_server
from codex_freecad.versioning import same_version


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def tool_count(workspace):
    async with Client(create_server(HeadlessClient(workspace))) as client:
        return len((await client.list_tools()).tools)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root).strip():
        raise RuntimeError("Commit the current source before packaging")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    workspace = args.workspace.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = f"PlanetaryGearbox-Coupled-v{__version__}-Demo"
    folder = output / name
    archive = output / (name + ".zip")
    if folder.exists() or archive.exists():
        raise RuntimeError("Versioned demo output already exists; choose a fresh output directory")
    report_path = workspace / "verification.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not same_version(report["plugin_version"], __version__) or not report.get(
        "fresh_process_reopen_inverse_pose_undo"
    ):
        raise RuntimeError("Matching fresh-process native verification is required")
    for key in ("saved", "exported"):
        if digest(Path(report[key]["path"])) != report[key]["sha256"]:
            raise RuntimeError("Model/STEP bytes changed since native verification")
    report.update(
        tool_count=asyncio.run(tool_count(workspace)),
        git_commit=commit,
        sample_name="PlanetaryGearbox-Coupled",
        shape={"valid": True, "solids": report["solid_count"], "volume_mm3": report["volume_mm3"]},
        checks=[
            "15 linked components, 14 joints and 26 valid solid instances",
            "four saved affine coupling rules",
            "26-solid STEP roundtrip within 1e-6 relative volume tolerance",
            "18 discrete gear-intersection samples with source pose/revision preserved",
            "fresh-process FCStd reopen, inverse carrier drive and Undo",
            "source and saved-model file bytes preserved by verification",
        ],
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    folder.mkdir()
    for item in (
        "PlanetaryGearbox-Coupled.FCStd",
        "PlanetaryGearbox-Coupled.step",
        "OpenCoupledGearbox.FCMacro",
        "verification.json",
        "Readme.md",
        "LICENSE",
    ):
        shutil.copy2(workspace / item, folder / item)
    shutil.copytree(
        workspace / "native",
        folder / "native",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for module in (folder / "native/codex_freecad").rglob("*"):
        if not module.is_file() or module.suffix not in {".py", ".json"}:
            continue
        relative = module.relative_to(folder / "native/codex_freecad")
        if module.read_bytes() != (root / "src/codex_freecad" / relative).read_bytes():
            raise RuntimeError("Native demo/source mismatch: " + module.name)
    entries = [
        {
            "path": str(path.relative_to(folder)).replace("\\", "/"),
            "sha256": digest(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    ]
    manifest = {
        "version": __version__,
        "package_version": __package_version__,
        "git_commit": commit,
        "backend": "headless",
        "panel_gui_validation": "requires manual GUI smoke test",
        "physical_drag_validation": "requires manual gesture check",
        "files": entries,
    }
    (folder / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output))
    with zipfile.ZipFile(archive) as bundle:
        for entry in entries:
            assert (
                hashlib.sha256(bundle.read(name + "/" + entry["path"])).hexdigest()
                == entry["sha256"]
            )
    (output / f"artifact-manifest-coupled-demo-v{__version__}.json").write_text(
        json.dumps(
            {
                **manifest,
                "archive": {
                    "file": archive.name,
                    "sha256": digest(archive),
                    "bytes": archive.stat().st_size,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(archive)


if __name__ == "__main__":
    main()
