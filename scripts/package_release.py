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
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads(args.live_report.read_text(encoding="utf-8"))
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
        prefix + ".png": Path(report["screenshot"]),
        f"VALIDATION-v{version}.md": root / "docs/VALIDATION.md",
        f"CHANGES-v{version}.md": root / "docs/CHANGELOG.md",
        f"test-results-v{version}.xml": args.tests,
        wheel.name: wheel,
    }
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
        for name in installed.namelist():
            if name.startswith("codex_freecad/") and name.endswith(".py"):
                if installed.read(name) != source.read("CodexFeeCADPlugin/src/" + name):
                    raise RuntimeError("Wheel/source mismatch: " + name)

    guide = f"""# FreeCAD plugin v{version}

The project is updated in `{root}`. It now has {tool_count} MCP tools and {operation_count} edit operations.

New functionality includes three-point sketch arcs, dimensioned rectangles, adding geometry to existing sketches, detailed sketch inspection, native revolutions, and editable linear/circular patterns backed by native link arrays. Earlier imports, fillets/chamfers, mesh conversion, measurement and view tools remain available.

**{counts["passed"]} automated tests passed**, with {counts["skipped"]} skipped. Native GUI checks also passed on FreeCAD 1.0.2. The included example revolves a constrained rectangle into a flange, cuts six circular-pattern holes, and repeats the finished part in a three-instance row. Native measured volume is {report["shape"]["volume_mm3"]} mm³.

## Load the update

The project virtual environment and generated macros have already been updated on this computer. Restart the FreeCAD MCP servers in Codex, or restart Codex. Then run the regenerated `.local\\StartBridge.FCMacro` from the project directory inside FreeCAD using **Macro → Macros → Execute**. The macro reloads integration code while preserving open native documents.

If you have not registered the servers yet, run `scripts\\Register-Codex.ps1` from the project directory and start a new chat. To rebuild on another machine or regenerate configuration, run `scripts\\Setup.ps1`.

Try: “Create a revolved flange with a 60 mm outer diameter, 20 mm bore and 8 mm thickness. Add six 4 mm holes on a 44 mm bolt circle, repeat the finished flange three times at a 75 mm X step, and save FCStd and STEP.”

Try: “Inspect my sketch's named rectangle dimensions, change its width to 21 mm, and verify the downstream revolution and pattern volumes.”

The default CAD workspace is the project's `models` folder. Source inputs remain unchanged; imports return source hashes. The import operation can also be included in an atomic edit batch. Use internal object names and inspect topology again after changes; EdgeN/FaceN labels are specific to the inspected shape.

Pattern counts include the original and range from 2 to 200. Linear steps and circular centers/axes use document coordinates before the pattern object's own placement. Full +/-360 degree circles omit the repeated endpoint; partial spans include both endpoints. Copies remain separate solids and link source dimensions. Source placement is sampled when creating/updating the pattern; use the matching set-pattern operation to resample it after a placement change. Nested body features should be patterned through their top-level Body.

Rectangles are fully dimensioned by default and report width/height/origin constraint indices. Use `inspect_sketch` and `set_datum` to edit them. Sketch coordinates are local XY; use Placement for the profile's plane. A solid revolution needs an appropriate closed profile and axis. There are no custom Python feature proxies in these native features.

The optional API adapter exposes {tool_count - 1} text-result tools and has local tests. Paid API execution and plugin-browser installation remain untested. Assemblies, splines, expression editing and broad FreeCAD workbench coverage remain future work.

Versioned source ZIP, wheel, FCStd/STEP sample, PNG preview, changelog, test XML and validation report accompany this guide. The manifest records hashes and the native GUI check list. Earlier v0.1/v0.2 deliverables remain intact.
"""
    guide_path = output / f"Start-Here-v{version}.md"
    guide_path.write_text(guide, encoding="utf-8")
    artifact_names = [*copies, source_zip.name, guide_path.name]
    manifest = {
        "version": version,
        "tests": counts,
        "tool_count": tool_count,
        "operation_count": operation_count,
        "source_files": len(entries),
        "native_gui_checks": report["checks"],
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
                "native_gui_checks": len(report["checks"]),
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
