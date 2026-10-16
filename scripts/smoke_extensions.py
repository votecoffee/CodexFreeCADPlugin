"""Headless native extension sample and release evidence; never opens a GUI."""

import argparse
import asyncio
import json
import math
from pathlib import Path

from mcp import Client

from codex_freecad.client import HeadlessClient
from codex_freecad.server import create_server


async def tool_count(workspace):
    async with Client(create_server(HeadlessClient(workspace))) as client:
        return len((await client.list_tools()).tools)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    expected = math.pi * (10**2 - 6**2) * 20
    checks = []
    with HeadlessClient(workspace) as cad:
        cad.call("new_document", name="ExtensionDemo")
        described = cad.call("describe_capability", capability="parts.create_tube")
        cad.call(
            "apply_operations",
            document="ExtensionDemo",
            operations=[
                {
                    "op": "extension",
                    "capability": "parts.create_tube",
                    "catalog_revision": described["catalog_revision"],
                    "arguments": {
                        "name": "Sleeve",
                        "outer_radius": 10,
                        "inner_radius": 6,
                        "height": 20,
                    },
                }
            ],
        )
        shape = cad.call("inspect_object", document="ExtensionDemo", object_name="Sleeve")["shape"]
        assert shape["valid"] and shape["solids"] == 1
        assert math.isclose(shape["volume_mm3"], expected, rel_tol=1e-9)
        checks.append("extension-created native cylinder/cut sleeve matches analytic volume")
        before = cad.call("inspect_document", document="ExtensionDemo")["revision"]
        mass = cad.call(
            "run_query",
            document="ExtensionDemo",
            capability="parts.mass_properties",
            arguments={"object": "Sleeve", "density_kg_m3": 7800},
        )["result"]
        assert math.isclose(mass["mass_kg"], expected * 7800e-9, rel_tol=1e-9)
        assert cad.call("inspect_document", document="ExtensionDemo")["revision"] == before
        checks.append("guarded native mass query matches declared density and preserves revision")
        pid = cad.process.pid
        reloaded = cad.call("reload_extensions")
        assert not reloaded["reloaded"] and cad.process.pid == pid
        checks.append("unchanged extension reload is a no-op in the same native worker")
        saved = cad.call("save_document", document="ExtensionDemo", path="ExtensionSleeve.FCStd")
        exported = cad.call(
            "export_model",
            document="ExtensionDemo",
            objects=["Sleeve"],
            path="ExtensionSleeve.step",
        )
        cad.call(
            "import_model", document="ExtensionDemo", path="ExtensionSleeve.step", name="Snapshot"
        )
        snapshot = cad.call("inspect_object", document="ExtensionDemo", object_name="Snapshot")[
            "shape"
        ]
        assert snapshot["valid"] and snapshot["solids"] == 1
        assert math.isclose(snapshot["volume_mm3"], expected, rel_tol=1e-6)
        checks.append("one-solid STEP roundtrip preserves sleeve volume")
        status = cad.call("status")
    with HeadlessClient(workspace) as cad:
        name = cad.call("open_document", path="ExtensionSleeve.FCStd")["name"]
        assert cad.call("inspect_object", document=name, object_name="Sleeve")["shape"]["valid"]
        checks.append("fresh native process reopens the persistent native features")
    report = {
        "plugin_version": status["plugin_version"],
        "backend": "headless",
        "freecad_version": status["freecad_version"],
        "tool_count": asyncio.run(tool_count(workspace)),
        "operation_count": len(status["operations"]),
        "sample_name": "ExtensionSleeve",
        "shape": shape,
        "expected_volume_mm3": expected,
        "relative_volume_tolerance": 1e-6,
        "saved": saved,
        "exported": exported,
        "mass_properties": mass,
        "extensions": status["extensions"],
        "checks": checks,
        "panel_gui_validation": "pending user-run smoke test",
        "physical_drag_validation": "pending user's manual check",
    }
    (workspace / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(workspace / "result.json")


if __name__ == "__main__":
    main()
