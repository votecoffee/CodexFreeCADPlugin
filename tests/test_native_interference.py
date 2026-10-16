import pytest

from codex_freecad.client import HeadlessClient, find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native


@pytest.fixture
def cad(tmp_path):
    with HeadlessClient(tmp_path, find_freecad_cmd(), timeout=60) as client:
        client.call("new_document", name="Model")
        yield client


def edit(cad, *operations):
    return cad.call("apply_operations", document="Model", operations=list(operations))


def box(name):
    return {"op": "create_box", "name": name, "length": 10, "width": 10, "height": 10}


@pytest.mark.parametrize(
    "offset,clearance,category,volume,distance",
    [
        (5, 0, "overlap", 500, 0),
        (10, 0, "contact", 0, 0),
        (12, 3, "insufficient_clearance", 0, 2),
        (12, 0, "clear", 0, 2),
        (12, 2, "clear", 0, 2),
    ],
)
def test_known_brep_intersection_contact_and_clearance(
    cad, offset, clearance, category, volume, distance
):
    edit(
        cad, box("A"), box("B"), {"op": "set_placement", "object": "B", "position": [offset, 0, 0]}
    )
    before = cad.call("inspect_document", document="Model")["revision"]
    result = cad.call(
        "check_interference", document="Model", objects=["A", "B"], clearance=clearance
    )
    assert result["pair_count"] == 1 and result["counts"][category] == 1
    if category != "clear":
        assert result["pairs"][0]["overlap_mm3"] == pytest.approx(volume)
        assert result["pairs"][0]["distance_mm"] == pytest.approx(distance)
    assert cad.call("inspect_document", document="Model")["revision"] == before


def slider(cad):
    edit(
        cad,
        box("A"),
        box("B"),
        {"op": "create_assembly", "name": "Assembly"},
        {"op": "add_component", "assembly": "Assembly", "name": "ALink", "source": "A"},
        {"op": "add_component", "assembly": "Assembly", "name": "BLink", "source": "B"},
        {"op": "ground_component", "assembly": "Assembly", "name": "Ground", "component": "ALink"},
        {
            "op": "create_joint",
            "assembly": "Assembly",
            "name": "Slide",
            "kind": "slider",
            "component_a": "ALink",
            "component_b": "BLink",
            "frame_a": {"axis": [0, 1, 0], "angle": 90},
            "frame_b": {"axis": [0, 1, 0], "angle": 90},
        },
        {
            "op": "set_joint_positions",
            "assembly": "Assembly",
            "positions": [{"joint": "Slide", "position": 20}],
        },
    )


def test_sample_copy_detects_middle_collision_preserves_pose_revision_and_undo(cad):
    slider(cad)
    before = cad.call("inspect_document", document="Model")
    result = cad.call(
        "sample_motion",
        document="Model",
        assembly="Assembly",
        joint="Slide",
        start=-20,
        end=20,
        steps=5,
        objects=["ALink", "BLink"],
    )
    assert [x["counts"]["overlap"] for x in result["frames"]] == [0, 0, 1, 0, 0]
    assert result["overlap_frames"] == 1
    assert len(cad.call("list_documents")) == 1
    assert cad.call("inspect_document", document="Model")["revision"] == before["revision"]
    # Sampling must not consume the preceding real edit's Undo transaction.
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_failed_sample_cleans_clone_and_preserves_source(cad):
    slider(cad)
    edit(
        cad,
        {
            "op": "set_joint_limits",
            "assembly": "Assembly",
            "joint": "Slide",
            "minimum": 0,
            "maximum": 25,
        },
    )
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError, match="outside.*limits"):
        cad.call(
            "sample_motion",
            document="Model",
            assembly="Assembly",
            joint="Slide",
            start=20,
            end=30,
            steps=3,
            objects=["ALink", "BLink"],
        )
    assert len(cad.call("list_documents")) == 1
    assert cad.call("inspect_document", document="Model")["revision"] == before


@pytest.mark.parametrize(
    "params",
    [
        {"objects": ["A", "A"]},
        {"objects": ["A"]},
        {"objects": ["A", "Missing"]},
        {"objects": ["A", "B"], "clearance": -1},
        {"objects": ["A", "B"], "volume_tolerance": float("inf")},
    ],
)
def test_bad_interference_inputs_rejected(cad, params):
    edit(cad, box("A"), box("B"))
    with pytest.raises(CadError):
        cad.call("check_interference", document="Model", **params)
