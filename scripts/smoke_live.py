"""Native live-bridge smoke test in a separate, isolated FreeCAD GUI instance.

No existing FreeCAD process, settings or user document is touched. Outputs go to work/live-smoke.
"""

import argparse
import asyncio
import base64
import json
import math
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from codex_freecad.client import LiveClient, find_freecad_cmd
from codex_freecad.setup import generate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from finish_plate import finish_existing_plate  # noqa: E402
from movable_arm import build as build_movable_arm  # noqa: E402
from movable_arm import positions as arm_positions
from parametric_transition import build as build_transition  # noqa: E402
from parametric_transition import expected_volume as transition_volume
from swept_parts import build as build_swept_parts  # noqa: E402
from swept_parts import expected_volumes as swept_volumes
from turned_flange import build as build_turned_flange  # noqa: E402


def assert_same_assembly_pose(actual, expected):
    for first, second in zip(actual["components"], expected["components"], strict=True):
        assert {k: v for k, v in first.items() if k != "placement"} == {
            k: v for k, v in second.items() if k != "placement"
        }
        a, b = first["placement"], second["placement"]
        assert all(
            math.isclose(x, y, abs_tol=1e-8)
            for x, y in zip(a["position_mm"], b["position_mm"], strict=True)
        )
        qa, qb = a["quaternion"], b["quaternion"]
        assert (
            min(
                sum((x - y) ** 2 for x, y in zip(qa, qb, strict=True)),
                sum((x + y) ** 2 for x, y in zip(qa, qb, strict=True)),
            )
            < 1e-16
        )


def check_http(state, *, token=None, origin=None, body=None, expected=401):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if origin:
        headers["Origin"] = origin
    request = Request(
        f"http://127.0.0.1:{state['port']}/call",
        method="POST",
        data=body or b'{"method":"status","params":{}}',
        headers=headers,
    )
    try:
        build_opener(ProxyHandler({})).open(request, timeout=10)
    except HTTPError as exc:
        assert exc.code == expected, (exc.code, exc.read())
        return
    raise AssertionError("Expected HTTP rejection")


async def mcp_check(workspace):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "codex_freecad.server", "--mode", "live", "--workspace", str(workspace)],
    )
    async with Client(parameters, read_timeout_seconds=30) as client:
        tools = (await client.list_tools()).tools
        assert len(tools) == 18
        viewed = await client.call_tool("set_view", {"document": "LivePlate", "orientation": "top"})
        assert not viewed.is_error, viewed
        topology = await client.call_tool(
            "inspect_topology",
            {"document": "LivePlate", "object_name": "FinishedPlate", "kind": "faces"},
        )
        assert not topology.is_error, topology
        sketch = await client.call_tool(
            "inspect_sketch", {"document": "TurnedDemo", "object_name": "Profile"}
        )
        assert not sketch.is_error, sketch
        edited = await client.call_tool(
            "apply_operations",
            {
                "document": "ParametricDemo",
                "operations": [
                    {
                        "op": "set_property",
                        "object": "Design",
                        "property": "Height",
                        "value": "46 mm",
                    },
                ],
            },
        )
        assert not edited.is_error, edited
        pair = await client.call_tool(
            "inspect_object", {"document": "ParametricDemo", "object_name": "TransitionPair"}
        )
        assert not pair.is_error, pair
        pair_data = pair.structured_content or json.loads(pair.content[0].text)
        assert math.isclose(pair_data["shape"]["volume_mm3"], transition_volume(height=46))
        undone = await client.call_tool("undo_document", {"document": "ParametricDemo"})
        assert not undone.is_error, undone
        sweep_edit = await client.call_tool(
            "apply_operations",
            {
                "document": "SweptDemo",
                "operations": [
                    {
                        "op": "set_sweep",
                        "object": "Coil",
                        "profiles": ["CoilProfile"],
                        "path": "CoilPath",
                        "frenet": True,
                        "transition": "right_corner",
                    },
                ],
            },
        )
        assert not sweep_edit.is_error, sweep_edit
        swept = await client.call_tool(
            "inspect_object", {"document": "SweptDemo", "object_name": "SweptParts"}
        )
        assert not swept.is_error, swept
        swept_data = swept.structured_content or json.loads(swept.content[0].text)
        assert math.isclose(
            swept_data["shape"]["volume_mm3"], sum(swept_volumes().values()), rel_tol=1e-5
        )
        restored = await client.call_tool("undo_document", {"document": "SweptDemo"})
        assert not restored.is_error, restored
        joint_edit = await client.call_tool(
            "apply_operations",
            {
                "document": "MovableArm",
                "operations": [arm_positions(60, 12)],
            },
        )
        assert not joint_edit.is_error, joint_edit
        assembly = await client.call_tool(
            "inspect_assembly", {"document": "MovableArm", "assembly": "ArmAssembly"}
        )
        assert not assembly.is_error, assembly
        joint_data = assembly.structured_content or json.loads(assembly.content[0].text)
        assert all(x["connected_to_ground"] for x in joint_data["components"])
        assert math.isclose(joint_data["joints"][0]["position"], 60)
        assert math.isclose(joint_data["joints"][1]["position"], 12)
        assert not (await client.call_tool("undo_document", {"document": "MovableArm"})).is_error
        result = await client.call_tool(
            "capture_view", {"document": "LivePlate", "width": 800, "height": 600}
        )
        assert not result.is_error, result
        image = next(c for c in result.content if c.type == "image")
        assert base64.b64decode(image.data).startswith(b"\x89PNG")
        await client.call_tool("set_view", {"document": "LivePlate", "orientation": "isometric"})
        return {
            "check": "live MCP discovery, sketch/topology/assembly inspection, parameter/sweep/joint editing and undo, view control and image response",
            "tool_count": len(tools),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("work/live-smoke"))
    args = parser.parse_args()
    output = args.output.resolve() / uuid.uuid4().hex[:8]
    config = generate(output / "models", output / "config")
    workspace = Path(config["workspace"])
    macro = Path(config["start_macro"])
    stop_file = output / "stop.flag"
    restart_file = output / "restart.flag"
    restarted_file = output / "restarted.flag"
    start_code = macro.read_text()
    macro.write_text(
        macro.read_text()
        + (
            "\nfrom PySide import QtCore\n"
            "import FreeCAD as App\nimport FreeCADGui as Gui\n"
            "from pathlib import Path\n"
            f"_start_bridge_source = {start_code!r}\n"
            "def _finish_smoke():\n"
            f"    if Path({str(restart_file)!r}).exists():\n"
            f"        Path({str(restart_file)!r}).unlink()\n"
            "        exec(compile(_start_bridge_source, '<generated-start-macro>', 'exec'), globals())\n"
            f"        Path({str(restarted_file)!r}).touch()\n"
            f"    if Path({str(stop_file)!r}).exists():\n"
            "        _smoke_timer.stop()\n        bridge.stop()\n"
            "        for name in list(App.listDocuments()):\n            App.closeDocument(name)\n"
            "        Gui.getMainWindow().close()\n"
            "_smoke_timer = QtCore.QTimer()\n_smoke_timer.timeout.connect(_finish_smoke)\n"
            "_smoke_timer.start(100)\n"
        ),
        encoding="utf-8",
    )
    executable = Path(find_freecad_cmd()).with_name("FreeCAD.exe")
    startup = None
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    checks = []
    with open(output / "freecad.log", "w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                str(executable),
                "-u",
                str(output / "gui-user.cfg"),
                "-s",
                str(output / "gui-system.cfg"),
                str(macro),
            ],
            stdout=log,
            stderr=log,
            startupinfo=startup,
            cwd=output,
        )
        try:
            state_file = workspace / ".codex-freecad-live.json"
            deadline = time.monotonic() + 45
            while not state_file.exists():
                if process.poll() is not None:
                    raise RuntimeError("FreeCAD GUI exited; inspect " + str(output / "freecad.log"))
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Bridge startup timed out; inspect " + str(output / "freecad.log")
                    )
                time.sleep(0.1)
            state = json.loads(state_file.read_text())
            client = LiveClient(state_file, timeout=30)
            assert client.call("status")["mode"] == "live"
            checks.append("native GUI bridge startup")
            check_http(state)
            check_http(state, token="wrong-token")
            check_http(state, token=state["token"], origin="https://example.com", expected=403)
            check_http(state, token=state["token"], body=b"not json", expected=400)
            checks.append("missing/wrong token, browser origin and malformed JSON rejected")
            client.call("new_document", name="LivePlate")
            operations = json.loads(
                (Path(__file__).parents[1] / "examples/mounting_plate.json").read_text()
            )
            result = client.call("apply_operations", document="LivePlate", operations=operations)
            shape = result["document"]["objects"][-1]["shape"]
            assert shape["valid"] and shape["solids"] == 1
            assert math.isclose(shape["volume_mm3"], 32000 - math.pi * 25 * 8)
            checks.append("live main-thread geometry edit and measurement")
            original_token = state["token"]
            restart_file.touch()
            deadline = time.monotonic() + 20
            while not restarted_file.exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("Bridge reload did not complete")
                time.sleep(0.1)
            assert json.loads(state_file.read_text())["token"] != original_token
            preserved = client.call("inspect_document", document="LivePlate")
            assert preserved["objects"][-1]["shape"]["valid"]
            checks.append(
                "generated start macro reloads code, rotates credentials and preserves open model"
            )
            result = finish_existing_plate(client, "LivePlate")
            shape = next(
                obj["shape"]
                for obj in result["document"]["objects"]
                if obj["name"] == "FinishedPlate"
            )
            expected_volume = (
                32000
                - math.pi * 25 * 8
                - (4 - math.pi) * 9 * 8
                - math.pi * (5 * 0.8**2 + 0.8**3 / 3)
            )
            assert shape["valid"] and math.isclose(shape["volume_mm3"], expected_volume)
            checks.append(
                "topology-selected parametric corner fillets and hole chamfer match analytic volume"
            )
            for orientation in ("top", "bottom", "front", "rear", "left", "right", "isometric"):
                viewed = client.call("set_view", document="LivePlate", orientation=orientation)
                assert viewed["orientation"] == orientation
            checks.append("all seven standard live view orientations")
            assert client.call("get_selection") == []
            captured = client.call("capture_view", document="LivePlate", width=1200, height=900)
            assert base64.b64decode(captured["data"]).startswith(b"\x89PNG")
            checks.append("native viewport PNG capture")
            saved = client.call("save_document", document="LivePlate", path="LivePlate.FCStd")
            exported = client.call(
                "export_model",
                document="LivePlate",
                objects=["FinishedPlate"],
                path="LivePlate.step",
            )
            checks.append("live FCStd save and STEP export")
            imported = client.call(
                "import_model", document="LivePlate", path="LivePlate.step", name="ImportedCopy"
            )
            imported_shape = next(
                o["shape"] for o in imported["document"]["objects"] if o["name"] == "ImportedCopy"
            )
            assert math.isclose(imported_shape["volume_mm3"], expected_volume)
            distance = client.call(
                "measure_distance",
                document="LivePlate",
                object_a="FinishedPlate",
                object_b="ImportedCopy",
            )
            assert math.isclose(distance["distance_mm"], 0, abs_tol=1e-8)
            client.call(
                "apply_operations",
                document="LivePlate",
                operations=[
                    {
                        "op": "set_property",
                        "object": "ImportedCopy",
                        "property": "Visibility",
                        "value": False,
                    }
                ],
            )
            checks.append(
                "live STEP reimport, measured equality of volume and minimum-distance query"
            )
            client.call(
                "export_model", document="LivePlate", objects=["Plate"], path="PlateMesh.stl"
            )
            client.call("import_model", document="LivePlate", path="PlateMesh.stl", name="LiveMesh")
            converted = client.call(
                "apply_operations",
                document="LivePlate",
                operations=[
                    {"op": "set_placement", "object": "LiveMesh", "position": [100, 0, 0]},
                    {"op": "mesh_to_solid", "name": "MeshSolid", "mesh": "LiveMesh"},
                    {
                        "op": "set_property",
                        "object": "MeshSolid",
                        "property": "Visibility",
                        "value": False,
                    },
                ],
            )
            mesh_shape = next(
                o["shape"] for o in converted["document"]["objects"] if o["name"] == "MeshSolid"
            )
            assert mesh_shape["valid"] and math.isclose(mesh_shape["volume_mm3"], 32000)
            assert math.isclose(mesh_shape["bounds_mm"]["min"][0], 100)
            checks.append("live STL import and placed closed-mesh conversion to a valid solid")
            arc_result = client.call(
                "apply_operations",
                document="LivePlate",
                operations=[
                    {"op": "create_body", "name": "ArcBody"},
                    {
                        "op": "create_sketch",
                        "name": "ArcProfile",
                        "body": "ArcBody",
                        "geometry": [
                            {"type": "arc", "start": [10, 0], "mid": [0, 10], "end": [-10, 0]},
                            {"type": "line", "start": [-10, 0], "end": [10, 0]},
                        ],
                    },
                    {
                        "op": "pad",
                        "name": "ArcPad",
                        "body": "ArcBody",
                        "sketch": "ArcProfile",
                        "length": 4,
                    },
                    {
                        "op": "set_property",
                        "object": "ArcBody",
                        "property": "Visibility",
                        "value": False,
                    },
                ],
            )
            arc_shape = next(
                o["shape"] for o in arc_result["document"]["objects"] if o["name"] == "ArcPad"
            )
            assert math.isclose(arc_shape["volume_mm3"], 200 * math.pi)
            checks.append("live three-point arc profile pads to the expected half-disk volume")
            turned = build_turned_flange(client)
            sketch = client.call("inspect_sketch", document="TurnedDemo", object_name="Profile")
            assert sketch["fully_constrained"]
            checks.append(
                "live constrained rectangle, native revolution, circular hole pattern and linked linear row"
            )
            client.call("set_view", document="TurnedDemo", orientation="isometric")
            client.call("capture_view", document="TurnedDemo", width=800, height=600)
            before_display = client.call("inspect_document", document="TurnedDemo")["revision"]
            client.call(
                "export_model", document="TurnedDemo", objects=["FlangeRow"], path="RowMesh.stl"
            )
            client.call(
                "apply_operations",
                document="TurnedDemo",
                expected_revision=before_display,
                operations=[
                    {
                        "op": "set_property",
                        "object": "FlangeRow",
                        "property": "Label",
                        "value": "Verified row",
                    }
                ],
            )
            client.call("undo_document", document="TurnedDemo")
            checks.append("live display/STL meshing leaves pattern revision guards stable")
            client.call(
                "apply_operations",
                document="TurnedDemo",
                operations=[
                    {
                        "op": "set_datum",
                        "object": "Profile",
                        "constraint_index": turned["width_constraint"],
                        "value": "21 mm",
                    }
                ],
            )
            updated = client.call("inspect_object", document="TurnedDemo", object_name="FlangeRow")
            assert math.isclose(
                updated["shape"]["volume_mm3"], 3 * math.pi * ((31**2 - 10**2) * 8 - 6 * 2**2 * 8)
            )
            client.call("undo_document", document="TurnedDemo")
            client.call(
                "apply_operations",
                document="TurnedDemo",
                operations=[{"op": "set_circular_pattern", "object": "BoltHoles", "count": 8}],
            )
            updated = client.call("inspect_object", document="TurnedDemo", object_name="FlangeRow")
            assert math.isclose(
                updated["shape"]["volume_mm3"], 3 * math.pi * ((30**2 - 10**2) * 8 - 8 * 2**2 * 8)
            )
            client.call(
                "apply_operations",
                document="TurnedDemo",
                operations=[
                    {
                        "op": "set_linear_pattern",
                        "object": "FlangeRow",
                        "count": 2,
                        "step": [80, 0, 0],
                    }
                ],
            )
            assert (
                client.call("inspect_object", document="TurnedDemo", object_name="FlangeRow")[
                    "shape"
                ]["solids"]
                == 2
            )
            client.call("undo_document", document="TurnedDemo")
            client.call("undo_document", document="TurnedDemo")
            shape = client.call("inspect_object", document="TurnedDemo", object_name="FlangeRow")[
                "shape"
            ]
            assert math.isclose(shape["volume_mm3"], turned["expected_volume_mm3"])
            checks.append("live source-dimension and pattern-count propagation with native undo")
            saved = client.call(
                "save_document", document="TurnedDemo", path="PatternedFlanges.FCStd"
            )
            exported = client.call(
                "export_model",
                document="TurnedDemo",
                objects=["FlangeRow"],
                path="PatternedFlanges.step",
            )
            imported = client.call(
                "import_model",
                document="TurnedDemo",
                path="PatternedFlanges.step",
                name="ImportedRow",
            )
            row_copy = next(
                o["shape"] for o in imported["document"]["objects"] if o["name"] == "ImportedRow"
            )
            assert row_copy["solids"] == 3 and math.isclose(
                row_copy["volume_mm3"], turned["expected_volume_mm3"]
            )
            client.call(
                "apply_operations",
                document="TurnedDemo",
                operations=[
                    {
                        "op": "set_property",
                        "object": "ImportedRow",
                        "property": "Visibility",
                        "value": False,
                    }
                ],
            )
            checks.append(
                "live STEP export/reimport preserves all three patterned solids and their volume"
            )
            transition = build_transition(client)
            assert client.call("inspect_sketch", document="ParametricDemo", object_name="Lower")[
                "fully_constrained"
            ]
            assert client.call("inspect_sketch", document="ParametricDemo", object_name="Upper")[
                "fully_constrained"
            ]
            checks.append(
                "live named parameters drive fully constrained profile radii, profile elevation, loft and mirror"
            )
            revision = client.call("inspect_document", document="ParametricDemo")["revision"]
            client.call(
                "apply_operations",
                document="ParametricDemo",
                expected_revision=revision,
                operations=[
                    {
                        "op": "set_property",
                        "object": "Design",
                        "property": "Height",
                        "value": "60 mm",
                    },
                ],
            )
            updated = client.call(
                "inspect_object", document="ParametricDemo", object_name="TransitionPair"
            )
            assert math.isclose(updated["shape"]["volume_mm3"], transition_volume(height=60))
            try:
                client.call(
                    "apply_operations",
                    document="ParametricDemo",
                    expected_revision=revision,
                    operations=[
                        {
                            "op": "set_property",
                            "object": "Design",
                            "property": "Height",
                            "value": "70 mm",
                        },
                    ],
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Stale parametric revision was accepted")
            client.call("undo_document", document="ParametricDemo")
            checks.append("live parameter propagation, stale-revision rejection and native undo")
            try:
                client.call(
                    "apply_operations",
                    document="ParametricDemo",
                    operations=[
                        {
                            "op": "set_property",
                            "object": "Design",
                            "property": "Height",
                            "value": "55 mm",
                        },
                        {
                            "op": "set_expression",
                            "object": "Upper",
                            "property": "Placement.Base.z",
                            "expression": "Design.Height + 1 deg",
                        },
                    ],
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Incompatible expression units were accepted")
            shape = client.call(
                "inspect_object", document="ParametricDemo", object_name="TransitionPair"
            )["shape"]
            assert math.isclose(shape["volume_mm3"], transition["expected_volume_mm3"])
            checks.append(
                "live incompatible expression units roll back earlier edits in the same batch"
            )
            client.call(
                "apply_operations",
                document="ParametricDemo",
                operations=[
                    {"op": "clear_expression", "object": "Upper", "property": "Placement.Base.z"},
                    {"op": "set_placement", "object": "Upper", "position": [0, 0, 50]},
                ],
            )
            assert math.isclose(
                client.call(
                    "inspect_object", document="ParametricDemo", object_name="TransitionPair"
                )["shape"]["volume_mm3"],
                transition_volume(height=50),
            )
            client.call("undo_document", document="ParametricDemo")
            client.call(
                "apply_operations",
                document="ParametricDemo",
                operations=[
                    {
                        "op": "set_loft",
                        "object": "Transition",
                        "profiles": ["Lower", "Upper"],
                        "ruled": False,
                    },
                    {"op": "set_mirror", "object": "Reflected", "point": [45, 0, 0]},
                ],
            )
            assert math.isclose(
                client.call(
                    "inspect_object", document="ParametricDemo", object_name="TransitionPair"
                )["shape"]["bounds_mm"]["max"][0],
                110,
            )
            client.call("undo_document", document="ParametricDemo")
            checks.append(
                "live expression removal, direct placement, loft/mirror updates and undo restore dependencies"
            )
            saved = client.call(
                "save_document", document="ParametricDemo", path="MirroredTransitions.FCStd"
            )
            exported = client.call(
                "export_model",
                document="ParametricDemo",
                objects=["TransitionPair"],
                path="MirroredTransitions.step",
            )
            client.call(
                "import_model",
                document="ParametricDemo",
                path="MirroredTransitions.step",
                name="ImportedPair",
            )
            copy = client.call(
                "inspect_object", document="ParametricDemo", object_name="ImportedPair"
            )["shape"]
            assert copy["solids"] == 2 and math.isclose(
                copy["volume_mm3"], transition["expected_volume_mm3"]
            )
            client.call(
                "apply_operations",
                document="ParametricDemo",
                operations=[
                    {
                        "op": "set_property",
                        "object": "ImportedPair",
                        "property": "Visibility",
                        "value": False,
                    },
                ],
            )
            shape = client.call(
                "inspect_object", document="ParametricDemo", object_name="TransitionPair"
            )["shape"]
            checks.append(
                "live loft/mirror STEP export preserves both solids and their analytic volume"
            )
            swept = build_swept_parts(client)
            for name in ("OuterProfile", "InnerProfile", "CoilProfile"):
                assert client.call("inspect_sketch", document="SweptDemo", object_name=name)[
                    "fully_constrained"
                ]
            checks.append(
                "live hollow swept elbow and helical solid match analytic volumes within 1e-5 relative tolerance"
            )
            client.call(
                "apply_operations",
                document="SweptDemo",
                operations=[
                    {
                        "op": "set_property",
                        "object": "Design",
                        "property": "CoilHeight",
                        "value": "50 mm",
                    },
                    {
                        "op": "set_property",
                        "object": "Design",
                        "property": "WireRadius",
                        "value": "2.5 mm",
                    },
                ],
            )
            shape = client.call("inspect_object", document="SweptDemo", object_name="SweptParts")[
                "shape"
            ]
            assert math.isclose(
                shape["volume_mm3"], sum(swept_volumes(height=50, wire=2.5).values()), rel_tol=1e-5
            )
            client.call("undo_document", document="SweptDemo")
            checks.append(
                "live helix height and section radius expressions propagate through sweep/boolean dependencies with undo"
            )
            client.call(
                "apply_operations",
                document="SweptDemo",
                operations=[
                    {
                        "op": "set_sweep",
                        "object": "OuterSweep",
                        "profiles": ["OuterProfile"],
                        "path": "BendPath",
                        "path_edges": ["Edge1"],
                        "frenet": True,
                        "transition": "round_corner",
                    },
                ],
            )
            shape = client.call("inspect_object", document="SweptDemo", object_name="SweptParts")[
                "shape"
            ]
            assert shape["valid"] and shape["solids"] == 2
            assert math.isclose(shape["volume_mm3"], swept["expected_volume_mm3"], rel_tol=1e-5)
            client.call("undo_document", document="SweptDemo")
            checks.append(
                "live topology-selected sweep path and framing/corner updates preserve valid solids"
            )
            try:
                client.call(
                    "apply_operations",
                    document="SweptDemo",
                    operations=[
                        {
                            "op": "set_property",
                            "object": "Design",
                            "property": "WireRadius",
                            "value": "3 mm",
                        },
                        {
                            "op": "set_sweep",
                            "object": "Coil",
                            "profiles": ["CoilProfile"],
                            "path": "CoilPath",
                            "path_edges": ["Edge999"],
                        },
                    ],
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Out-of-range sweep path edge was accepted")
            shape = client.call("inspect_object", document="SweptDemo", object_name="SweptParts")[
                "shape"
            ]
            assert math.isclose(shape["volume_mm3"], swept["expected_volume_mm3"], rel_tol=1e-5)
            checks.append("live invalid sweep path selection rolls back earlier parameter edits")
            saved = client.call("save_document", document="SweptDemo", path="SweptParts.FCStd")
            exported = client.call(
                "export_model", document="SweptDemo", objects=["SweptParts"], path="SweptParts.step"
            )
            client.call(
                "export_model", document="SweptDemo", objects=["SweptParts"], path="SweptParts.brep"
            )
            for extension in ("step", "brep"):
                name = "SweptCopy" + extension
                client.call(
                    "import_model", document="SweptDemo", path="SweptParts." + extension, name=name
                )
                copied = client.call("inspect_object", document="SweptDemo", object_name=name)[
                    "shape"
                ]
                assert copied["valid"] and copied["solids"] == 2
                assert math.isclose(
                    copied["volume_mm3"], swept["expected_volume_mm3"], rel_tol=1e-5
                )
                client.call(
                    "apply_operations",
                    document="SweptDemo",
                    operations=[
                        {
                            "op": "set_property",
                            "object": name,
                            "property": "Visibility",
                            "value": False,
                        },
                    ],
                )
            checks.append("live STEP/BREP roundtrips retain both swept solids and their volumes")
            shape = client.call("inspect_object", document="SweptDemo", object_name="SweptParts")[
                "shape"
            ]
            arm = build_movable_arm(client)
            original_arm = client.call(
                "inspect_assembly", document="MovableArm", assembly="ArmAssembly"
            )
            client.call(
                "apply_operations", document="MovableArm", operations=[arm_positions(60, 12)]
            )
            moved_arm = client.call(
                "inspect_assembly", document="MovableArm", assembly="ArmAssembly"
            )
            assert math.isclose(moved_arm["joints"][0]["position"], 60)
            assert math.isclose(moved_arm["joints"][1]["position"], 12)
            point = moved_arm["components"][2]["placement"]["position_mm"]
            assert all(
                math.isclose(a, b, abs_tol=1e-6)
                for a, b in zip(point, [38, 10 + 23 * math.sqrt(3), 10], strict=True)
            )
            checks.append(
                "live native assembly links, grounding, oblique slider and coordinated revolute motion"
            )
            client.call("undo_document", document="MovableArm")
            assert_same_assembly_pose(
                client.call("inspect_assembly", document="MovableArm", assembly="ArmAssembly"),
                original_arm,
            )
            try:
                client.call(
                    "apply_operations", document="MovableArm", operations=[arm_positions(150, 12)]
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Joint travel limit was ignored")
            assert_same_assembly_pose(
                client.call("inspect_assembly", document="MovableArm", assembly="ArmAssembly"),
                original_arm,
            )
            checks.append(
                "live joint limits reject unreachable poses and Undo restores the full assembly"
            )
            client.call("save_document", document="MovableArm", path="MovableArm.FCStd")
            client.call(
                "export_model",
                document="MovableArm",
                objects=arm["objects"],
                path="MovableArm.step",
            )
            client.call(
                "import_model",
                document="MovableArm",
                path="MovableArm.step",
                name="AssemblySnapshot",
            )
            arm_copy = client.call(
                "inspect_object", document="MovableArm", object_name="AssemblySnapshot"
            )["shape"]
            assert arm_copy["valid"] and arm_copy["solids"] == 3
            assert math.isclose(arm_copy["volume_mm3"], arm["expected_volume_mm3"])
            client.call(
                "apply_operations",
                document="MovableArm",
                operations=[
                    {
                        "op": "set_property",
                        "object": "AssemblySnapshot",
                        "property": "Visibility",
                        "value": False,
                    }
                ],
            )
            checks.append("live assembly FCStd save and three-solid STEP roundtrip")
            mcp_result = asyncio.run(mcp_check(workspace))
            checks.append(mcp_result["check"])
            client.call("set_view", document="SweptDemo", orientation="isometric")
            captured = client.call("capture_view", document="SweptDemo", width=1200, height=900)
            report = {
                "plugin_version": client.call("status")["plugin_version"],
                "tool_count": mcp_result["tool_count"],
                "operation_count": len(client.call("status")["operations"]),
                "sample_name": "SweptParts",
                "expected_volumes_mm3": swept["expected_volumes_mm3"],
                "expected_volume_mm3": swept["expected_volume_mm3"],
                "relative_volume_tolerance": 1e-5,
                "checks": checks,
                "shape": shape,
                "saved": saved,
                "exported": exported,
                "screenshot": captured["path"],
                "freecad_version": client.call("status")["freecad_version"],
            }
            (output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
        finally:
            stop_file.touch()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        if (output / "result.json").exists():
            assert process.returncode == 0, "FreeCAD GUI did not exit cleanly"
            assert not state_file.exists(), "Bridge left a stale credential file"
            report["checks"].append("clean GUI exit and bridge credential cleanup")
            (output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
