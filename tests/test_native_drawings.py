import hashlib
import xml.etree.ElementTree as ET

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
        client.call("new_document", name="Model")
        client.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Block", "length": 40, "width": 30, "height": 10}
            ],
        )
        yield client


def operation(capability="create_sheet", **arguments):
    return {"op": "extension", "capability": "drawings." + capability, "arguments": arguments}


def create(cad, **changes):
    return cad.call(
        "apply_operations",
        document="Model",
        operations=[operation(name="Sheet", objects=["Block"], **changes)],
    )


def render(cad, document="Model", page="Sheet"):
    return cad.call(
        "run_query", document=document, capability="drawings.render_svg", arguments={"page": page}
    )["result"]


def test_native_sheet_dimensions_and_svg_are_headless_read_only(cad):
    created = create(cad, title="Plate <script>bad</script>", part_number="P-01", revision="A")
    assert [
        (row["width_mm"], row["height_mm"])
        for row in created["results"][0]["result"]["measurements"]
    ] == [(40, 10), (40, 30), (30, 10)]
    objects = created["document"]["objects"]
    assert len([obj for obj in objects if obj["type"] == "TechDraw::DrawViewPart"]) == 3
    assert len([obj for obj in objects if obj["type"] == "TechDraw::DrawViewDimExtent"]) == 6
    before = created["document"]["revision"]
    result = render(cad)
    assert result["paper_mm"] == [297, 210]
    assert [(row["width_mm"], row["height_mm"]) for row in result["views"]] == [
        (40, 10),
        (40, 30),
        (30, 10),
    ]
    assert result["sha256"] == hashlib.sha256(result["svg"].encode()).hexdigest()
    root = ET.fromstring(result["svg"])
    assert root.attrib["width"] == "297mm"
    assert root.findall(".//{http://www.w3.org/2000/svg}path")
    assert not root.findall(".//{http://www.w3.org/2000/svg}script")
    assert "&lt;script&gt;" in result["svg"]
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert render(cad)["svg"] == result["svg"]
    cad.call("undo_document", document="Model")
    assert [obj["name"] for obj in cad.call("inspect_document", document="Model")["objects"]] == [
        "Block"
    ]


def test_source_edit_refresh_reopen_and_undo(cad, tmp_path):
    create(cad)
    original = render(cad)
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {"op": "set_property", "object": "Block", "property": "Length", "value": 55},
        ],
    )
    with pytest.raises(CadError, match="source changed"):
        render(cad)
    cad.call(
        "apply_operations", document="Model", operations=[operation("refresh_sheet", page="Sheet")]
    )
    updated = render(cad)
    assert updated["views"][0]["width_mm"] == pytest.approx(55)
    assert updated["sha256"] != original["sha256"]
    cad.call("save_document", document="Model", path="Drawing.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd()) as other:
        name = other.call("open_document", path="Drawing.FCStd")["name"]
        assert render(other, name)["views"][0]["width_mm"] == pytest.approx(55)
    cad.call("undo_document", document="Model")
    with pytest.raises(CadError, match="source changed"):
        render(cad)
    cad.call("undo_document", document="Model")
    assert render(cad)["views"][0]["width_mm"] == pytest.approx(40)


@pytest.mark.parametrize(
    "changes",
    [
        {"views": ["front", "front"]},
        {"scale": 100},
        {"paper": "A2"},
    ],
)
def test_invalid_drawing_rolls_back(cad, changes):
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError):
        create(cad, **changes)
    assert cad.call("inspect_document", document="Model")["revision"] == before


def test_one_view_scaled_sheet_and_failed_mixed_batch(cad):
    create(cad, paper="A3", views=["front"], scale=0.5)
    result = render(cad)
    assert result["paper_mm"] == [420, 297] and result["scale"] == 0.5
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError):
        cad.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Temporary", "length": 2, "width": 2, "height": 2},
                operation(name="Bad", objects=["Missing"]),
            ],
        )
    assert cad.call("inspect_document", document="Model")["revision"] == before


def test_curved_boolean_translated_and_link_array_sources(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {"op": "create_cylinder", "name": "Bore", "radius": 4, "height": 10},
            {"op": "set_placement", "object": "Bore", "position": [20, 15, 0]},
            {"op": "boolean", "kind": "cut", "name": "Plate", "base": "Block", "tool": "Bore"},
            {"op": "set_placement", "object": "Plate", "position": [100, -50, 20]},
            {
                "op": "linear_pattern",
                "name": "Row",
                "source": "Plate",
                "count": 2,
                "step": [50, 0, 0],
            },
            operation(name="Sheet", objects=["Row"]),
        ],
    )
    result = render(cad)
    assert [(row["width_mm"], row["height_mm"]) for row in result["views"]] == pytest.approx(
        [(90, 10), (90, 30), (30, 10)]
    )
    root = ET.fromstring(result["svg"])
    ids = [node.get("id") for node in root.iter() if node.get("id")]
    assert len(ids) == len(set(ids))
