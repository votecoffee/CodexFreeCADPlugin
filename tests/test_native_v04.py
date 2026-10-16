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


def profiles(cad):
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Lower",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 5}],
        },
        {"op": "add_constraint", "object": "Lower", "type": "Radius", "args": [0, 5.0]},
        {
            "op": "create_sketch",
            "name": "Upper",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 10}],
        },
        {"op": "set_placement", "object": "Upper", "position": [0, 0, 20]},
        {
            "op": "create_sketch",
            "name": "Last",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 8}],
        },
        {"op": "set_placement", "object": "Last", "position": [0, 0, 40]},
    )


def frustum(r1, r2, h):
    return math.pi * h * (r1 * r1 + r1 * r2 + r2 * r2) / 3


@pytest.mark.parametrize("ruled", [False, True])
def test_loft_analytic_volume_native_dependencies_and_datum_update(cad, ruled):
    profiles(cad)
    edit(cad, {"op": "loft", "name": "Transition", "profiles": ["Lower", "Upper"], "ruled": ruled})
    loft = inspect(cad, "Transition")
    assert loft["type"] == "Part::Loft" and set(loft["depends_on"]) == {"Lower", "Upper"}
    assert loft["shape"]["valid"] and loft["shape"]["solids"] == 1
    assert loft["shape"]["volume_mm3"] == pytest.approx(frustum(5, 10, 20))
    edit(cad, {"op": "set_datum", "object": "Lower", "constraint_index": 0, "value": "6 mm"})
    assert inspect(cad, "Transition")["shape"]["volume_mm3"] == pytest.approx(frustum(6, 10, 20))


def test_loft_profile_replacement_ruled_sections_surface_and_undo(cad):
    profiles(cad)
    edit(
        cad,
        {"op": "loft", "name": "Transition", "profiles": ["Lower", "Upper", "Last"], "ruled": True},
    )
    assert inspect(cad, "Transition")["shape"]["volume_mm3"] == pytest.approx(
        frustum(5, 10, 20) + frustum(10, 8, 20)
    )
    edit(cad, {"op": "set_loft", "object": "Transition", "profiles": ["Lower", "Last"]})
    assert inspect(cad, "Transition")["shape"]["volume_mm3"] == pytest.approx(frustum(5, 8, 40))
    edit(
        cad,
        {"op": "set_loft", "object": "Transition", "profiles": ["Lower", "Last"], "solid": False},
    )
    surface = inspect(cad, "Transition")["shape"]
    assert surface["valid"] and surface["solids"] == 0
    assert surface["area_mm2"] == pytest.approx(math.pi * 13 * math.sqrt(40**2 + 3**2))
    cad.call("undo_document", document="Model")
    assert inspect(cad, "Transition")["shape"]["solids"] == 1


def test_open_wire_surface_loft_and_solid_rejection(cad):
    for name, z in [("Lower", 0), ("Upper", 20)]:
        edit(
            cad,
            {
                "op": "create_sketch",
                "name": name,
                "geometry": [{"type": "line", "start": [0, 0], "end": [10, 0]}],
            },
            {"op": "set_placement", "object": name, "position": [0, 0, z]},
        )
    with pytest.raises(CadError, match="closed"):
        edit(cad, {"op": "loft", "name": "Bad", "profiles": ["Lower", "Upper"]})
    edit(cad, {"op": "loft", "name": "Surface", "profiles": ["Lower", "Upper"], "solid": False})
    assert inspect(cad, "Surface")["shape"]["area_mm2"] == pytest.approx(200)


@pytest.mark.parametrize(
    "names", [["Lower"], ["Lower", "Lower"], ["Lower", "Missing"], ["Lower", "Block"]]
)
def test_invalid_loft_profiles_roll_back(cad, names):
    profiles(cad)
    edit(cad, {"op": "create_box", "name": "Block", "length": 2, "width": 3, "height": 4})
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError):
        edit(cad, {"op": "loft", "name": "Bad", "profiles": names}, expected_revision=before)
    assert cad.call("inspect_document", document="Model")["revision"] == before


def test_loft_rejects_dependency_cycle(cad):
    profiles(cad)
    edit(cad, {"op": "loft", "name": "Transition", "profiles": ["Lower", "Upper"]})
    with pytest.raises(CadError):
        edit(cad, expression("Lower", "Placement.Base.x", "Transition.Placement.Base.x + 1 mm"))
    with pytest.raises(CadError, match="cycle"):
        edit(cad, {"op": "set_loft", "object": "Transition", "profiles": ["Lower", "Transition"]})
    assert inspect(cad, "Transition")["shape"]["volume_mm3"] == pytest.approx(frustum(5, 10, 20))


def test_mirror_rotated_source_updates_plane_and_native_undo(cad):
    parameters(cad)
    edit(
        cad,
        {
            "op": "set_placement",
            "object": "Block",
            "position": [30, 20, 30],
            "axis": [0, 0, 1],
            "angle": 90,
        },
        {"op": "mirror", "name": "Reflected", "source": "Block"},
    )
    reflected = inspect(cad, "Reflected")
    assert reflected["type"] == "Part::Mirroring" and reflected["depends_on"] == ["Block"]
    assert reflected["shape"]["volume_mm3"] == pytest.approx(200)
    assert reflected["shape"]["bounds_mm"]["min"] == pytest.approx([-30, 20, 30])
    assert reflected["shape"]["bounds_mm"]["max"] == pytest.approx([-10, 30, 31])
    edit(cad, {"op": "set_mirror", "object": "Reflected", "point": [5, 0, 0], "normal": [1, 0, 0]})
    assert inspect(cad, "Reflected")["shape"]["bounds_mm"]["max"][0] == pytest.approx(0)
    cad.call("undo_document", document="Model")
    assert inspect(cad, "Reflected")["shape"]["bounds_mm"]["max"][0] == pytest.approx(-10)
    edit(cad, {"op": "set_property", "object": "Block", "property": "Height", "value": 3})
    assert inspect(cad, "Reflected")["shape"]["volume_mm3"] == pytest.approx(600)


def test_oblique_mirror_and_zero_normal_rollback(cad):
    parameters(cad)
    edit(cad, {"op": "mirror", "name": "Reflected", "source": "Block", "normal": [1, 1, 0]})
    shape = inspect(cad, "Reflected")["shape"]
    assert shape["bounds_mm"]["min"] == pytest.approx([-20, -10, 0])
    assert shape["bounds_mm"]["max"] == pytest.approx([0, 0, 1])
    with pytest.raises(CadError, match="normal"):
        edit(cad, {"op": "set_mirror", "object": "Reflected", "normal": [0, 0, 0]})
    assert inspect(cad, "Reflected")["shape"]["volume_mm3"] == pytest.approx(200)


def test_loft_and_mirror_dependencies_survive_native_save_reopen(cad, tmp_path):
    profiles(cad)
    edit(
        cad,
        {"op": "loft", "name": "Transition", "profiles": ["Lower", "Upper"]},
        {"op": "mirror", "name": "Reflected", "source": "Transition", "point": [20, 0, 0]},
    )
    cad.call("save_document", document="Model", path="loft.FCStd")
    with HeadlessClient(tmp_path, timeout=30) as reopened:
        document = reopened.call("open_document", path="loft.FCStd")["name"]
        reopened.call(
            "apply_operations",
            document=document,
            operations=[
                {"op": "set_datum", "object": "Lower", "constraint_index": 0, "value": "7 mm"},
            ],
        )
        result = reopened.call("inspect_object", document=document, object_name="Reflected")
        assert result["shape"]["valid"] and result["shape"]["volume_mm3"] == pytest.approx(
            frustum(7, 10, 20)
        )


def test_expression_target_and_missing_binding_guards(cad):
    parameters(cad)
    for prop in ("Label", "Visibility", "Shape", "Placement.Rotation.Angle"):
        with pytest.raises(CadError):
            edit(cad, expression(prop=prop, text="2"))
    with pytest.raises(CadError, match="No expression"):
        edit(cad, {"op": "clear_expression", "object": "Block", "property": "Height"})


def test_expression_driven_placement_requires_clearing(cad):
    parameters(cad)
    edit(cad, expression(prop="Placement.Base.z", text="Design.Thickness"))
    with pytest.raises(CadError, match="Placement has an expression"):
        edit(cad, {"op": "set_placement", "object": "Block", "position": [0, 0, 10]})
    assert inspect(cad, "Block")["shape"]["bounds_mm"]["min"][2] == pytest.approx(4)


def test_nested_loft_profiles_and_mirror_sources_are_rejected(cad):
    profiles(cad)
    edit(
        cad,
        {"op": "create_body", "name": "Body"},
        {
            "op": "create_sketch",
            "name": "Nested",
            "body": "Body",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 2}],
        },
        {"op": "pad", "name": "Pad", "body": "Body", "sketch": "Nested", "length": 4},
    )
    for operation in [
        {"op": "loft", "name": "Bad", "profiles": ["Lower", "Nested"]},
        {"op": "mirror", "name": "Bad", "source": "Pad"},
    ]:
        with pytest.raises(CadError, match="top-level"):
            edit(cad, operation)
    edit(cad, {"op": "mirror", "name": "Reflected", "source": "Body"})
    assert inspect(cad, "Reflected")["shape"]["volume_mm3"] == pytest.approx(16 * math.pi)


def test_multiple_wire_loft_is_rejected(cad):
    profiles(cad)
    edit(
        cad,
        {
            "op": "add_sketch_geometry",
            "object": "Lower",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 2}],
        },
    )
    with pytest.raises(CadError, match="exactly one wire"):
        edit(cad, {"op": "loft", "name": "Bad", "profiles": ["Lower", "Upper"]})


def test_mirror_native_link_array_retains_all_instances(cad):
    parameters(cad)
    edit(
        cad,
        {"op": "linear_pattern", "name": "Row", "source": "Block", "count": 3, "step": [30, 0, 0]},
        {"op": "mirror", "name": "Reflected", "source": "Row", "point": [40, 0, 0]},
    )
    shape = inspect(cad, "Reflected")["shape"]
    assert shape["valid"] and shape["solids"] == 3
    assert shape["volume_mm3"] == pytest.approx(600)
    edit(cad, {"op": "set_property", "object": "Block", "property": "Height", "value": 2})
    assert inspect(cad, "Reflected")["shape"]["volume_mm3"] == pytest.approx(1200)
