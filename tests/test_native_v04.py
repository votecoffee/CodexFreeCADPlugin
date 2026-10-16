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
    with HeadlessClient(tmp_path, command, timeout=40) as client:
        client.call("new_document", name="Model")
        yield client


def edit(cad, *operations, **kwargs):
    return cad.call("apply_operations", document="Model", operations=list(operations), **kwargs)


def inspect(cad, name):
    return cad.call("inspect_object", document="Model", object_name=name)


def parameters(cad):
    edit(
        cad,
        {
            "op": "create_parameters",
            "name": "Design",
            "parameters": [
                {"name": "Thickness", "type": "length", "value": "4 mm"},
                {"name": "Tilt", "type": "angle", "value": "30 deg"},
                {"name": "ScaleFactor", "type": "number", "value": 2.5},
                {"name": "Copies", "type": "integer", "value": 3},
            ],
        },
        {"op": "create_box", "name": "Block", "length": 10, "width": 20, "height": 1},
    )


def expression(obj="Block", prop="Height", text="Design.Thickness * 2"):
    return {"op": "set_expression", "object": obj, "property": prop, "expression": text}


def test_named_parameters_expression_propagation_and_clear(cad):
    parameters(cad)
    edit(cad, expression())
    block = inspect(cad, "Block")
    assert block["shape"]["volume_mm3"] == pytest.approx(1600)
    assert block["expressions"] == [{"property": "Height", "expression": "Design.Thickness * 2"}]
    assert "Design" in block["depends_on"]
    assert inspect(cad, "Design")["properties"]["Thickness"]["type"] == "App::PropertyLength"
    edit(cad, {"op": "set_property", "object": "Design", "property": "Thickness", "value": "6 mm"})
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(2400)
    with pytest.raises(CadError, match="expression"):
        edit(cad, {"op": "set_property", "object": "Block", "property": "Height", "value": 7})
    edit(cad, {"op": "clear_expression", "object": "Block", "property": "Height"})
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(2400)
    assert not inspect(cad, "Block")["expressions"]
    edit(cad, {"op": "set_property", "object": "Block", "property": "Height", "value": 7})
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(1400)


def test_expression_units_local_references_placement_and_undo(cad):
    parameters(cad)
    edit(cad, expression(text="(Length + 2 cm) / 3"))
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(2000)
    edit(cad, expression(prop="Placement.Base.z", text="Design.Thickness + 1 mm"))
    assert inspect(cad, "Block")["shape"]["bounds_mm"]["min"][2] == pytest.approx(5)
    edit(cad, expression(prop="Width", text="pi * 10 mm"))
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(1000 * math.pi)
    cad.call("undo_document", document="Model")
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(2000)


def test_named_and_indexed_sketch_datum_expressions(cad):
    parameters(cad)
    result = edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Profile",
            "geometry": [
                {"type": "rectangle", "origin": [0, 0], "width": 10, "height": 20},
            ],
        },
    )
    index = result["results"][0]["geometry"][0]["dimension_constraints"]["width"]
    edit(cad, expression("Profile", "Constraints.Rect0_width", "Design.Thickness * 3"))
    sketch = cad.call("inspect_sketch", document="Model", object_name="Profile")
    assert sketch["fully_constrained"]
    assert sketch["constraints"][index]["value_native"] == pytest.approx(12)
    with pytest.raises(CadError, match="expression"):
        edit(
            cad,
            {"op": "set_datum", "object": "Profile", "constraint_index": index, "value": "8 mm"},
        )
    edit(cad, expression(prop="Height", text="Profile.Constraints.Rect0_width / 2"))
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(1200)
    edit(cad, {"op": "clear_expression", "object": "Profile", "property": f"Constraints[{index}]"})
    edit(cad, {"op": "set_datum", "object": "Profile", "constraint_index": index, "value": "8 mm"})
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(800)


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os')",
        "Design.__class__",
        "Other#Design.Thickness",
        "<<Design>>.Thickness",
        "Design.Label",
        "open(1)",
        "Design.Thickness; 1 mm",
        "Unknown.Length",
        "1e999 mm",
        "Design.Thickness + 1 deg",
        "Design.Thickness / 0",
        "Width +",
        "Block.Height + 1 mm",
    ],
)
def test_invalid_expressions_roll_back_entire_batch(cad, text):
    parameters(cad)
    with pytest.raises(CadError):
        edit(
            cad,
            {"op": "set_property", "object": "Block", "property": "Width", "value": 25},
            expression(text=text),
        )
    block = inspect(cad, "Block")
    assert block["shape"]["volume_mm3"] == pytest.approx(200)
    assert not block["expressions"]


def test_cross_object_expression_cycle_is_rejected(cad):
    parameters(cad)
    edit(cad, expression())
    with pytest.raises(CadError):
        edit(cad, expression("Design", "Thickness", "Block.Height"))
    assert inspect(cad, "Block")["shape"]["volume_mm3"] == pytest.approx(1600)


@pytest.mark.parametrize(
    "items",
    [
        [{"name": "Label", "type": "length", "value": 2}],
        [{"name": "Size", "type": "length", "value": -2}],
        [{"name": "Count", "type": "integer", "value": True}],
        [{"name": "Length", "type": "length", "value": "2 deg"}],
        [{"name": "Data", "type": "python", "value": "x"}],
        [{"name": "X", "type": "number", "value": 1}] * 2,
    ],
)
def test_invalid_parameters_leave_no_container(cad, items):
    with pytest.raises(CadError):
        edit(cad, {"op": "create_parameters", "name": "Bad", "parameters": items})
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_expression_dependencies_survive_native_save_reopen(cad, tmp_path):
    parameters(cad)
    edit(cad, expression())
    cad.call("save_document", document="Model", path="parameters.FCStd")
    with HeadlessClient(tmp_path, timeout=30) as reopened:
        document = reopened.call("open_document", path="parameters.FCStd")["name"]
        reopened.call(
            "apply_operations",
            document=document,
            operations=[
                {
                    "op": "set_property",
                    "object": "Design",
                    "property": "Thickness",
                    "value": "5 mm",
                },
            ],
        )
        assert reopened.call("inspect_object", document=document, object_name="Block")["shape"][
            "volume_mm3"
        ] == pytest.approx(2000)
