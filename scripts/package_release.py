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
    git_state = subprocess.check_output(["git", "status", "--porcelain"], cwd=root).decode().strip()
    if git_state:
        raise RuntimeError("Commit the current source before packaging a release")
    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
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

New functionality includes native movable assemblies: linked components, grounding, fixed/revolute/slider joints, travel limits, coordinated absolute joint positioning and assembly inspection. Explicit positioning supports directed trees rooted at grounded components. The shared engine works in the live GUI and FreeCADCmd. Earlier sweep, helix, parameter, loft, sketch, pattern, import, finishing and measurement tools remain available.

**{counts["passed"]} automated tests passed**, with {counts["skipped"]} skipped. All {len(report["checks"])} native GUI checks also passed on FreeCAD 1.0.2. The included sample uses parameter-driven circular sections to sweep a hollow 90-degree pipe elbow and a four-turn helical solid. The elbow has a 30 mm bend radius, 6 mm outer radius and 4 mm inner radius. The coil has a 15 mm centerline radius, 10 mm pitch, 40 mm axial height and 2 mm wire radius. It contains two separate valid solids with native total volume {report["shape"]["volume_mm3"]} mm³, compared with analytic {report["expected_volume_mm3"]} mm³ within a 1e-5 relative tolerance. Native helical geometry is approximated; exact numeric equality is not claimed.

The source corresponds to local Git commit `{git_commit}`. Origin points to the user's GitHub repository; no push was performed. Release packaging requires a clean working tree and records this commit in the artifact manifest.

## Load the update

The project virtual environment and generated macros have already been updated on this computer. Restart the FreeCAD MCP servers in Codex, or restart Codex. Then run the regenerated `.local\\StartBridge.FCMacro` from the project directory inside FreeCAD using **Macro → Macros → Execute**. The macro reloads integration code while preserving open native documents.

If you have not registered the servers yet, run `scripts\\Register-Codex.ps1` from the project directory and start a new chat. To rebuild on another machine or regenerate configuration, run `scripts\\Setup.ps1`.

Try: “Create a hollow quarter-circle elbow with a 30 mm bend radius, 6 mm outer radius and 4 mm inner radius. Sweep the two sections along the arc, cut out the bore, verify the volume and save FCStd and STEP.”

Try: “Create an assembly with a grounded base, a revolute arm and a sliding tool. Set joint limits, move the arm to 60 degrees and the tool extension to 12 mm, inspect the resulting assembly and save FCStd.”

`examples/movable_arm.py` is a backend-independent joint example. The planetary demonstration adds a native jointed 4:1 gearbox and optional Play/Pause/Reset controls. The model uses standard installed FreeCAD Assembly proxies; gear ratios are coordinated by its analytical controller. See README.md for component frames, angle wrapping, limits, save/reopen and positioning scope. Native joints remain movable after positioning; no integration feature proxy is embedded in FCStd.

Try: “Open the included SweptParts FCStd sample. Inspect its design parameters and expressions. Change Design.CoilHeight to 50 mm and WireRadius to 2.5 mm. Verify the coil recomputes and save a separate copy.”

`sweep` takes 1–50 distinct top-level single-wire `profiles` and a top-level `path`. Position and rotate the sections before sweeping; the tool does not automatically choose their planes. An empty `path_edges` uses the entire single-wire path; a nonempty list selects current EdgeN names and must form one connected wire. Reinspect topology and use revision guards after upstream edits. Solid mode requires closed sections and one valid positive-volume result; surface mode accepts open sections. Frenet framing defaults to false. Transition choices are transformed, right_corner and round_corner. `set_sweep` replaces sections, path and edge selection while preserving omitted framing/solid/transition controls.

`create_helix` creates a native Part::Helix along local +Z with positive pitch, height and starting radius, optional taper angle strictly between -90 and 90 degrees and optional left_handed=true. Conical top radius must stay positive, and native creation is limited to 10,000 turns. Its pitch/height/radius/angle are native dimensional properties, editable through `set_property` or expressions. The example positions the coil section perpendicular to the initial helix tangent and uses Frenet framing. A wire sweep does not model spring end finishing or engineering spring performance.

Named parameter types are length, angle, number and integer. Use `set_property` to edit their values and `set_expression` to drive numeric properties, placement translations or driving dimensional constraints. Formulas support arithmetic, parentheses, fixed length/angle units, pi and numeric references inside the same document. Functions, external documents, strings and Python execution are excluded. `clear_expression` keeps the last evaluated value; clear a binding before direct datum/placement assignment.

Lofts use 2–50 distinct top-level single-wire profiles in section order. Solid mode requires closed wires and exactly one resulting positive-volume solid; surface and ruled modes are also supported. Use `set_loft` for profiles/options. Mirrors use a top-level source and document-space plane point/normal; the result contains only the reflected geometry. Use `set_mirror` for the plane. The included sweep example uses a disconnected native boolean union to retain both solids in one final feature without joining material across the gap.

The default CAD workspace is the project's `models` folder. Source inputs remain unchanged; imports return source hashes. The import operation can also be included in an atomic edit batch. Use internal object names and inspect topology again after changes; EdgeN/FaceN labels are specific to the inspected shape.

Pattern counts include the original and range from 2 to 200. Linear steps and circular centers/axes use document coordinates before the pattern object's own placement. Full +/-360 degree circles omit the repeated endpoint; partial spans include both endpoints. Copies remain separate solids and link source dimensions. Source placement is sampled when creating/updating the pattern; use the matching set-pattern operation to resample it after a placement change. Nested body features should be patterned through their top-level Body.

Rectangles are fully dimensioned by default and report width/height/origin constraint indices. Use `inspect_sketch` and `set_datum` to edit them. Sketch coordinates are local XY; use Placement for the profile's plane. A solid revolution needs an appropriate closed profile and axis. There are no custom Python feature proxies in these native features.

The optional API adapter exposes {tool_count - 1} text-result tools and has local tests. Paid API execution and plugin-browser installation remain untested. Closed-loop joint driving, nested assemblies, collision/contact/dynamics, splines, sheet metal, TechDraw and broad FreeCAD workbench coverage remain future work.

Versioned source ZIP, wheel, FCStd/STEP sample, PNG preview, changelog, test XML and validation report accompany this guide. The manifest records hashes, the source commit and the native GUI check list. Earlier versioned deliverables remain intact.
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
        "sample": {
            "name": sample_name,
            "shape": report["shape"],
            "expected_volume_mm3": report["expected_volume_mm3"],
            "relative_volume_tolerance": report["relative_volume_tolerance"],
        },
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
