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


def straight(cad):
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Profile",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 2}],
        },
        {"op": "add_constraint", "object": "Profile", "type": "Radius", "args": [0, 2.0]},
        {
            "op": "create_sketch",
            "name": "Path",
            "geometry": [{"type": "line", "start": [0, 0], "end": [0, 30]}],
        },
        {
            "op": "set_placement",
            "object": "Path",
            "position": [0, 0, 0],
            "axis": [1, 0, 0],
            "angle": 90,
        },
    )


@pytest.mark.parametrize("frenet", [True, False])
def test_straight_sweep_native_volume_profile_update_and_undo(cad, frenet):
    straight(cad)
    edit(
        cad,
        {"op": "sweep", "name": "Rod", "profiles": ["Profile"], "path": "Path", "frenet": frenet},
    )
    rod = inspect(cad, "Rod")
    assert rod["type"] == "Part::Sweep" and set(rod["depends_on"]) == {"Profile", "Path"}
    assert rod["shape"]["valid"] and rod["shape"]["solids"] == 1
    assert rod["shape"]["volume_mm3"] == pytest.approx(120 * math.pi)
    edit(cad, {"op": "set_datum", "object": "Profile", "constraint_index": 0, "value": "3 mm"})
    assert inspect(cad, "Rod")["shape"]["volume_mm3"] == pytest.approx(270 * math.pi)
    cad.call("undo_document", document="Model")
    assert inspect(cad, "Rod")["shape"]["volume_mm3"] == pytest.approx(120 * math.pi)


def test_surface_sweep_options_update(cad):
    straight(cad)
    edit(
        cad,
        {
            "op": "sweep",
            "name": "TubeSurface",
            "profiles": ["Profile"],
            "path": "Path",
            "solid": False,
        },
    )
    assert inspect(cad, "TubeSurface")["shape"]["area_mm2"] == pytest.approx(120 * math.pi)
    assert inspect(cad, "TubeSurface")["shape"]["solids"] == 0
    edit(
        cad,
        {
            "op": "set_sweep",
            "object": "TubeSurface",
            "profiles": ["Profile"],
            "path": "Path",
            "solid": True,
            "frenet": True,
            "transition": "round_corner",
        },
    )
    assert inspect(cad, "TubeSurface")["shape"]["volume_mm3"] == pytest.approx(120 * math.pi)


def test_curved_sweep_matches_quarter_torus(cad):
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Profile",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 2}],
        },
        {
            "op": "set_placement",
            "object": "Profile",
            "position": [20, 0, 0],
            "axis": [1, 0, 0],
            "angle": 90,
        },
        {
            "op": "create_sketch",
            "name": "Path",
            "geometry": [
                {
                    "type": "arc",
                    "start": [20, 0],
                    "mid": [20 / math.sqrt(2), 20 / math.sqrt(2)],
                    "end": [0, 20],
                }
            ],
        },
        {"op": "sweep", "name": "Elbow", "profiles": ["Profile"], "path": "Path"},
    )
    assert inspect(cad, "Elbow")["shape"]["volume_mm3"] == pytest.approx(40 * math.pi**2)


def test_closed_spine_sweep_matches_torus(cad):
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Profile",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 2}],
        },
        {
            "op": "set_placement",
            "object": "Profile",
            "position": [20, 0, 0],
            "axis": [1, 0, 0],
            "angle": 90,
        },
        {
            "op": "create_sketch",
            "name": "Path",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 20}],
        },
        {"op": "sweep", "name": "Ring", "profiles": ["Profile"], "path": "Path"},
    )
    assert inspect(cad, "Ring")["shape"]["volume_mm3"] == pytest.approx(160 * math.pi**2)


def test_multiple_sections_sweep_matches_conical_frustum(cad):
    straight(cad)
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "EndProfile",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 4}],
        },
        {"op": "set_placement", "object": "EndProfile", "position": [0, 0, 30]},
        {"op": "sweep", "name": "Taper", "profiles": ["Profile", "EndProfile"], "path": "Path"},
    )
    assert inspect(cad, "Taper")["shape"]["volume_mm3"] == pytest.approx(
        math.pi * 30 * (4 + 8 + 16) / 3
    )


@pytest.mark.parametrize(
    "options",
    [
        {"profiles": []},
        {"profiles": ["Profile", "Profile"]},
        {"path": "Profile"},
        {"path_edges": ["Face1"]},
        {"path_edges": ["Edge1", "Edge1"]},
        {"path_edges": ["Edge99"]},
        {"transition": "unknown"},
        {"frenet": 1},
    ],
)
def test_invalid_sweep_rolls_back_prior_operations(cad, options):
    straight(cad)
    with pytest.raises(CadError):
        edit(
            cad,
            {"op": "set_datum", "object": "Profile", "constraint_index": 0, "value": "3 mm"},
            {"op": "sweep", "name": "Bad", "profiles": ["Profile"], "path": "Path", **options},
        )
    assert len(cad.call("inspect_document", document="Model")["objects"]) == 2
    assert cad.call("inspect_sketch", document="Model", object_name="Profile")["geometry"][0][
        "radius_mm"
    ] == pytest.approx(2)


def test_disconnected_path_edges_are_rejected(cad):
    straight(cad)
    edit(
        cad,
        {
            "op": "add_sketch_geometry",
            "object": "Path",
            "geometry": [{"type": "line", "start": [10, 0], "end": [10, 30]}],
        },
    )
    for selection in ([], ["Edge1", "Edge2"]):
        with pytest.raises(CadError):
            edit(
                cad,
                {
                    "op": "sweep",
                    "name": "Bad",
                    "profiles": ["Profile"],
                    "path": "Path",
                    "path_edges": selection,
                },
            )
    edit(
        cad,
        {
            "op": "sweep",
            "name": "Rod",
            "profiles": ["Profile"],
            "path": "Path",
            "path_edges": ["Edge1"],
        },
    )
    assert inspect(cad, "Rod")["shape"]["volume_mm3"] == pytest.approx(120 * math.pi)


def test_sweep_source_links_survive_save_reopen(cad, tmp_path):
    straight(cad)
    edit(cad, {"op": "sweep", "name": "Rod", "profiles": ["Profile"], "path": "Path"})
    cad.call("save_document", document="Model", path="sweep.FCStd")
    with HeadlessClient(tmp_path, timeout=35) as reopened:
        document = reopened.call("open_document", path="sweep.FCStd")["name"]
        reopened.call(
            "apply_operations",
            document=document,
            operations=[
                {"op": "set_datum", "object": "Profile", "constraint_index": 0, "value": "3 mm"}
            ],
        )
        shape = reopened.call("inspect_object", document=document, object_name="Rod")["shape"]
        assert shape["valid"] and shape["volume_mm3"] == pytest.approx(270 * math.pi)


def test_open_profile_requires_surface_mode(cad):
    straight(cad)
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Line",
            "geometry": [{"type": "line", "start": [0, 0], "end": [5, 0]}],
        },
    )
    with pytest.raises(CadError, match="closed"):
        edit(cad, {"op": "sweep", "name": "Bad", "profiles": ["Line"], "path": "Path"})
    edit(
        cad, {"op": "sweep", "name": "Ribbon", "profiles": ["Line"], "path": "Path", "solid": False}
    )
    assert inspect(cad, "Ribbon")["shape"]["area_mm2"] == pytest.approx(150)


def test_sweep_profile_path_replacement_and_cycle_guard(cad):
    straight(cad)
    edit(cad, {"op": "sweep", "name": "Rod", "profiles": ["Profile"], "path": "Path"})
    with pytest.raises(CadError, match="cycle"):
        edit(cad, {"op": "set_sweep", "object": "Rod", "profiles": ["Rod"], "path": "Path"})
    edit(
        cad,
        {
            "op": "create_sketch",
            "name": "Profile2",
            "geometry": [{"type": "circle", "center": [0, 0], "radius": 3}],
        },
        {
            "op": "create_sketch",
            "name": "Path2",
            "geometry": [{"type": "line", "start": [0, 0], "end": [0, 40]}],
        },
        {
            "op": "set_placement",
            "object": "Path2",
            "position": [0, 0, 0],
            "axis": [1, 0, 0],
            "angle": 90,
        },
        {"op": "set_sweep", "object": "Rod", "profiles": ["Profile2"], "path": "Path2"},
    )
    rod = inspect(cad, "Rod")
    assert set(rod["depends_on"]) == {"Profile2", "Path2"}
    assert rod["shape"]["volume_mm3"] == pytest.approx(360 * math.pi)
