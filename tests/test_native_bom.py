import csv
import io

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
    with HeadlessClient(tmp_path, executable) as client:
        client.call("new_document", name="Model")
        client.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Block", "length": 10, "width": 20, "height": 5},
                {
                    "op": "linear_pattern",
                    "name": "Row",
                    "source": "Block",
                    "count": 3,
                    "step": [30, 0, 0],
                },
            ],
        )
        yield client


def edit(cad, capability, document="Model", **arguments):
    return cad.call(
        "apply_operations",
        document=document,
        operations=[{"op": "extension", "capability": "bom." + capability, "arguments": arguments}],
    )


def report(cad, *objects, document="Model"):
    return cad.call(
        "run_query",
        document=document,
        capability="bom.inspect",
        arguments={"objects": list(objects)},
    )["result"]


def test_bom_array_quantity_known_and_unknown_mass_source_preservation(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    unknown = report(cad, "Row")
    assert unknown["quantity"] == 3
    assert unknown["total_mass_kg"] is None
    assert unknown["unknown_density_sources"] == ["Block"]
    assert cad.call("inspect_document", document="Model")["revision"] == before
    edit(
        cad, "set_metadata", object="Row", part_number="P-001", material="Steel", density_kg_m3=7800
    )
    result = report(cad, "Row")
    assert result["rows"][0]["source"] == "Block"
    assert result["rows"][0]["quantity"] == 3
    assert result["rows"][0]["solids_per_item"] == 1
    assert result["rows"][0]["volume_each_mm3"] == pytest.approx(1000)
    assert result["total_volume_mm3"] == pytest.approx(3000)
    assert result["total_mass_kg"] == pytest.approx(0.0234)
    assert list(csv.reader(io.StringIO(result["csv"])))[1][1] == "P-001"
    cad.call("undo_document", document="Model")
    assert report(cad, "Row")["total_mass_kg"] is None


def test_distinct_sources_with_same_labels_and_numbers_are_not_merged(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {"op": "create_box", "name": "Other", "length": 4, "width": 3, "height": 2},
            {"op": "set_property", "object": "Block", "property": "Label", "value": "Same"},
            {"op": "set_property", "object": "Other", "property": "Label", "value": "Same"},
        ],
    )
    for obj in ("Block", "Other"):
        edit(cad, "set_metadata", object=obj, part_number="Duplicate")
    result = report(cad, "Block", "Other")
    assert len(result["rows"]) == 2
    assert result["duplicate_part_numbers"] == ["Duplicate"]
    assert result["total_volume_mm3"] == pytest.approx(1024)


def test_spreadsheet_literal_text_refresh_undo_and_native_reopen(cad, tmp_path):
    edit(cad, "set_metadata", object="Block", description="=1+1", part_number="@danger")
    result = report(cad, "Row")
    assert "'=1+1" in result["csv"] and "'@danger" in result["csv"]
    edit(cad, "create_sheet", name="PartsList", objects=["Row"])
    sheet = cad.call("inspect_object", document="Model", object_name="PartsList")
    assert sheet["type"] == "Spreadsheet::Sheet"
    cad.call("save_document", document="Model", path="BOM.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd()) as other:
        reopened = other.call("open_document", path="BOM.FCStd")["name"]
        cad.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "set_property", "object": "Block", "property": "Length", "value": 25}
            ],
        )
        edit(cad, "refresh_sheet", sheet="PartsList")
        assert report(cad, "Row")["total_volume_mm3"] == pytest.approx(7500)
        cad.call("undo_document", document="Model")
        assert report(cad, "Row")["total_volume_mm3"] == pytest.approx(7500)
        cad.call("undo_document", document="Model")
        assert report(cad, "Row")["total_volume_mm3"] == pytest.approx(3000)
        assert report(other, "Row", document=reopened)["total_volume_mm3"] == pytest.approx(3000)
        edit(other, "refresh_sheet", document=reopened, sheet="PartsList")


def test_root_assembly_counts_component_instances_only(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {"op": "create_assembly", "name": "Assembly"},
            {"op": "add_component", "assembly": "Assembly", "name": "First", "source": "Block"},
            {"op": "add_component", "assembly": "Assembly", "name": "Second", "source": "Block"},
        ],
    )
    result = report(cad, "Assembly")
    assert result["quantity"] == 2 and len(result["rows"]) == 1
    assert result["total_volume_mm3"] == pytest.approx(2000)
    with pytest.raises(CadError, match="repeats"):
        report(cad, "Assembly", "First")


@pytest.mark.parametrize("objects", [["Row", "Row"], ["Missing"]])
def test_invalid_query_preserves_model_and_undo(cad, objects):
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError):
        report(cad, *objects)
    assert cad.call("inspect_document", document="Model")["revision"] == before
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_invalid_sheet_batch_rolls_back_prior_model_edit(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError):
        cad.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Temporary", "length": 1, "width": 1, "height": 1},
                {
                    "op": "extension",
                    "capability": "bom.create_sheet",
                    "arguments": {"name": "Bad", "objects": ["Missing"]},
                },
            ],
        )
    assert cad.call("inspect_document", document="Model")["revision"] == before
