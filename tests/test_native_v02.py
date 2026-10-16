import hashlib
import math
import struct

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
    with HeadlessClient(tmp_path, executable, timeout=40) as client:
        client.call("new_document", name="Model")
        client.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Block", "length": 40, "width": 30, "height": 10}
            ],
        )
        yield client


def edit(cad, *operations, **kwargs):
    return cad.call("apply_operations", document="Model", operations=list(operations), **kwargs)


def shape(cad, name):
    return cad.call("inspect_object", document="Model", object_name=name)["shape"]


def test_topology_paging_measurements_and_stable_revisions(cad):
    edges = cad.call("inspect_topology", document="Model", object_name="Block", limit=5)
    assert edges["total"] == 12 and edges["next_offset"] == 5
    assert edges["items"][0]["name"] == "Edge1"
    assert edges["items"][0]["length_mm"] == pytest.approx(10)
    assert edges["items"][0]["curve"] == "Line"
    rest = cad.call("inspect_topology", document="Model", object_name="Block", offset=5)
    assert rest["next_offset"] is None and len(rest["items"]) == 7
    assert rest["revision"] == edges["revision"]
    faces = cad.call("inspect_topology", document="Model", object_name="Block", kind="faces")
    assert len(faces["items"]) == 6
    assert sum(face["area_mm2"] for face in faces["items"]) == pytest.approx(3800)
    assert all(face["surface"] == "Plane" and "normal" in face for face in faces["items"])
    vertices = cad.call("inspect_topology", document="Model", object_name="Block", kind="vertices")
    assert vertices["total"] == 8
    with pytest.raises(CadError):
        cad.call("inspect_topology", document="Model", object_name="Block", limit=1000)


def test_curved_topology_reports_radii(cad):
    edit(
        cad,
        {"op": "create_sphere", "name": "Ball", "radius": 5},
        {"op": "create_cylinder", "name": "Cylinder", "radius": 3, "height": 12},
    )
    faces = cad.call("inspect_topology", document="Model", object_name="Ball", kind="faces")
    assert faces["items"][0]["radius_mm"] == pytest.approx(5)
    edges = cad.call("inspect_topology", document="Model", object_name="Ball")
    assert edges["total"] > 0
    edges = cad.call("inspect_topology", document="Model", object_name="Cylinder")
    rings = [e for e in edges["items"] if e["curve"] == "Circle"]
    assert len(rings) == 2 and all(e["radius_mm"] == pytest.approx(3) for e in rings)


def test_minimum_distance_between_objects_faces_and_vertices(cad):
    edit(
        cad,
        {"op": "create_box", "name": "Other", "length": 40, "width": 30, "height": 10},
        {"op": "set_placement", "object": "Other", "position": [55, 0, 0]},
    )
    result = cad.call("measure_distance", document="Model", object_a="Block", object_b="Other")
    assert result["distance_mm"] == pytest.approx(15)
    assert result["nearest_points_mm"]
    faces_a = cad.call("inspect_topology", document="Model", object_name="Block", kind="faces")
    faces_b = cad.call("inspect_topology", document="Model", object_name="Other", kind="faces")
    face_a = next(f["name"] for f in faces_a["items"] if abs(f["center_mm"][0] - 40) < 1e-8)
    face_b = next(f["name"] for f in faces_b["items"] if abs(f["center_mm"][0] - 55) < 1e-8)
    result = cad.call(
        "measure_distance",
        document="Model",
        object_a="Block",
        object_b="Other",
        subelement_a=face_a,
        subelement_b=face_b,
    )
    assert result["distance_mm"] == pytest.approx(15)
    result = cad.call(
        "measure_distance",
        document="Model",
        object_a="Block",
        object_b="Other",
        subelement_a="Vertex1",
        subelement_b="Vertex1",
    )
    assert result["distance_mm"] == pytest.approx(55)
    with pytest.raises(CadError):
        cad.call(
            "measure_distance",
            document="Model",
            object_a="Block",
            object_b="Other",
            subelement_a="Edge999",
        )


@pytest.mark.parametrize("kind,factor", [("fillet", 1 - math.pi / 4), ("chamfer", 0.5)])
def test_native_edge_feature_radius_edit_undo_and_base_propagation(cad, kind, factor):
    edit(cad, {"op": kind, "name": "Finished", "base": "Block", "edges": ["Edge1"], "size": 2})
    result = cad.call("inspect_object", document="Model", object_name="Finished")
    assert result["type"] == ("Part::Fillet" if kind == "fillet" else "Part::Chamfer")
    assert result["depends_on"] == ["Block"]
    base = cad.call("inspect_object", document="Model", object_name="Block")
    assert base["properties"]["Visibility"]["value"] is False
    assert result["shape"]["volume_mm3"] == pytest.approx(12000 - factor * 4 * 10)
    edit(cad, {"op": "set_edge_treatment", "object": "Finished", "edges": ["Edge1"], "size": 3})
    assert shape(cad, "Finished")["volume_mm3"] == pytest.approx(12000 - factor * 9 * 10)
    cad.call("undo_document", document="Model")
    assert shape(cad, "Finished")["volume_mm3"] == pytest.approx(12000 - factor * 4 * 10)
    edit(cad, {"op": "set_property", "object": "Block", "property": "Height", "value": 15})
    assert shape(cad, "Finished")["volume_mm3"] == pytest.approx(18000 - factor * 4 * 15)


@pytest.mark.parametrize(
    "edges,size", [(["Edge999"], 1), (["Edge1", "Edge1"], 1), (["Face1"], 1), (["Edge1"], 1000)]
)
def test_bad_edge_treatment_rolls_back_entire_batch(cad, edges, size):
    with pytest.raises(CadError):
        edit(
            cad,
            {"op": "set_property", "object": "Block", "property": "Length", "value": 50},
            {"op": "fillet", "name": "Bad", "base": "Block", "edges": edges, "size": size},
        )
    assert shape(cad, "Block")["volume_mm3"] == pytest.approx(12000)
    assert len(cad.call("inspect_document", document="Model")["objects"]) == 1


@pytest.mark.parametrize("extension", ["step", "brep", "stl"])
def test_import_source_preservation_and_undo(cad, tmp_path, extension):
    path = "source part." + extension
    cad.call("export_model", document="Model", objects=["Block"], path=path)
    before = hashlib.sha256((tmp_path / path).read_bytes()).hexdigest()
    cad.call("import_model", document="Model", path=path, name="Imported")
    inspected = cad.call("inspect_object", document="Model", object_name="Imported")
    assert inspected["mesh" if extension == "stl" else "shape"]["volume_mm3"] == pytest.approx(
        12000
    )
    assert hashlib.sha256((tmp_path / path).read_bytes()).hexdigest() == before
    cad.call("undo_document", document="Model")
    assert len(cad.call("inspect_document", document="Model")["objects"]) == 1


def test_placed_mesh_to_solid_then_boolean(cad):
    cad.call("export_model", document="Model", objects=["Block"], path="block.stl")
    cad.call("import_model", document="Model", path="block.stl", name="Mesh")
    revision = cad.call("inspect_document", document="Model")["revision"]
    assert cad.call("inspect_document", document="Model")["revision"] == revision
    edit(
        cad,
        {"op": "set_placement", "object": "Mesh", "position": [60, 2, 3]},
        {"op": "mesh_to_solid", "name": "Solid", "mesh": "Mesh", "tolerance": 0.01},
    )
    converted = shape(cad, "Solid")
    assert converted["valid"] and converted["solids"] == 1
    assert converted["bounds_mm"]["min"] == pytest.approx([60, 2, 3])
    assert converted["bounds_mm"]["max"] == pytest.approx([100, 32, 13])
    edit(
        cad,
        {"op": "create_cylinder", "name": "Drill", "radius": 5, "height": 20},
        {"op": "set_placement", "object": "Drill", "position": [70, 10, 0]},
        {"op": "boolean", "name": "Drilled", "kind": "cut", "base": "Solid", "tool": "Drill"},
    )
    assert shape(cad, "Drilled")["volume_mm3"] == pytest.approx(12000 - math.pi * 25 * 10)


def test_open_mesh_conversion_and_malformed_import_roll_back(cad, tmp_path):
    triangle = struct.pack(
        "<80sI12fH", b"open triangle", 1, 0, 0, 1, 0, 0, 0, 10, 0, 0, 0, 10, 0, 0
    )
    (tmp_path / "open.stl").write_bytes(triangle)
    cad.call("import_model", document="Model", path="open.stl", name="OpenMesh")
    with pytest.raises(CadError, match="closed mesh"):
        edit(cad, {"op": "mesh_to_solid", "name": "BadSolid", "mesh": "OpenMesh"})
    with pytest.raises(CadError, match="BREP"):
        cad.call("inspect_topology", document="Model", object_name="OpenMesh")
    (tmp_path / "invalid.step").write_text("This is not a STEP file")
    with pytest.raises(CadError):
        cad.call("import_model", document="Model", path="invalid.step", name="BadImport")
    assert len(cad.call("inspect_document", document="Model")["objects"]) == 2


def test_import_round_save_and_reopen_retains_native_dependency(cad, tmp_path):
    cad.call("export_model", document="Model", objects=["Block"], path="block.step")
    edit(
        cad,
        {"op": "import_model", "path": "block.step", "name": "Imported"},
        {"op": "fillet", "name": "Round", "base": "Imported", "edges": ["Edge1"], "size": 2},
    )
    original = shape(cad, "Round")["volume_mm3"]
    cad.call("save_document", document="Model", path="round.FCStd")
    with HeadlessClient(tmp_path, timeout=30) as reopened:
        doc = reopened.call("open_document", path="round.FCStd")
        result = reopened.call("inspect_object", document=doc["name"], object_name="Round")
        assert result["type"] == "Part::Fillet" and result["depends_on"] == ["Imported"]
        assert result["shape"]["volume_mm3"] == pytest.approx(original)
        result = reopened.call(
            "apply_operations",
            document=doc["name"],
            operations=[
                {"op": "set_edge_treatment", "object": "Round", "edges": ["Edge1"], "size": 3}
            ],
        )
        rounded = next(o for o in result["document"]["objects"] if o["name"] == "Round")
        assert rounded["shape"]["valid"] and rounded["shape"]["volume_mm3"] < original


def test_import_path_guard_and_stale_revision(cad):
    revision = cad.call("inspect_document", document="Model")["revision"]
    cad.call("export_model", document="Model", objects=["Block"], path="block.step")
    edit(cad, {"op": "create_sphere", "name": "Ball", "radius": 2})
    with pytest.raises(CadError, match="changed since inspection"):
        cad.call(
            "import_model",
            document="Model",
            path="block.step",
            name="Stale",
            expected_revision=revision,
        )
    with pytest.raises(CadError, match="workspace"):
        cad.call("import_model", document="Model", path="../block.step", name="Outside")
