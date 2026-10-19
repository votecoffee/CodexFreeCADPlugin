import pytest
import test_native_studies

from codex_freecad.client import HeadlessClient, find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native
cad = test_native_studies.cad


def preview(cad, **arguments):
    return cad.call(
        "run_query",
        document="Model",
        capability="studies.preview_changes",
        arguments={
            "changes": [
                {"object": "Design", "property": "Length", "value": 20},
                {"object": "Box", "property": "Width", "value": 10},
            ],
            "objects": ["Box"],
            **arguments,
        },
    )["result"]


def test_equal_volume_change_reports_added_and_removed_material_and_preserves_source(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    docs = cad.call("list_documents")
    report = preview(cad, density_kg_m3=7800)
    row = report["objects"][0]
    assert row["before"]["volume_mm3"] == pytest.approx(1000)
    assert row["after"]["volume_mm3"] == pytest.approx(1000)
    assert row["delta_volume_mm3"] == pytest.approx(0)
    assert row["added_volume_mm3"] == pytest.approx(500)
    assert row["removed_volume_mm3"] == pytest.approx(500)
    assert row["delta_mass_kg"] == pytest.approx(0)
    assert row["after"]["bounds_mm"]["max"] == pytest.approx([20, 10, 5])
    assert [item["after"] for item in report["parameters"]] == [20, 10]
    assert report["apply_arguments"]["expected_revision"] == before
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert cad.call("list_documents") == docs
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_preview_apply_matches_prediction_is_one_undo_and_survives_reopen(cad, tmp_path):
    report = preview(cad)
    baseline = cad.call("inspect_document", document="Model")["revision"]
    cad.call("apply_operations", **report["apply_arguments"])
    shape = cad.call("inspect_object", document="Model", object_name="Box")["shape"]
    assert shape["bounds_mm"] == report["objects"][0]["after"]["bounds_mm"]
    cad.call("save_document", document="Model", path="PreviewApplied.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd()) as other:
        doc = other.call("open_document", path="PreviewApplied.FCStd")["name"]
        assert (
            other.call("inspect_object", document=doc, object_name="Box")["shape"]["bounds_mm"]
            == shape["bounds_mm"]
        )
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["revision"] == baseline


def test_stale_preview_cannot_be_applied(cad):
    report = preview(cad)
    cad.call(
        "apply_operations",
        document="Model",
        operations=[{"op": "set_property", "object": "Box", "property": "Height", "value": 8}],
    )
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError, match="changed since inspection"):
        cad.call("apply_operations", **report["apply_arguments"])
    assert cad.call("inspect_document", document="Model")["revision"] == before


@pytest.mark.parametrize(
    "arguments",
    [
        {"changes": [{"object": "Box", "property": "Length", "value": 20}]},
        {"changes": [{"object": "Box", "property": "Label", "value": 20}]},
        {"changes": [{"object": "Design", "property": "Count", "value": 2.5}]},
        {
            "changes": [
                {"object": "Design", "property": "Length", "value": 20},
                {"object": "Box", "property": "Height", "value": -1},
            ]
        },
        {
            "changes": [
                {"object": "Design", "property": "Length", "value": 20},
                {"object": "Design", "property": "Length", "value": 30},
            ]
        },
        {"objects": ["Box", "Box"]},
        {"objects": ["Design"]},
        {"changes": []},
        {"changes": [{"object": "Box", "property": "Width", "value": 1000001}]},
    ],
)
def test_failed_preview_preserves_source_undo_and_cleans_hidden_copy(cad, arguments):
    before = cad.call("inspect_document", document="Model")["revision"]
    docs = cad.call("list_documents")
    with pytest.raises(CadError):
        preview(cad, **arguments)
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert cad.call("list_documents") == docs
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_unchanged_geometry_and_multiple_outputs(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[{"op": "create_box", "name": "Other", "length": 2, "width": 2, "height": 2}],
    )
    report = preview(
        cad,
        changes=[{"object": "Box", "property": "Width", "value": 25}],
        objects=["Box", "Other"],
    )
    first, second = report["objects"]
    assert first["added_volume_mm3"] == pytest.approx(250)
    assert first["removed_volume_mm3"] == pytest.approx(0)
    assert second["added_volume_mm3"] == pytest.approx(0)
    assert second["removed_volume_mm3"] == pytest.approx(0)


def test_disjoint_translation_preserves_other_document_and_reports_both_material_volumes(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {
                "op": "create_parameters",
                "name": "Position",
                "parameters": [{"name": "Offset", "type": "length", "value": 0}],
            },
            {
                "op": "set_expression",
                "object": "Box",
                "property": "Placement.Base.x",
                "expression": "Position.Offset",
            },
        ],
    )
    cad.call("new_document", name="OtherActive")
    other = cad.call("inspect_document", document="OtherActive")["revision"]
    before = cad.call("inspect_document", document="Model")["revision"]
    row = preview(cad, changes=[{"object": "Position", "property": "Offset", "value": 30}])[
        "objects"
    ][0]
    assert row["delta_volume_mm3"] == pytest.approx(0)
    assert row["added_volume_mm3"] == pytest.approx(1000)
    assert row["removed_volume_mm3"] == pytest.approx(1000)
    assert row["after"]["bounds_mm"]["min"] == pytest.approx([30, 0, 0])
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert cad.call("inspect_document", document="OtherActive")["revision"] == other


def test_curved_boolean_difference_propagates_through_dependencies(cad):
    import math

    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {"op": "create_cylinder", "name": "Bore", "radius": 1, "height": 5},
            {"op": "set_placement", "object": "Bore", "position": [5, 5, 0]},
            {"op": "boolean", "kind": "cut", "name": "Plate", "base": "Box", "tool": "Bore"},
        ],
    )
    row = preview(
        cad,
        changes=[{"object": "Bore", "property": "Radius", "value": 2}],
        objects=["Plate"],
        density_kg_m3=2700,
    )["objects"][0]
    assert row["removed_volume_mm3"] == pytest.approx(15 * math.pi)
    assert row["added_volume_mm3"] == pytest.approx(0)
    assert row["delta_mass_kg"] == pytest.approx(-15 * math.pi * 2700e-9)
