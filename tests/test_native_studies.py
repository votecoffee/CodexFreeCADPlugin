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
                {
                    "op": "create_parameters",
                    "name": "Design",
                    "parameters": [
                        {"name": "Length", "type": "length", "value": 10},
                        {"name": "Count", "type": "integer", "value": 2},
                    ],
                },
                {"op": "create_box", "name": "Box", "length": 10, "width": 20, "height": 5},
                {
                    "op": "set_expression",
                    "object": "Box",
                    "property": "Length",
                    "expression": "Design.Length",
                },
            ],
        )
        yield client


def arguments(**changes):
    return {
        "object": "Design",
        "property": "Length",
        "values": [10, 20, 30],
        "objects": ["Box"],
        **changes,
    }


def query(cad, **changes):
    return cad.call(
        "run_query",
        document="Model",
        capability="studies.parameter_sweep",
        arguments=arguments(**changes),
    )["result"]


def test_sweep_propagates_expressions_preserves_revision_undo_and_documents(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    docs = cad.call("list_documents")
    result = query(cad, density_kg_m3=7800)
    assert [frame["total_volume_mm3"] for frame in result["frames"]] == pytest.approx(
        [1000, 2000, 3000]
    )
    assert result["frames"][2]["objects"][0]["bounds_mm"]["max"] == pytest.approx([30, 20, 5])
    assert result["frames"][0]["objects"][0]["mass_kg"] == pytest.approx(0.0078)
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert cad.call("list_documents") == docs
    query(cad)
    assert cad.call("inspect_document", document="Model")["revision"] == before
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"values": [10, -2]},
        {"values": [10, 0]},
        {"object": "Box", "property": "Length"},
        {"object": "Box", "property": "Label"},
        {"object": "Design", "property": "Count", "values": [1, 2.5]},
        {"objects": ["Box", "Box"]},
        {"objects": ["Missing"]},
    ],
)
def test_failed_sweep_preserves_source_and_cleans_hidden_document(cad, changes):
    before = cad.call("inspect_document", document="Model")["revision"]
    docs = cad.call("list_documents")
    with pytest.raises(CadError):
        query(cad, **changes)
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert cad.call("list_documents") == docs
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_variants_are_frozen_native_snapshots_reopenable_and_undoable(cad, tmp_path):
    result = cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {
                "op": "extension",
                "capability": "studies.create_variants",
                "arguments": {"name": "Variants", **arguments()},
            }
        ],
    )["results"][0]["result"]
    names = [frame["objects"][0] for frame in result["variants"]]
    for name, volume in zip(names, [1000, 2000, 3000], strict=True):
        assert cad.call("inspect_object", document="Model", object_name=name)["shape"][
            "volume_mm3"
        ] == pytest.approx(volume)
    assert cad.call("inspect_object", document="Model", object_name="Box")["shape"][
        "volume_mm3"
    ] == pytest.approx(1000)
    cad.call("save_document", document="Model", path="Study.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd()) as other:
        reopened = other.call("open_document", path="Study.FCStd")["name"]
        other.call(
            "apply_operations",
            document=reopened,
            operations=[
                {"op": "set_property", "object": "Design", "property": "Length", "value": 40}
            ],
        )
        assert other.call("inspect_object", document=reopened, object_name="Box")["shape"][
            "volume_mm3"
        ] == pytest.approx(4000)
        assert other.call("inspect_object", document=reopened, object_name=names[0])["shape"][
            "volume_mm3"
        ] == pytest.approx(1000)
    cad.call("undo_document", document="Model")
    assert [obj["name"] for obj in cad.call("inspect_document", document="Model")["objects"]] == [
        "Design",
        "Box",
    ]


def test_failed_variant_batch_rolls_back_all_prior_edits(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError):
        cad.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Temporary", "length": 2, "width": 2, "height": 2},
                {
                    "op": "extension",
                    "capability": "studies.create_variants",
                    "arguments": {"name": "Variants", **arguments(values=[10, -10])},
                },
            ],
        )
    assert cad.call("inspect_document", document="Model")["revision"] == before


def test_measured_outputs_require_solids(cad):
    with pytest.raises(CadError, match="BREP shape"):
        query(cad, objects=["Design"])
