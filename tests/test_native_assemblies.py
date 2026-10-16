import math

import pytest

from codex_freecad.client import HeadlessClient, find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native


@pytest.fixture
def cad(tmp_path):
    try:
        command = find_freecad_cmd()
    except CadError:
        pytest.skip("Native FreeCADCmd is not installed")
    with HeadlessClient(tmp_path, command, timeout=60) as client:
        client.call("new_document", name="Model")
        yield client


def edit(cad, *operations, **kwargs):
    return cad.call("apply_operations", document="Model", operations=list(operations), **kwargs)


def inspect(cad):
    return cad.call("inspect_assembly", document="Model", assembly="Assembly")


def linkage(cad):
    edit(
        cad,
        {"op": "create_box", "name": "Base", "length": 20, "width": 10, "height": 3},
        {"op": "create_box", "name": "Arm", "length": 30, "width": 4, "height": 3},
        {"op": "create_box", "name": "Tip", "length": 5, "width": 4, "height": 3},
        {"op": "create_assembly", "name": "Assembly"},
        {"op": "add_component", "assembly": "Assembly", "name": "BaseLink", "source": "Base"},
        {"op": "add_component", "assembly": "Assembly", "name": "ArmLink", "source": "Arm"},
        {"op": "add_component", "assembly": "Assembly", "name": "TipLink", "source": "Tip"},
        {
            "op": "ground_component",
            "assembly": "Assembly",
            "name": "Ground",
            "component": "BaseLink",
        },
        {
            "op": "create_joint",
            "assembly": "Assembly",
            "name": "Hinge",
            "kind": "revolute",
            "component_a": "BaseLink",
            "component_b": "ArmLink",
            "frame_a": {"position": [10, 0, 3]},
        },
        {
            "op": "create_joint",
            "assembly": "Assembly",
            "name": "Slide",
            "kind": "slider",
            "component_a": "ArmLink",
            "component_b": "TipLink",
            "frame_a": {"position": [30, 0, 0]},
        },
        {"op": "solve_assembly", "assembly": "Assembly"},
    )


def pose(cad, angle, length):
    return edit(
        cad,
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [
                {"joint": "Hinge", "position": angle},
                {"joint": "Slide", "position": length},
            ],
        },
    )


def test_linked_native_joints_move_and_undo(cad):
    linkage(cad)
    original = inspect(cad)
    pose(cad, 90, 12)
    data = inspect(cad)
    assert [j["position"] for j in data["joints"]] == pytest.approx([90, 12])
    assert data["components"][0]["grounded"]
    assert all(c["connected_to_ground"] for c in data["components"])
    assert data["components"][2]["placement"]["position_mm"] == pytest.approx([10, 30, 15])
    cad.call("undo_document", document="Model")
    assert inspect(cad)["components"] == original["components"]
    assert [j["position"] for j in inspect(cad)["joints"]] == pytest.approx(
        [j["position"] for j in original["joints"]]
    )
    edit(cad, {"op": "set_property", "object": "Arm", "property": "Length", "value": 40})
    linked = cad.call("inspect_object", document="Model", object_name="ArmLink")
    assert linked["shape"]["volume_mm3"] == pytest.approx(40 * 4 * 3)


def test_joint_limit_rejection_and_batch_rollback(cad):
    linkage(cad)
    edit(
        cad,
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Hinge",
            "minimum": -45,
            "maximum": 120,
        },
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Slide",
            "minimum": -5,
            "maximum": 20,
        },
    )
    pose(cad, 45, 10)
    before = inspect(cad)
    with pytest.raises(CadError, match="outside.*limits"):
        pose(cad, 150, 10)
    with pytest.raises(CadError, match="outside.*limits"):
        pose(cad, 30, 25)
    assert inspect(cad)["components"] == before["components"]
    with pytest.raises(CadError):
        edit(
            cad,
            {
                "op": "set_joint_positions",
                "assembly": "Assembly",
                "positions": [{"joint": "Hinge", "position": 80}],
            },
            {"op": "create_sphere", "name": "Bad", "radius": -1},
        )
    assert inspect(cad)["components"] == before["components"]


def test_half_turn_limit_boundary_has_equivalent_signed_angles(cad):
    linkage(cad)
    edit(
        cad,
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Hinge",
            "minimum": 0,
            "maximum": 180,
        },
    )
    pose(cad, 180, 0)
    assert abs(inspect(cad)["joints"][0]["position"]) == pytest.approx(180)
    edit(
        cad,
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Hinge",
            "minimum": -180,
            "maximum": 0,
        },
    )
    pose(cad, -180, 0)
    assert abs(inspect(cad)["joints"][0]["position"]) == pytest.approx(180)


def test_assembly_save_reopen_and_move_without_host_proxies(cad, tmp_path):
    linkage(cad)
    pose(cad, -30, -8)
    cad.call("save_document", document="Model", path="assembly.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd(), timeout=60) as reopened:
        name = reopened.call("open_document", path="assembly.FCStd")["name"]
        saved = reopened.call("inspect_assembly", document=name, assembly="Assembly")
        assert [j["position"] for j in saved["joints"]] == pytest.approx([-30, -8])
        reopened.call(
            "apply_operations",
            document=name,
            operations=[
                {
                    "op": "set_joint_positions",
                    "assembly": "Assembly",
                    "positions": [{"joint": "Hinge", "position": 60}],
                }
            ],
        )
        actual = reopened.call("inspect_assembly", document=name, assembly="Assembly")
        assert actual["joints"][0]["position"] == pytest.approx(60)
        point = actual["components"][2]["placement"]["position_mm"]
        assert point == pytest.approx([25, 15 * math.sqrt(3), -5])


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "set_placement", "object": "ArmLink", "position": [1, 2, 3]},
        {"op": "set_property", "object": "Hinge", "property": "Detach1", "value": False},
        {"op": "set_property", "object": "ArmLink", "property": "LinkTransform", "value": True},
        {
            "op": "set_expression",
            "object": "ArmLink",
            "property": "Placement.Base.x",
            "expression": "2 mm",
        },
        {"op": "create_assembly", "name": "SecondAssembly"},
        {
            "op": "ground_component",
            "assembly": "Assembly",
            "name": "DuplicateGround",
            "component": "BaseLink",
        },
        {
            "op": "create_joint",
            "assembly": "Assembly",
            "name": "BadJoint",
            "kind": "revolute",
            "component_a": "ArmLink",
            "component_b": "ArmLink",
        },
        {
            "op": "create_joint",
            "assembly": "Assembly",
            "name": "BadJoint",
            "kind": "revolute",
            "component_a": "Arm",
            "component_b": "TipLink",
        },
        {
            "op": "create_joint",
            "assembly": "Assembly",
            "name": "BadJoint",
            "kind": "slider",
            "component_a": "ArmLink",
            "component_b": "TipLink",
            "frame_a": {"axis": [0, 0, 0]},
        },
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Hinge",
            "minimum": 40,
            "maximum": 10,
        },
        {"op": "set_joint_limits", "assembly": "Assembly", "joint": "Hinge", "minimum": -360},
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Hinge", "position": 20}, {"joint": "Hinge", "position": 30}],
        },
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Ground", "position": 20}],
        },
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Hinge", "position": float("inf")}],
        },
    ],
)
def test_invalid_assembly_edit_preserves_pose_and_objects(cad, operation):
    linkage(cad)
    pose(cad, 35, 7)
    before = inspect(cad)
    names = [x["name"] for x in cad.call("inspect_document", document="Model")["objects"]]
    with pytest.raises(CadError):
        edit(cad, operation)
    after = inspect(cad)
    assert after["components"] == before["components"]
    assert after["joints"] == before["joints"]
    assert [x["name"] for x in cad.call("inspect_document", document="Model")["objects"]] == names


def test_fixed_child_oblique_axis_reversed_drives_and_turn_wrapping(cad):
    linkage(cad)
    edit(
        cad,
        {"op": "create_cylinder", "name": "Tool", "radius": 2, "height": 8},
        {"op": "add_component", "assembly": "Assembly", "name": "ToolLink", "source": "Tool"},
        {
            "op": "create_joint",
            "assembly": "Assembly",
            "name": "ToolMount",
            "kind": "fixed",
            "component_a": "TipLink",
            "component_b": "ToolLink",
            "frame_a": {"position": [2, 3, 4], "axis": [0, 1, 0], "angle": 90},
            "frame_b": {"position": [0, 0, 2]},
        },
        {"op": "solve_assembly", "assembly": "Assembly"},
    )
    edit(
        cad,
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Slide", "position": 9}, {"joint": "Hinge", "position": 810}],
        },
    )
    result = inspect(cad)
    assert [j["position"] for j in result["joints"][:2]] == pytest.approx([90, 9])
    tool = result["components"][-1]["placement"]
    assert tool["position_mm"] == pytest.approx([7, 30, 16])
    shape = cad.call("inspect_object", document="Model", object_name="ToolLink")["shape"]
    assert shape["valid"] and shape["volume_mm3"] == pytest.approx(32 * math.pi)


def test_limits_can_be_cleared_and_revision_guard_rejects_stale_pose(cad):
    linkage(cad)
    edit(
        cad,
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Hinge",
            "minimum": -10,
            "maximum": 10,
        },
    )
    old = inspect(cad)["revision"]
    edit(cad, {"op": "set_joint_limits", "assembly": "Assembly", "joint": "Hinge"})
    assert inspect(cad)["joints"][0]["limits"] == {"minimum": None, "maximum": None}
    with pytest.raises(CadError, match="changed since inspection"):
        edit(
            cad,
            {
                "op": "set_joint_positions",
                "assembly": "Assembly",
                "positions": [{"joint": "Hinge", "position": 20}],
            },
            expected_revision=old,
        )
    pose(cad, 150, 10)


def test_disconnected_assembly_cannot_be_solved(cad):
    linkage(cad)
    edit(cad, {"op": "add_component", "assembly": "Assembly", "name": "LooseLink", "source": "Arm"})
    with pytest.raises(CadError, match="not connected to ground"):
        edit(cad, {"op": "solve_assembly", "assembly": "Assembly"})
