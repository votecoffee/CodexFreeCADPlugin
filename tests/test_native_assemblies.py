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
