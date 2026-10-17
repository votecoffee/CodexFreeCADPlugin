"""Build and verify a native hole/fastener demonstration through FreeCADCmd only."""

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path

from smoke_extensions import tool_count

from codex_freecad.client import HeadlessClient


def extension(capability, **arguments):
    return {"op": "extension", "capability": capability, "arguments": arguments}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="A new output folder")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    checks = []
    with HeadlessClient(workspace) as cad:
        cad.call("new_document", name="HardwareDemo")
        operations = [
            {"op": "create_cylinder", "name": "FlangeBlank", "radius": 42, "height": 12},
            extension(
                "holes.drill",
                name="CenterBore",
                base="FlangeBlank",
                diameter=16,
                positions=[[0, 0, 12]],
            ),
            extension(
                "holes.bolt_circle",
                name="Flange",
                base="CenterBore",
                diameter=6.5,
                radius=28,
                count=6,
                center=[0, 0, 12],
                style="counterbore",
                recess_diameter=11,
                recess_depth=6,
            ),
            {"op": "create_box", "name": "CouponBlank", "length": 60, "width": 40, "height": 10},
            {"op": "set_placement", "object": "CouponBlank", "position": [60, -20, 0]},
            extension(
                "holes.drill",
                name="BlindBore",
                base="CouponBlank",
                diameter=8,
                mode="blind",
                depth=6,
                positions=[[70, -10, 10]],
            ),
            extension(
                "holes.drill",
                name="Countersink",
                base="BlindBore",
                diameter=5,
                style="countersink",
                recess_diameter=10,
                positions=[[90, -10, 10]],
            ),
            extension(
                "holes.drill",
                name="Coupon",
                base="Countersink",
                diameter=6.5,
                positions=[[105, 10, 10]],
            ),
        ]
        objects = ["Flange", "Coupon"]
        for index in range(6):
            # +Z -> -Z maps local X to -X, matching holes.bolt_circle's default frame.
            angle = math.radians(index * 60)
            x, y = -28 * math.cos(angle), 28 * math.sin(angle)
            bolt, washer, nut = (prefix + str(index + 1) for prefix in ("CapBolt", "Washer", "Nut"))
            operations.extend(
                [
                    extension(
                        "fasteners.bolt",
                        name=bolt,
                        head_style="socket_cap",
                        diameter=6,
                        length=18,
                        head_diameter=10,
                        head_height=5,
                        socket_across_flats=5,
                        socket_depth=3,
                        position=[x, y, 6],
                    ),
                    extension(
                        "fasteners.washer",
                        name=washer,
                        outer_diameter=12,
                        bore_diameter=6.5,
                        thickness=1.6,
                        position=[x, y, -1.6],
                    ),
                    extension(
                        "fasteners.nut",
                        name=nut,
                        across_flats=10,
                        bore_diameter=6.5,
                        thickness=5,
                        position=[x, y, -6.6],
                    ),
                ]
            )
            objects.extend([bolt, washer, nut])
        operations.extend(
            [
                extension(
                    "fasteners.washer",
                    name="TopWasher",
                    outer_diameter=12,
                    bore_diameter=6.5,
                    thickness=1.5,
                    position=[105, 10, 10],
                ),
                extension(
                    "fasteners.bolt",
                    name="HexBolt",
                    diameter=6,
                    length=20,
                    head_height=4,
                    across_flats=10,
                    position=[105, 10, 11.5],
                ),
                extension(
                    "fasteners.nut",
                    name="HexNut",
                    across_flats=10,
                    bore_diameter=6.5,
                    thickness=5,
                    position=[105, 10, -5],
                ),
            ]
        )
        objects.extend(["TopWasher", "HexBolt", "HexNut"])
        document = cad.call("apply_operations", document="HardwareDemo", operations=operations)[
            "document"
        ]
        shapes = {
            obj["name"]: obj["shape"] for obj in document["objects"] if obj["name"] in objects
        }
        assert all(s["valid"] and s["solids"] == 1 for s in shapes.values())
        flange_volume = math.pi * (
            (42**2 - 8**2) * 12 - 6 * (3.25**2 * 12 + (5.5**2 - 3.25**2) * 6)
        )
        sink_depth = 2.5
        sink_removed = (
            math.pi * 2.5**2 * 10
            + math.pi * sink_depth * (5**2 + 5 * 2.5 + 2.5**2) / 3
            - math.pi * 2.5**2 * sink_depth
        )
        coupon_volume = 24000 - math.pi * 4**2 * 6 - sink_removed - math.pi * 3.25**2 * 10
        cap_volume = math.pi * (3**2 * 18 + 5**2 * 5) - math.sqrt(3) / 2 * 5**2 * 3
        washer_area = math.pi * (6**2 - 3.25**2)
        nut_volume = (math.sqrt(3) / 2 * 10**2 - math.pi * 3.25**2) * 5
        hex_volume = math.pi * 3**2 * 20 + math.sqrt(3) / 2 * 10**2 * 4
        expected = (
            flange_volume
            + coupon_volume
            + 6 * (cap_volume + washer_area * 1.6 + nut_volume)
            + washer_area * 1.5
            + hex_volume
            + nut_volume
        )
        assert math.isclose(shapes["Flange"]["volume_mm3"], flange_volume, rel_tol=1e-9), (
            shapes["Flange"]["volume_mm3"],
            flange_volume,
        )
        assert math.isclose(shapes["Coupon"]["volume_mm3"], coupon_volume, rel_tol=1e-9)
        assert math.isclose(sum(s["volume_mm3"] for s in shapes.values()), expected, rel_tol=1e-9)
        checks.append(
            "23 selected native solids match independent plate, bore, recess and fastener volume formulas"
        )
        interference = cad.call("check_interference", document="HardwareDemo", objects=objects)
        assert interference["counts"]["overlap"] == 0
        assert interference["revision"] == document["revision"]
        checks.append(
            "253 BREP pair checks find zero positive-volume overlaps; seating contact remains distinct"
        )
        pid = cad.process.pid
        assert not cad.call("reload_extensions")["reloaded"] and cad.process.pid == pid
        assert (
            cad.call("inspect_document", document="HardwareDemo")["revision"]
            == document["revision"]
        )
        checks.append("unchanged extension reload preserves native worker and source revision")
        saved = cad.call("save_document", document="HardwareDemo", path="HardwareDemo.FCStd")
        exported = cad.call(
            "export_model", document="HardwareDemo", objects=objects, path="HardwareDemo.step"
        )
        cad.call(
            "import_model", document="HardwareDemo", path="HardwareDemo.step", name="Roundtrip"
        )
        shape = cad.call("inspect_object", document="HardwareDemo", object_name="Roundtrip")[
            "shape"
        ]
        assert shape["valid"] and shape["solids"] == 23
        assert math.isclose(shape["volume_mm3"], expected, rel_tol=1e-6)
        checks.append("STEP roundtrip preserves 23 valid solid instances and total volume")
        status = cad.call("status")
    with HeadlessClient(workspace) as cad:
        cad.call("open_document", path="HardwareDemo.FCStd")
        original = cad.call("inspect_document", document="HardwareDemo")["revision"]
        for name in objects:
            assert cad.call("inspect_object", document="HardwareDemo", object_name=name)["shape"][
                "valid"
            ]
        cad.call(
            "apply_operations",
            document="HardwareDemo",
            operations=[
                {
                    "op": "set_property",
                    "object": "CapBolt1Parameters",
                    "property": "Length",
                    "value": 20,
                }
            ],
        )
        changed = cad.call("inspect_object", document="HardwareDemo", object_name="CapBolt1")[
            "shape"
        ]["volume_mm3"]
        assert math.isclose(changed, cap_volume + math.pi * 3**2 * 2, rel_tol=1e-9)
        restored = cad.call("undo_document", document="HardwareDemo")
        restored_shapes = {
            obj["name"]: obj["shape"] for obj in restored["objects"] if obj["name"] in objects
        }
        for name in objects:
            assert restored_shapes[name]["valid"] and restored_shapes[name]["solids"] == 1
            assert math.isclose(
                restored_shapes[name]["volume_mm3"], shapes[name]["volume_mm3"], rel_tol=1e-9
            )
        params = cad.call(
            "inspect_object", document="HardwareDemo", object_name="CapBolt1Parameters"
        )["properties"]
        assert params["Length"]["value"]["value"] == 18
        undo_same_revision = restored["revision"] == original
        checks.append(
            "fresh native process reopens all parts, edits a bolt's native dimensions and restores dimensions/geometry with Undo"
        )
    for item in (saved, exported):
        assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
    report = {
        "plugin_version": status["plugin_version"],
        "backend": "headless",
        "freecad_version": status["freecad_version"],
        "tool_count": asyncio.run(tool_count(workspace)),
        "operation_count": len(status["operations"]),
        "sample_name": "HardwareDemo",
        "objects": objects,
        "shape": shape,
        "expected_volume_mm3": expected,
        "relative_volume_tolerance": 1e-6,
        "saved": saved,
        "exported": exported,
        "interference": interference,
        "extensions": status["extensions"],
        "checks": checks,
        "panel_gui_validation": "requires manual GUI smoke test",
        "physical_drag_validation": "requires manual gesture check",
        "fastener_scope": "explicit dimensions, simplified unthreaded geometry; no standards, fits, thread contact or load claims",
        "undo_restores_revision_token": undo_same_revision,
        "undo_revision_scope": "Native BREP serialization after recompute can change the conservative revision token; dimensions and geometry are checked independently.",
    }
    (workspace / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(workspace / "result.json")


if __name__ == "__main__":
    main()
