import hashlib
import math
import uuid
from pathlib import Path

import pytest

from codex_freecad.client import HeadlessClient, find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native


@pytest.fixture
def cad(tmp_path):
    try:
        executable = find_freecad_cmd()
    except CadError:
        pytest.skip("Native FreeCADCmd is not installed")
    with HeadlessClient(tmp_path, executable, timeout=30) as client:
        client.call("new_document", name="TestModel")
        yield client


def edit(cad, *operations, **kwargs):
    return cad.call("apply_operations", document="TestModel", operations=list(operations), **kwargs)


def box(name="Block", length=40):
    return {"op": "create_box", "name": name, "length": length, "width": 30, "height": 10}


def test_dimension_edit_recomputes_volume_and_undo(cad):
    edit(cad, box())
    original = cad.call("inspect_document", document="TestModel")
    assert cad.call("inspect_document", document="TestModel")["revision"] == original["revision"]
    result = edit(
        cad,
        {"op": "set_property", "object": "Block", "property": "Length", "value": "50 mm"},
        expected_revision=original["revision"],
    )
    assert result["document"]["objects"][0]["shape"]["volume_mm3"] == pytest.approx(15000)
    undone = cad.call("undo_document", document="TestModel")
    assert undone["objects"][0]["shape"]["volume_mm3"] == pytest.approx(12000)


def test_failed_batch_rolls_back_creation_and_edits(cad):
    edit(cad, box())
    with pytest.raises(CadError):
        edit(
            cad,
            {"op": "set_property", "object": "Block", "property": "Length", "value": 55},
            box("Temporary"),
            {"op": "set_property", "object": "Missing", "property": "Width", "value": 2},
        )
    result = cad.call("inspect_document", document="TestModel")
    assert [obj["name"] for obj in result["objects"]] == ["Block"]
    assert result["objects"][0]["shape"]["volume_mm3"] == pytest.approx(12000)


def test_stale_revision_rejects_mutation(cad):
    before = cad.call("inspect_document", document="TestModel")
    edit(cad, box())
    with pytest.raises(CadError, match="changed since inspection"):
        edit(cad, box("Stale"), expected_revision=before["revision"])
    assert len(cad.call("inspect_document", document="TestModel")["objects"]) == 1


def test_boolean_hole_volume_and_dependency_guard(cad):
    result = edit(
        cad,
        box(),
        {"op": "create_cylinder", "name": "Drill", "radius": 3, "height": 20},
        {"op": "set_placement", "object": "Drill", "position": [10, 10, -5]},
        {"op": "boolean", "name": "Result", "kind": "cut", "base": "Block", "tool": "Drill"},
    )
    shape = result["document"]["objects"][-1]["shape"]
    assert shape["valid"] and shape["solids"] == 1
    assert shape["volume_mm3"] == pytest.approx(12000 - math.pi * 3**2 * 10)
    with pytest.raises(CadError, match="dependents"):
        edit(cad, {"op": "delete_object", "object": "Drill"})


def test_sketch_constraint_datum_pad_and_pocket(cad):
    operations = [
        {"op": "create_body", "name": "Body"},
        {
            "op": "create_sketch",
            "name": "Profile",
            "body": "Body",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 10}],
        },
        {"op": "add_constraint", "object": "Profile", "type": "Radius", "args": [0, 10.0]},
        {"op": "pad", "name": "Pad", "body": "Body", "sketch": "Profile", "length": 12},
        {
            "op": "create_sketch",
            "name": "Hole",
            "body": "Body",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 3}],
        },
        {"op": "set_placement", "object": "Hole", "position": [0, 0, 12]},
        {"op": "pocket", "name": "Pocket", "body": "Body", "sketch": "Hole", "length": 12},
    ]
    edit(cad, *operations)
    result = edit(
        cad, {"op": "set_datum", "object": "Profile", "constraint_index": 0, "value": "15 mm"}
    )
    pocket = next(obj for obj in result["document"]["objects"] if obj["name"] == "Pocket")
    assert pocket["shape"]["volume_mm3"] == pytest.approx(math.pi * (15**2 - 3**2) * 12)
    assert pocket["shape"]["valid"]


def test_save_reopen_export_and_backup(cad, tmp_path):
    edit(cad, box())
    saved = cad.call("save_document", document="TestModel", path="model.FCStd")
    original_hash = saved["sha256"]
    with pytest.raises(CadError, match="File exists"):
        cad.call("save_document", document="TestModel", path="model.FCStd")
    edit(cad, {"op": "set_property", "object": "Block", "property": "Length", "value": 50})
    saved = cad.call("save_document", document="TestModel", path="model.FCStd", overwrite=True)
    assert hashlib.sha256(Path(saved["backup"]).read_bytes()).hexdigest() == original_hash
    for extension in ("step", "stl", "brep"):
        exported = cad.call(
            "export_model", document="TestModel", objects=["Block"], path="model." + extension
        )
        assert exported["bytes"] > 100
    with HeadlessClient(tmp_path, timeout=30) as reopened:
        result = reopened.call("open_document", path="model.FCStd")
        assert result["objects"][0]["shape"]["volume_mm3"] == pytest.approx(15000)


def test_forbidden_property_and_outside_file_leave_model_unchanged(cad):
    edit(cad, box())
    with pytest.raises(CadError):
        edit(
            cad,
            {"op": "set_property", "object": "Block", "property": "Shape", "value": "malicious"},
        )
    with pytest.raises(CadError, match="workspace"):
        cad.call("save_document", document="TestModel", path="../" + uuid.uuid4().hex + ".FCStd")
    assert cad.call("inspect_document", document="TestModel")["objects"][0]["shape"][
        "volume_mm3"
    ] == pytest.approx(12000)
