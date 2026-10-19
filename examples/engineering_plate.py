"""Create a drilled plate, BOM, change preview, thickness variants and dimensioned SVG."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from codex_freecad.client import HeadlessClient, LiveClient


def extension(capability, **arguments):
    return {"op": "extension", "capability": capability, "arguments": arguments}


def build(cad, workspace, name):
    outputs = {
        "model": name + ".FCStd",
        "step": name + ".step",
        "drawing": name + ".svg",
        "bom": name + "-BOM.csv",
        "study": name + "-Study.json",
        "preview": name + "-Preview.json",
        "verification": name + "-Verification.json",
    }
    if any((workspace / path).exists() for path in outputs.values()):
        raise ValueError("Choose a fresh --name; existing outputs are preserved")
    if Path(cad.call("status")["workspace"]) != workspace:
        raise ValueError("Client and backend must use the same workspace")
    created = cad.call("new_document", name=name)
    cad.call(
        "apply_operations",
        document=name,
        expected_revision=created["revision"],
        operations=[
            {
                "op": "create_parameters",
                "name": "Design",
                "parameters": [
                    {"name": "Thickness", "type": "length", "value": 8},
                ],
            },
            {"op": "create_box", "name": "Blank", "length": 80, "width": 50, "height": 8},
            {
                "op": "set_expression",
                "object": "Blank",
                "property": "Height",
                "expression": "Design.Thickness",
            },
            extension(
                "holes.drill",
                name="Plate",
                base="Blank",
                diameter=6.5,
                positions=[
                    [10, 10, 8],
                    [70, 10, 8],
                    [10, 40, 8],
                    [70, 40, 8],
                ],
            ),
            extension(
                "bom.set_metadata",
                object="Plate",
                part_number="DEMO-PLATE",
                material="Aluminium (nominal density)",
                density_kg_m3=2700,
            ),
            {
                "op": "linear_pattern",
                "name": "PlateRow",
                "source": "Plate",
                "count": 3,
                "step": [100, 0, 0],
            },
            extension("bom.create_sheet", name="PartsList", objects=["PlateRow"]),
        ],
    )

    def query(capability, **arguments):
        return cad.call("run_query", document=name, capability=capability, arguments=arguments)[
            "result"
        ]

    before = cad.call("inspect_document", document=name)["revision"]
    study_args = {
        "object": "Design",
        "property": "Thickness",
        "values": [4, 6, 8],
        "objects": ["Plate"],
        "density_kg_m3": 2700,
    }
    study = query("studies.parameter_sweep", **study_args)
    net_area = 80 * 50 - 4 * math.pi * (6.5 / 2) ** 2
    for frame in study["frames"]:
        if not math.isclose(frame["total_volume_mm3"], net_area * frame["value"], rel_tol=1e-8):
            raise AssertionError("Thickness study disagrees with analytic drilled plate volume")
    preview = query(
        "studies.preview_changes",
        changes=[
            {"object": "Design", "property": "Thickness", "value": 6},
            {"object": "Blank", "property": "Length", "value": 90},
        ],
        objects=["PlateRow"],
        density_kg_m3=2700,
    )
    material = preview["objects"][0]
    for key, expected in {
        "added_volume_mm3": 10 * 50 * 6 * 3,
        "removed_volume_mm3": net_area * 2 * 3,
        "delta_volume_mm3": (10 * 50 * 6 - net_area * 2) * 3,
    }.items():
        if not math.isclose(material[key], expected, rel_tol=1e-8):
            raise AssertionError("Change preview disagrees with analytic linked-plate material")
    if cad.call("inspect_document", document=name)["revision"] != before:
        raise AssertionError("Parameter query changed the source model")
    variants = cad.call(
        "apply_operations",
        document=name,
        operations=[
            extension("studies.create_variants", name="ThicknessVariants", **study_args),
        ],
    )["results"][0]["result"]
    cad.call(
        "apply_operations",
        document=name,
        operations=[
            {"op": "set_property", "object": item, "property": "Visibility", "value": False}
            for frame in variants["variants"]
            for item in frame["objects"]
        ]
        + [
            extension(
                "drawings.create_sheet",
                name="PlateDrawing",
                objects=["Plate"],
                title="Drilled mounting plate",
                part_number="DEMO-PLATE",
                revision="A",
            )
        ],
    )
    bom = query("bom.inspect", objects=["PlateRow"])
    drawing = query("drawings.render_svg", page="PlateDrawing")
    if bom["quantity"] != 3 or not math.isclose(
        bom["total_volume_mm3"], net_area * 8 * 3, rel_tol=1e-8
    ):
        raise AssertionError("BOM quantity or volume disagrees with the three linked plates")
    cad.call("save_document", document=name, path=outputs["model"])
    cad.call("export_model", document=name, objects=["PlateRow"], path=outputs["step"])
    (workspace / outputs["drawing"]).write_text(drawing["svg"], encoding="utf-8")
    (workspace / outputs["bom"]).write_text(bom["csv"], encoding="utf-8", newline="")
    (workspace / outputs["study"]).write_text(json.dumps(study, indent=2) + "\n", encoding="utf-8")
    (workspace / outputs["preview"]).write_text(
        json.dumps(preview, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "name": name,
        "backend": cad.call("status")["mode"],
        "checks": [
            "analytic plate volumes for all three thicknesses",
            "analytic added/removed material for two proposed edits across three linked plates",
            "query preserves source revision",
            "BOM counts three linked plates",
            "native TechDraw extent dimensions validated during creation",
        ],
        "bom_quantity": bom["quantity"],
        "bom_mass_kg": bom["total_mass_kg"],
        "drawing_views": drawing["views"],
        "artifacts": [
            {"file": path, "sha256": hashlib.sha256((workspace / path).read_bytes()).hexdigest()}
            for key, path in outputs.items()
            if key != "verification"
        ],
        "scope": "Native geometry and numerical checks. GUI page appearance, physical printing, tolerances and load capacity require separate validation.",
    }
    (workspace / outputs["verification"]).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("work/engineering-demo"))
    parser.add_argument("--name", default="EngineeringPlate")
    parser.add_argument("--mode", choices=["headless", "live"], default="headless")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    client = (
        HeadlessClient(workspace)
        if args.mode == "headless"
        else LiveClient(workspace / ".codex-freecad-live.json")
    )
    try:
        print(json.dumps(build(client, workspace, args.name), indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
