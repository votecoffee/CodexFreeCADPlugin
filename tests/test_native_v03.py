import math
from pathlib import Path

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


def rectangle(origin=(0, 0), width=10, height=20):
    return {"type": "rectangle", "origin": list(origin), "width": width, "height": height}


def box(cad):
    edit(cad, {"op": "create_box", "name": "Source", "length": 2, "width": 3, "height": 4})


@pytest.mark.parametrize("origin", [(0, 0), (5, -3)])
def test_rectangle_constraints_pad_and_dimension_edit(cad, origin):
    result = edit(
        cad,
        {"op": "create_body", "name": "Body"},
        {"op": "create_sketch", "name": "Profile", "body": "Body", "geometry": [rectangle(origin)]},
        {"op": "pad", "name": "Pad", "body": "Body", "sketch": "Profile", "length": 5},
    )
    record = result["results"][1]["geometry"][0]
    assert record["geometry_indices"] == [0, 1, 2, 3]
    assert inspect(cad, "Pad")["shape"]["volume_mm3"] == pytest.approx(1000)
    sketch = cad.call("inspect_sketch", document="Model", object_name="Profile")
    assert sketch["fully_constrained"] and len(sketch["constraints"]) == 12
    width = next(c for c in sketch["constraints"] if c["name"] == "Rect0_width")
    assert width["index"] == record["dimension_constraints"]["width"]
    edit(
        cad,
        {
            "op": "set_datum",
            "object": "Profile",
            "constraint_index": width["index"],
            "value": "12 mm",
        },
    )
    assert inspect(cad, "Pad")["shape"]["volume_mm3"] == pytest.approx(1200)
    assert inspect(cad, "Pad")["shape"]["bounds_mm"]["min"] == pytest.approx([*origin, 0])


def test_arc_profile_produces_analytic_half_disk(cad):
    edit(
        cad,
        {"op": "create_body", "name": "Body"},
        {
            "op": "create_sketch",
            "name": "Profile",
            "body": "Body",
            "geometry": [
                {"type": "arc", "start": [10, 0], "mid": [0, 10], "end": [-10, 0]},
                {"type": "line", "start": [-10, 0], "end": [10, 0]},
            ],
        },
        {"op": "pad", "name": "Pad", "body": "Body", "sketch": "Profile", "length": 4},
    )
    result = inspect(cad, "Pad")["shape"]
    assert result["valid"] and result["volume_mm3"] == pytest.approx(200 * math.pi)
    arc = cad.call("inspect_sketch", document="Model", object_name="Profile")["geometry"][0]
    assert arc["type"] == "ArcOfCircle" and arc["radius_mm"] == pytest.approx(10)


def test_add_geometry_preserves_existing_indices_and_rolls_back_bad_arc(cad):
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Profile",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 2}],
        },
    )
    result = edit(
        cad, {"op": "add_sketch_geometry", "object": "Profile", "geometry": [rectangle((20, 20))]}
    )
    assert result["results"][0]["geometry"][0]["geometry_indices"] == [1, 2, 3, 4]
    with pytest.raises(CadError):
        edit(
            cad,
            {
                "op": "add_sketch_geometry",
                "object": "Profile",
                "geometry": [
                    {"type": "line", "start": [40, 40], "end": [50, 40]},
                    {"type": "arc", "start": [0, 0], "mid": [1, 0], "end": [2, 0]},
                ],
            },
        )
    sketch = cad.call("inspect_sketch", document="Model", object_name="Profile")
    assert len(sketch["geometry"]) == 5 and sketch["geometry"][0]["radius_mm"] == 2


def test_construction_rectangle_and_3d_point_validation(cad):
    item = dict(rectangle(), construction=True)
    edit(cad, {"op": "create_sketch", "name": "Reference", "geometry": [item]})
    sketch = cad.call("inspect_sketch", document="Model", object_name="Reference")
    assert sketch["fully_constrained"] and all(g["construction"] for g in sketch["geometry"])
    with pytest.raises(CadError, match="2D"):
        edit(
            cad,
            {
                "op": "create_sketch",
                "name": "Bad",
                "geometry": [{"type": "line", "start": [0, 0, 2], "end": [1, 0, 2]}],
            },
        )
    assert len(cad.call("inspect_document", document="Model")["objects"]) == 1


@pytest.mark.parametrize("angle", [360, 90, -180])
def test_revolution_volume_angle_and_profile_dimension_propagation(cad, angle):
    result = edit(
        cad,
        {"op": "create_sketch", "name": "Profile", "geometry": [rectangle((5, 0), 5, 12)]},
        {
            "op": "set_placement",
            "object": "Profile",
            "position": [0, 0, 0],
            "axis": [1, 0, 0],
            "angle": 90,
        },
        {"op": "revolve", "name": "Turned", "source": "Profile", "angle": angle},
    )
    turned = inspect(cad, "Turned")
    assert turned["type"] == "Part::Revolution" and turned["depends_on"] == ["Profile"]
    expected = math.pi * (100 - 25) * 12 * abs(angle) / 360
    assert turned["shape"]["valid"] and turned["shape"]["volume_mm3"] == pytest.approx(expected)
    index = result["results"][0]["geometry"][0]["dimension_constraints"]["width"]
    edit(cad, {"op": "set_datum", "object": "Profile", "constraint_index": index, "value": "7 mm"})
    assert inspect(cad, "Turned")["shape"]["volume_mm3"] == pytest.approx(
        math.pi * (144 - 25) * 12 * abs(angle) / 360
    )
    edit(cad, {"op": "set_property", "object": "Turned", "property": "Angle", "value": 180})
    assert inspect(cad, "Turned")["shape"]["volume_mm3"] == pytest.approx(math.pi * (144 - 25) * 6)


def test_surface_revolution(cad):
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Line",
            "geometry": [{"type": "line", "start": [10, 0], "end": [10, 12]}],
        },
        {
            "op": "set_placement",
            "object": "Line",
            "position": [0, 0, 0],
            "axis": [1, 0, 0],
            "angle": 90,
        },
        {"op": "revolve", "name": "Surface", "source": "Line", "solid": False},
    )
    shape = inspect(cad, "Surface")["shape"]
    assert shape["valid"] and shape["solids"] == 0
    assert shape["area_mm2"] == pytest.approx(240 * math.pi)


@pytest.mark.parametrize("options", [{"axis": [0, 0, 0]}, {"angle": 0}, {}])
def test_bad_solid_revolution_rolls_back(cad, options):
    with pytest.raises(CadError):
        edit(
            cad,
            {
                "op": "create_sketch",
                "name": "Line",
                "geometry": [{"type": "line", "start": [5, 0], "end": [10, 0]}],
            },
            {"op": "revolve", "name": "Bad", "source": "Line", **options},
        )
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_linear_pattern_rotated_source_geometry_updates_and_placement_resampling(cad):
    box(cad)
    edit(
        cad,
        {
            "op": "set_placement",
            "object": "Source",
            "position": [10, 20, 30],
            "axis": [0, 0, 1],
            "angle": 90,
        },
        {
            "op": "linear_pattern",
            "name": "Pattern",
            "source": "Source",
            "count": 3,
            "step": [5, 0, 0],
        },
    )
    pattern = inspect(cad, "Pattern")
    assert pattern["type"] == "App::Link" and pattern["depends_on"] == ["Source"]
    assert pattern["shape"]["volume_mm3"] == pytest.approx(72) and pattern["shape"]["solids"] == 3
    assert pattern["shape"]["bounds_mm"]["min"] == pytest.approx([7, 20, 30])
    assert pattern["shape"]["bounds_mm"]["max"] == pytest.approx([20, 22, 34])
    assert not any(p.startswith("_") for p in pattern["properties"])
    assert (
        cad.call("inspect_document", document="Model")["revision"]
        == cad.call("inspect_document", document="Model")["revision"]
    )
    edit(cad, {"op": "set_property", "object": "Source", "property": "Height", "value": 6})
    assert inspect(cad, "Pattern")["shape"]["volume_mm3"] == pytest.approx(108)
    edit(cad, {"op": "set_placement", "object": "Source", "position": [20, 0, 0]})
    assert inspect(cad, "Pattern")["shape"]["bounds_mm"]["min"] == pytest.approx([7, 20, 30])
    edit(cad, {"op": "set_linear_pattern", "object": "Pattern", "count": 4, "step": [6, 0, 0]})
    assert inspect(cad, "Pattern")["shape"]["bounds_mm"]["max"] == pytest.approx([40, 3, 6])


def test_linear_pattern_update_undo_and_root_placement(cad):
    box(cad)
    edit(
        cad,
        {
            "op": "linear_pattern",
            "name": "Pattern",
            "source": "Source",
            "count": 3,
            "step": [5, 0, 0],
        },
    )
    edit(cad, {"op": "set_linear_pattern", "object": "Pattern", "count": 5, "step": [6, 0, 0]})
    assert inspect(cad, "Pattern")["shape"]["solids"] == 5
    cad.call("undo_document", document="Model")
    assert inspect(cad, "Pattern")["pattern"]["count"] == 3
    edit(cad, {"op": "set_placement", "object": "Pattern", "position": [0, 0, 50]})
    assert inspect(cad, "Pattern")["shape"]["bounds_mm"]["min"][2] == pytest.approx(50)
    edit(cad, {"op": "set_linear_pattern", "object": "Pattern", "count": 4, "step": [5, 0, 0]})
    assert inspect(cad, "Pattern")["shape"]["bounds_mm"]["min"][2] == pytest.approx(50)


def test_circular_patterns_full_partial_and_negative_spans(cad):
    edit(
        cad,
        {"op": "create_cylinder", "name": "Source", "radius": 2, "height": 8},
        {"op": "set_placement", "object": "Source", "position": [15, 0, 0]},
        {"op": "circular_pattern", "name": "Pattern", "source": "Source", "count": 6},
    )
    pattern = inspect(cad, "Pattern")
    assert pattern["shape"]["solids"] == 6
    assert pattern["shape"]["volume_mm3"] == pytest.approx(6 * math.pi * 4 * 8)
    assert pattern["shape"]["bounds_mm"]["max"] == pytest.approx([17, 15 * math.sqrt(3) / 2 + 2, 8])
    edit(cad, {"op": "set_circular_pattern", "object": "Pattern", "count": 4, "angle": 180})
    result = inspect(cad, "Pattern")
    assert result["shape"]["solids"] == 4 and result["pattern"]["angle_degrees"] == 180
    assert result["shape"]["bounds_mm"]["min"][0] == pytest.approx(-17)
    edit(cad, {"op": "set_circular_pattern", "object": "Pattern", "count": 4, "angle": -360})
    assert inspect(cad, "Pattern")["shape"]["bounds_mm"]["min"] == pytest.approx([-17, -17, 0])


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "linear_pattern", "count": 1, "step": [5, 0, 0]},
        {"op": "linear_pattern", "count": True, "step": [5, 0, 0]},
        {"op": "linear_pattern", "count": 201, "step": [5, 0, 0]},
        {"op": "linear_pattern", "count": 3, "step": [0, 0, 0]},
        {"op": "circular_pattern", "count": 3, "axis": [0, 0, 0]},
        {"op": "circular_pattern", "count": 3, "angle": 0},
    ],
)
def test_invalid_patterns_roll_back_prior_edits(cad, operation):
    box(cad)
    with pytest.raises(CadError):
        edit(
            cad,
            {"op": "set_property", "object": "Source", "property": "Height", "value": 7},
            {**operation, "name": "Bad", "source": "Source"},
        )
    assert inspect(cad, "Source")["shape"]["volume_mm3"] == pytest.approx(24)
    assert len(cad.call("inspect_document", document="Model")["objects"]) == 1


def test_managed_pattern_guards_and_source_dependency(cad):
    box(cad)
    edit(
        cad,
        {
            "op": "linear_pattern",
            "name": "Pattern",
            "source": "Source",
            "count": 3,
            "step": [5, 0, 0],
        },
    )
    for operation in [
        {"op": "set_property", "object": "Pattern", "property": "Scale", "value": 2},
        {"op": "set_circular_pattern", "object": "Pattern", "count": 3},
        {"op": "delete_object", "object": "Source"},
    ]:
        with pytest.raises(CadError):
            edit(cad, operation)
    assert inspect(cad, "Pattern")["shape"]["volume_mm3"] == pytest.approx(72)


def test_pattern_native_dependency_and_updates_survive_save_reopen(cad, tmp_path):
    box(cad)
    edit(
        cad,
        {
            "op": "linear_pattern",
            "name": "Pattern",
            "source": "Source",
            "count": 3,
            "step": [5, 0, 0],
        },
    )
    cad.call("save_document", document="Model", path="pattern.FCStd")
    with HeadlessClient(tmp_path, timeout=30) as reopened:
        document = reopened.call("open_document", path="pattern.FCStd")["name"]
        result = reopened.call("inspect_object", document=document, object_name="Pattern")
        assert result["type"] == "App::Link" and result["pattern"]["count"] == 3
        assert "Proxy" not in result["properties"]
        reopened.call(
            "apply_operations",
            document=document,
            operations=[
                {"op": "set_property", "object": "Source", "property": "Height", "value": 8},
                {"op": "set_linear_pattern", "object": "Pattern", "count": 4, "step": [5, 0, 0]},
            ],
        )
        result = reopened.call("inspect_object", document=document, object_name="Pattern")
        assert result["shape"]["solids"] == 4 and result["shape"]["volume_mm3"] == pytest.approx(
            192
        )


def test_pattern_export_preserves_all_instances(cad):
    box(cad)
    edit(
        cad,
        {
            "op": "linear_pattern",
            "name": "Pattern",
            "source": "Source",
            "count": 3,
            "step": [5, 0, 0],
        },
    )
    for extension in ("step", "brep", "stl"):
        cad.call("export_model", document="Model", objects=["Pattern"], path="array." + extension)
        cad.call(
            "import_model", document="Model", path="array." + extension, name="Copy" + extension
        )
        imported = inspect(cad, "Copy" + extension)
        geometry = imported["mesh" if extension == "stl" else "shape"]
        assert geometry["volume_mm3"] == pytest.approx(72)
        if extension != "stl":
            assert geometry["solids"] == 3


def test_top_level_body_pattern_and_nested_feature_guard(cad):
    edit(
        cad,
        {"op": "create_body", "name": "Body"},
        {
            "op": "create_sketch",
            "name": "Profile",
            "body": "Body",
            "geometry": [rectangle(width=4, height=5)],
        },
        {"op": "pad", "name": "Pad", "body": "Body", "sketch": "Profile", "length": 1},
    )
    with pytest.raises(CadError, match="top-level"):
        edit(
            cad,
            {
                "op": "linear_pattern",
                "name": "Bad",
                "source": "Pad",
                "count": 3,
                "step": [10, 0, 0],
            },
        )
    edit(
        cad,
        {
            "op": "linear_pattern",
            "name": "Pattern",
            "source": "Body",
            "count": 3,
            "step": [10, 0, 0],
        },
    )
    assert inspect(cad, "Pattern")["shape"]["volume_mm3"] == pytest.approx(60)


def test_empty_brep_import_and_empty_export_are_rejected(cad, tmp_path):
    empty = Path(__file__).with_name("fixtures") / "empty_compound.brep"
    (tmp_path / "empty.brep").write_bytes(empty.read_bytes())
    with pytest.raises(CadError, match="empty"):
        cad.call("import_model", document="Model", path="empty.brep", name="Bad")
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Construction",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 5, "construction": True}],
        },
    )
    for extension in ("step", "stl", "brep"):
        with pytest.raises(CadError, match="no exportable geometry"):
            cad.call(
                "export_model", document="Model", objects=["Construction"], path="bad." + extension
            )
        assert not (tmp_path / ("bad." + extension)).exists()
