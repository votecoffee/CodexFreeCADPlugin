import pytest
from test_native_assemblies import edit, inspect, linkage

from codex_freecad.client import HeadlessClient, find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native


@pytest.fixture
def cad(tmp_path):
    with HeadlessClient(tmp_path, find_freecad_cmd(), timeout=60) as client:
        client.call("new_document", name="Model")
        yield client


def couple(cad, **changes):
    operation = {
        "op": "set_joint_coupling",
        "assembly": "Assembly",
        "joint": "Slide",
        "driver": "Hinge",
        "ratio": 0.1,
        "offset": 2,
    }
    operation.update(changes)
    return edit(cad, operation)


def test_affine_mixed_joint_coupling_forward_inverse_turns_and_undo(cad):
    linkage(cad)
    couple(cad)
    edit(
        cad,
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Hinge", "position": 450}],
        },
    )
    data = inspect(cad)
    assert [x["coordinate"] for x in data["joints"]] == pytest.approx([450, 47])
    assert data["joints"][0]["position"] == pytest.approx(90)
    edit(
        cad,
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Slide", "position": 14}],
        },
    )
    assert [x["coordinate"] for x in inspect(cad)["joints"]] == pytest.approx([120, 14])
    cad.call("undo_document", document="Model")
    assert [x["coordinate"] for x in inspect(cad)["joints"]] == pytest.approx([450, 47])


@pytest.mark.parametrize(
    "changes",
    [
        {"driver": "Slide"},
        {"ratio": 0},
        {"ratio": float("inf")},
        {"driver": "Ground"},
        {"joint": "Ground"},
        {"ratio": 1e-12},
        {"joint": "Hinge", "driver": "Slide"},
    ],
)
def test_invalid_coupling_rolls_back(cad, changes):
    linkage(cad)
    couple(cad)
    before = inspect(cad)
    with pytest.raises(CadError):
        couple(cad, **changes)
    after = inspect(cad)
    assert after["couplings"] == before["couplings"]
    assert after["components"] == before["components"]


def test_conflicting_or_out_of_limit_coupled_pose_is_atomic(cad):
    linkage(cad)
    couple(cad)
    before = inspect(cad)
    with pytest.raises(CadError, match="conflict"):
        edit(
            cad,
            {
                "op": "set_joint_positions",
                "assembly": "Assembly",
                "positions": [
                    {"joint": "Hinge", "position": 30},
                    {"joint": "Slide", "position": 99},
                ],
            },
        )
    edit(
        cad,
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Slide",
            "minimum": 0,
            "maximum": 10,
        },
    )
    with pytest.raises(CadError, match="outside.*limits"):
        edit(
            cad,
            {
                "op": "set_joint_positions",
                "assembly": "Assembly",
                "positions": [{"joint": "Hinge", "position": 100}],
            },
        )
    assert inspect(cad)["components"] == before["components"]


def test_coupling_restore_clear_and_reopened_worker(cad, tmp_path):
    linkage(cad)
    couple(cad, ratio=-0.25, offset=3)
    edit(
        cad,
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Hinge", "position": 720}],
        },
    )
    cad.call("save_document", document="Model", path="Coupled.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd(), timeout=60) as other:
        name = other.call("open_document", path="Coupled.FCStd")["name"]
        data = other.call("inspect_assembly", document=name, assembly="Assembly")
        assert [x["coordinate"] for x in data["joints"]] == pytest.approx([720, -177])
        other.call(
            "apply_operations",
            document=name,
            operations=[
                {
                    "op": "set_joint_positions",
                    "assembly": "Assembly",
                    "positions": [{"joint": "Hinge", "position": 1080}],
                }
            ],
        )
        data = other.call("inspect_assembly", document=name, assembly="Assembly")
        assert [x["coordinate"] for x in data["joints"]] == pytest.approx([1080, -267])
    edit(
        cad,
        {"op": "clear_joint_coupling", "assembly": "Assembly", "joint": "Slide"},
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Hinge", "position": 20}],
        },
    )
    assert inspect(cad)["couplings"] == []
    assert inspect(cad)["joints"][1]["coordinate"] == pytest.approx(-177)
