import asyncio
import json
import sys

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from codex_freecad.client import find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native


def data(result):
    assert not result.is_error, result
    return result.structured_content or json.loads(result.content[0].text)


def test_stdio_mcp_discovery_validation_and_native_edit(tmp_path):
    try:
        find_freecad_cmd()
    except CadError:
        pytest.skip("Native FreeCADCmd is not installed")

    async def run():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "codex_freecad.server", "--mode", "headless", "--workspace", str(tmp_path)],
        )
        async with Client(parameters, read_timeout_seconds=45) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 17
            assert next(t for t in tools if t.name == "inspect_document").annotations.read_only_hint
            assert next(
                t for t in tools if t.name == "apply_operations"
            ).annotations.destructive_hint
            status = data(await client.call_tool("freecad_status", {}))
            assert status["mode"] == "headless"
            await client.call_tool("new_document", {"name": "McpModel"})
            bad = await client.call_tool(
                "apply_operations",
                {
                    "document": "McpModel",
                    "operations": [{"op": "create_sphere", "name": "Bad", "radius": -1}],
                },
            )
            assert bad.is_error
            result = data(
                await client.call_tool(
                    "apply_operations",
                    {
                        "document": "McpModel",
                        "operations": [{"op": "create_sphere", "name": "Sphere", "radius": 5}],
                    },
                )
            )
            assert result["document"]["objects"][0]["shape"]["valid"]
            assert len(data(await client.call_tool("list_documents", {}))) == 1
            topology = data(
                await client.call_tool(
                    "inspect_topology",
                    {"document": "McpModel", "object_name": "Sphere", "kind": "faces"},
                )
            )
            assert topology["items"][0]["radius_mm"] == 5
            await client.call_tool(
                "apply_operations",
                {
                    "document": "McpModel",
                    "operations": [
                        {
                            "op": "create_box",
                            "name": "Block",
                            "length": 40,
                            "width": 30,
                            "height": 10,
                        }
                    ],
                },
            )
            await client.call_tool(
                "export_model", {"document": "McpModel", "objects": ["Block"], "path": "input.step"}
            )
            imported = data(
                await client.call_tool(
                    "import_model",
                    {"document": "McpModel", "path": "input.step", "name": "Imported"},
                )
            )
            revision = imported["document"]["revision"]
            rounded = data(
                await client.call_tool(
                    "apply_operations",
                    {
                        "document": "McpModel",
                        "expected_revision": revision,
                        "operations": [
                            {
                                "op": "fillet",
                                "name": "Round",
                                "base": "Imported",
                                "edges": ["Edge1"],
                                "size": 2,
                            }
                        ],
                    },
                )
            )
            assert rounded["document"]["objects"][-1]["shape"]["valid"]
            distance = data(
                await client.call_tool(
                    "measure_distance",
                    {"document": "McpModel", "object_a": "Imported", "object_b": "Block"},
                )
            )
            assert distance["distance_mm"] == 0
            no_gui = await client.call_tool(
                "set_view", {"document": "McpModel", "orientation": "top"}
            )
            assert no_gui.is_error
            turned = data(
                await client.call_tool(
                    "apply_operations",
                    {
                        "document": "McpModel",
                        "operations": [
                            {
                                "op": "create_sketch",
                                "name": "Profile",
                                "geometry": [
                                    {
                                        "type": "rectangle",
                                        "origin": [5, 0],
                                        "width": 5,
                                        "height": 12,
                                    }
                                ],
                            },
                            {
                                "op": "set_placement",
                                "object": "Profile",
                                "position": [0, 0, 0],
                                "axis": [1, 0, 0],
                                "angle": 90,
                            },
                            {"op": "revolve", "name": "Turned", "source": "Profile"},
                            {
                                "op": "linear_pattern",
                                "name": "Row",
                                "source": "Turned",
                                "count": 2,
                                "step": [30, 0, 0],
                            },
                        ],
                    },
                )
            )
            assert turned["document"]["objects"][-1]["shape"]["solids"] == 2
            sketch = data(
                await client.call_tool(
                    "inspect_sketch", {"document": "McpModel", "object_name": "Profile"}
                )
            )
            assert sketch["fully_constrained"] and len(sketch["constraints"]) == 12
            await client.call_tool("new_document", {"name": "Parametric"})
            parametric = data(
                await client.call_tool(
                    "apply_operations",
                    {
                        "document": "Parametric",
                        "operations": [
                            {
                                "op": "create_parameters",
                                "name": "Design",
                                "parameters": [
                                    {"name": "Height", "type": "length", "value": "20 mm"},
                                ],
                            },
                            {
                                "op": "create_sketch",
                                "name": "Lower",
                                "geometry": [{"type": "circle", "center": [0, 0], "radius": 5}],
                            },
                            {
                                "op": "create_sketch",
                                "name": "Upper",
                                "geometry": [{"type": "circle", "center": [0, 0], "radius": 10}],
                            },
                            {
                                "op": "set_expression",
                                "object": "Upper",
                                "property": "Placement.Base.z",
                                "expression": "Design.Height",
                            },
                            {"op": "loft", "name": "Taper", "profiles": ["Lower", "Upper"]},
                            {
                                "op": "mirror",
                                "name": "Reflected",
                                "source": "Taper",
                                "point": [25, 0, 0],
                            },
                            {
                                "op": "set_loft",
                                "object": "Taper",
                                "profiles": ["Lower", "Upper"],
                                "ruled": True,
                            },
                            {"op": "set_mirror", "object": "Reflected", "point": [30, 0, 0]},
                            {
                                "op": "clear_expression",
                                "object": "Upper",
                                "property": "Placement.Base.z",
                            },
                        ],
                    },
                )
            )
            assert parametric["document"]["objects"][-1]["shape"]["solids"] == 1
            assert parametric["document"]["objects"][-1]["shape"]["valid"]
            await client.call_tool("new_document", {"name": "Swept"})
            swept = data(
                await client.call_tool(
                    "apply_operations",
                    {
                        "document": "Swept",
                        "operations": [
                            {
                                "op": "create_sketch",
                                "name": "Profile",
                                "geometry": [{"type": "circle", "center": [0, 0], "radius": 2}],
                            },
                            {
                                "op": "create_sketch",
                                "name": "Path",
                                "geometry": [{"type": "line", "start": [0, 0], "end": [0, 30]}],
                            },
                            {
                                "op": "set_placement",
                                "object": "Path",
                                "position": [0, 0, 0],
                                "axis": [1, 0, 0],
                                "angle": 90,
                            },
                            {"op": "sweep", "name": "Rod", "profiles": ["Profile"], "path": "Path"},
                            {
                                "op": "set_sweep",
                                "object": "Rod",
                                "profiles": ["Profile"],
                                "path": "Path",
                                "solid": False,
                                "transition": "right_corner",
                            },
                        ],
                    },
                )
            )
            assert swept["document"]["objects"][-1]["shape"]["valid"]
            assert swept["document"]["objects"][-1]["shape"]["solids"] == 0

    asyncio.run(run())
