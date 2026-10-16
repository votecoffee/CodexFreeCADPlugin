"""Native geometry/transaction/persistence checks for the reloadable hole and fastener tools."""

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
    with HeadlessClient(tmp_path, command) as client:
        client.call("new_document", name="Hardware")
        yield client


def edit(cad, *operations):
    return cad.call("apply_operations", document="Hardware", operations=list(operations))


def extension(capability, **arguments):
    return {"op": "extension", "capability": capability, "arguments": arguments}


def plate():
    return {"op": "create_box", "name": "Plate", "length": 40, "width": 30, "height": 10}


def shape(cad, name):
    return cad.call("inspect_object", document="Hardware", object_name=name)["shape"]


def drill(**arguments):
    return extension(
        "holes.drill",
        **{
            "name": "Drilled",
            "base": "Plate",
            "diameter": 6,
            "positions": [[10, 15, 10]],
            **arguments,
        },
    )


@pytest.mark.parametrize("mode,depth", [("through", 10), ("blind", 6)])
@pytest.mark.parametrize("style", ["simple", "counterbore", "countersink"])
def test_hole_styles_match_analytic_volume_and_native_parameter_edits(cad, mode, depth, style):
    arguments = {"mode": mode, "style": style}
    if mode == "blind":
        arguments["depth"] = depth
    recess_depth = 2
    removed = math.pi * 3**2 * depth
    if style != "simple":
        arguments["recess_diameter"] = 10
        if style == "counterbore":
            arguments["recess_depth"] = recess_depth
            removed += math.pi * (5**2 - 3**2) * recess_depth
        else:
            removed += math.pi * recess_depth * (5**2 + 5 * 3 + 3**2) / 3
            removed -= math.pi * 3**2 * recess_depth
    edit(cad, plate(), drill(**arguments))
    result = shape(cad, "Drilled")
    assert result["valid"] and result["solids"] == 1
    assert result["volume_mm3"] == pytest.approx(12000 - removed, rel=1e-9)
    edit(
        cad,
        {"op": "set_property", "object": "DrilledParameters", "property": "Diameter", "value": 4},
    )
    assert shape(cad, "Drilled")["volume_mm3"] > result["volume_mm3"]
    cad.call("undo_document", document="Hardware")
    assert shape(cad, "Drilled")["volume_mm3"] == pytest.approx(result["volume_mm3"])


def test_arbitrary_direction_through_hole_and_refresh_after_base_resize(cad):
    edit(cad, plate(), drill(positions=[[40, 15, 5]], direction=[-5, 0, 0], diameter=4))
    assert shape(cad, "Drilled")["volume_mm3"] == pytest.approx(12000 - math.pi * 4 * 40)
    edit(
        cad,
        {"op": "set_property", "object": "Plate", "property": "Length", "value": 60},
        extension("holes.refresh", object="Drilled"),
    )
    assert shape(cad, "Drilled")["volume_mm3"] == pytest.approx(18000 - math.pi * 4 * 60)
    cad.call("undo_document", document="Hardware")
    assert shape(cad, "Drilled")["volume_mm3"] == pytest.approx(12000 - math.pi * 4 * 40)


def test_bolt_circle_save_reopen_recompute_and_undo(cad, tmp_path):
    edit(
        cad,
        {"op": "create_cylinder", "name": "Flange", "radius": 30, "height": 8},
        extension(
            "holes.bolt_circle",
            name="Circle",
            base="Flange",
            diameter=4,
            radius=20,
            count=6,
            center=[0, 0, 8],
        ),
    )
    expected = math.pi * (30**2 - 6 * 2**2) * 8
    assert shape(cad, "Circle")["volume_mm3"] == pytest.approx(expected)
    cad.call("save_document", document="Hardware", path="Hardware.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd()) as other:
        assert other.call("open_document", path="Hardware.FCStd")["name"] == "Hardware"
        assert shape(other, "Circle")["volume_mm3"] == pytest.approx(expected)
        edit(
            other,
            {
                "op": "set_property",
                "object": "CircleParameters",
                "property": "Diameter",
                "value": 6,
            },
        )
        assert shape(other, "Circle")["volume_mm3"] == pytest.approx(math.pi * (900 - 6 * 9) * 8)
        other.call("undo_document", document="Hardware")
        assert shape(other, "Circle")["volume_mm3"] == pytest.approx(expected)


@pytest.mark.parametrize(
    "arguments",
    [
        {"direction": [0, 0, 0]},
        {"mode": "blind"},
        {"depth": 8},
        {
            "mode": "blind",
            "depth": 3,
            "style": "counterbore",
            "recess_diameter": 10,
            "recess_depth": 4,
        },
        {"style": "counterbore", "recess_diameter": 4, "recess_depth": 2},
        {"style": "countersink", "recess_diameter": 10, "countersink_angle": 180},
        {"positions": [[10, 15, 10], [10, 15, 10]]},
        {"positions": [[100, 15, 10]]},
        {
            "positions": [[10, 15, 20]],
            "style": "counterbore",
            "recess_diameter": 10,
            "recess_depth": 2,
        },
        {"diameter": True},
        {"name": "../escape"},
    ],
)
def test_invalid_holes_roll_back_every_object_in_mixed_batch(cad, arguments):
    before = cad.call("inspect_document", document="Hardware")
    with pytest.raises(CadError):
        edit(cad, plate(), drill(**arguments))
    after = cad.call("inspect_document", document="Hardware")
    assert after["objects"] == [] and after["revision"] == before["revision"]
    edit(cad, plate(), drill())
    assert shape(cad, "Drilled")["valid"]


def test_name_collision_and_empty_result_preserve_existing_geometry(cad):
    edit(cad, plate())
    before = cad.call("inspect_document", document="Hardware")["revision"]
    for arguments in ({"name": "Plate"}, {"diameter": 100}):
        with pytest.raises(CadError):
            edit(cad, drill(**arguments))
        assert cad.call("inspect_document", document="Hardware")["revision"] == before
    cad.call("undo_document", document="Hardware")
    assert cad.call("inspect_document", document="Hardware")["objects"] == []
