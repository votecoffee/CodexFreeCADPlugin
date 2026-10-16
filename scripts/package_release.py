"""Package versioned source, wheel, native sample and validation evidence into a chosen directory."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from codex_freecad import __version__


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    validation = parser.add_mutually_exclusive_group(required=True)
    validation.add_argument("--live-report", type=Path)
    validation.add_argument(
        "--headless-report", type=Path, help="Package with GUI validation explicitly pending"
    )
    parser.add_argument("--tests", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    git_state = subprocess.check_output(["git", "status", "--porcelain"], cwd=root).decode().strip()
    if git_state:
        raise RuntimeError("Commit the current source before packaging a release")
    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = args.headless_report or args.live_report
    report = json.loads(report_path.read_text(encoding="utf-8"))
    headless = args.headless_report is not None
    if headless and report.get("backend") != "headless":
        raise RuntimeError("Headless packaging requires a report labeled backend=headless")
    suites = ET.parse(args.tests).getroot().findall(".//testsuite")
    counts = {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if not suites or counts["failures"] or counts["errors"]:
        raise RuntimeError("Packaging requires a completed passing JUnit test report")
    counts["passed"] = counts["tests"] - counts["skipped"]
    version = __version__
    if report.get("plugin_version") != version:
        raise RuntimeError("Native validation report version does not match the package")
    tool_count, operation_count = report["tool_count"], report["operation_count"]
    wheel = root / "dist" / f"codex_freecad-{version}-py3-none-any.whl"
    sample_name = report.get("sample_name", "FinishedPlate")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", sample_name):
        raise RuntimeError("Invalid sample artifact name")
    prefix = f"{sample_name}-v{version}"
    copies = {
        prefix + ".FCStd": Path(report["saved"]["path"]),
        prefix + ".step": Path(report["exported"]["path"]),
        f"VALIDATION-v{version}.md": root / "docs/VALIDATION.md",
        f"CHANGES-v{version}.md": root / "docs/CHANGELOG.md",
        f"Extension-Reload-Guide-v{version}.md": root / "docs/EXTENSIONS.md",
        f"test-results-v{version}.xml": args.tests,
        wheel.name: wheel,
        f"native-validation-v{version}.json": report_path,
    }
    if not headless:
        copies[prefix + ".png"] = Path(report["screenshot"])
    for name, source in copies.items():
        shutil.copy2(source, output / name)
    for key in ("saved", "exported"):
        if digest(Path(report[key]["path"])) != report[key]["sha256"]:
            raise RuntimeError("Native sample changed since its validation report")

    raw = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root
    )
    names = sorted(set(name for name in raw.decode("utf-8").split("\0") if name))
    entries = [
        {"path": name, "sha256": digest(root / name), "bytes": (root / name).stat().st_size}
        for name in names
    ]
    source_zip = output / f"CodexFreeCADPlugin-v{version}-source.zip"
    with zipfile.ZipFile(source_zip, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in entries:
            bundle.write(root / item["path"], "CodexFeeCADPlugin/" + item["path"])
        bundle.writestr(
            "CodexFeeCADPlugin/SOURCE_MANIFEST.json", json.dumps({"files": entries}, indent=2)
        )
    with zipfile.ZipFile(source_zip) as source, zipfile.ZipFile(wheel) as installed:
        for item in entries:
            if (
                hashlib.sha256(source.read("CodexFeeCADPlugin/" + item["path"])).hexdigest()
                != item["sha256"]
            ):
                raise RuntimeError("Source archive verification failed")
        expected_package = {
            item["path"][4:]
            for item in entries
            if item["path"].startswith("src/codex_freecad/")
            and Path(item["path"]).suffix in {".py", ".json"}
        }
        actual_package = {
            name
            for name in installed.namelist()
            if name.startswith("codex_freecad/") and Path(name).suffix in {".py", ".json"}
        }
        if expected_package != actual_package:
            raise RuntimeError("Wheel is missing or has unexpected package modules/manifests")
        for name in actual_package:
            if name.startswith("codex_freecad/"):
                if installed.read(name) != source.read("CodexFeeCADPlugin/src/" + name):
                    raise RuntimeError("Wheel/source mismatch: " + name)

    validation_scope = (
        "Native headless checks passed. New panel GUI checks and physical mouse dragging remain pending the user's manual test."
        if headless
        else f"All {len(report['checks'])} recorded native GUI checks passed. Physical mouse gestures require separate evidence."
    )
    guide = rf"""# FreeCAD plugin v{version}

The project is updated in `{root}` with {tool_count} MCP tools and {operation_count} edit operations. **{counts["passed"]} automated tests passed**, with {counts["skipped"]} skipped.

{validation_scope}

The included {sample_name} sample has {report["shape"]["solids"]} valid solid instances and native total volume {report["shape"]["volume_mm3"]} mm³. Read `native-validation-v{version}.json` for the actual sampled geometry and verification scope. Discrete motion checks do not prove continuous collision-free travel, physical gear contact or load capacity.

This source corresponds to local Git commit `{git_commit}`. The manifest records the source commit and SHA-256 hashes. No push was performed; the user pushes to origin.

## Load the update

Run `scripts\Setup.ps1` to regenerate local configuration. Restart the FreeCAD MCP servers in Codex, then execute `.local\StartBridge.FCMacro` through FreeCAD's Macro menu. It reloads the integration and opens the Codex CAD dock while preserving open models. The generated `OpenFreeCADPanel.FCMacro` opens local controls without connecting chat. A generated optional FreeCAD workbench folder is also available. Registration instructions are in README.md.

This initial v0.8 core migration adds permanent extension tools. After it is loaded, ordinary feature updates use `reload_extensions` in the existing chat, the dock's Reload extensions button, or `.local\ReloadExtensions.FCMacro`. Discover current capabilities with `list_capabilities` and `describe_capability`; invoke reads with `run_query`, and edits with the stable extension operation envelope. `docs/EXTENSIONS.md` in the source archive explains installation, schema guards, supported reload scope and extension authoring. This update includes native tube creation and mass properties as example capabilities.

Model provides protected parameter editing and a linked-source shortcut. Motion provides absolute joint positions, playback, stored ratio/offset controls and an explicit viewport drag mode. Checks separates BREP overlap, contact and insufficient clearance, and samples motion on a hidden model copy without consuming source Undo. Save/export and chat edits wait while a native edit is active.

For the portable gearbox ZIP, extract everything and execute `OpenCoupledGearbox.FCMacro` to open the model and Motion tab. Enter SunJoint=90 degrees: CarrierJoint should be 22.5 and each planet joint -67.5 degrees relative to the carrier. The saved ratio metadata is applied by the Codex CAD controller and both chat backends. Native Assembly's separate dragging does not enforce these rules.

Read `docs/PANEL_TESTING.md` in the source archive for the user's manual panel/drag check. From the repository, run `.venv\Scripts\python.exe scripts\smoke_panel.py --interactive` to open an isolated test window. New GUI checks are intentionally left for the user; headless controller tests do not prove Coin event delivery or physical picking.

The optional Responses adapter exposes {tool_count - 1} text-result tools. Paid API execution, plugin-browser installation, closed-loop driving, nested assemblies, dynamics and other FreeCAD versions remain unverified. Earlier versioned artifacts remain intact.
"""
    guide_path = output / f"Start-Here-v{version}.md"
    guide_path.write_text(guide, encoding="utf-8")
    artifact_names = [*copies, source_zip.name, guide_path.name]
    manifest = {
        "version": version,
        "git_commit": git_commit,
        "tests": counts,
        "tool_count": tool_count,
        "operation_count": operation_count,
        "extension_catalog": report.get("extensions"),
        "sample": {
            "name": sample_name,
            "shape": report["shape"],
            "expected_volume_mm3": report.get("expected_volume_mm3"),
            "relative_volume_tolerance": report.get("relative_volume_tolerance"),
        },
        "source_files": len(entries),
        "validation_backend": "headless" if headless else "live",
        "native_gui_checks": [] if headless else report["checks"],
        "native_headless_checks": report["checks"] if headless else [],
        "physical_drag_validation": report.get(
            "physical_drag_validation", "not recorded by this report"
        ),
        "freecad_version": report["freecad_version"],
        "artifacts": [
            {"file": name, "sha256": digest(output / name), "bytes": (output / name).stat().st_size}
            for name in sorted(artifact_names)
        ],
    }
    (output / f"artifact-manifest-v{version}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "version": version,
                "tests": counts,
                "source_files": len(entries),
                "validation_backend": "headless" if headless else "live",
                "native_checks": len(report["checks"]),
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
