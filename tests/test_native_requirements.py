import copy
import json

import pytest
from test_extensions import write_extension

from codex_freecad.client import HeadlessClient, find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native

RULES = [
    {
        "id": "GapInput",
        "metric": "property",
        "object": "Design",
        "property": "Gap",
        "minimum": 2,
        "maximum": 8,
    },
    {"id": "BaseVolume", "metric": "volume", "object": "Base", "minimum": 999, "maximum": 1001},
    {"id": "BaseMass", "metric": "mass", "object": "Base", "density_kg_m3": 7850, "maximum": 0.01},
    {"id": "Envelope", "metric": "extent", "object": "Moving", "axis": "x", "maximum": 10},
    {
        "id": "WorkingClearance",
        "metric": "clearance",
        "object": "Base",
        "other": "Moving",
        "minimum": 2,
    },
]


def extension(capability, **arguments):
    return {"op": "extension", "capability": "requirements." + capability, "arguments": arguments}


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
                    "parameters": [{"name": "Gap", "type": "length", "value": 5}],
                },
                {"op": "create_box", "name": "Base", "length": 10, "width": 10, "height": 10},
                {"op": "create_box", "name": "Moving", "length": 10, "width": 10, "height": 10},
                {
                    "op": "set_expression",
                    "object": "Moving",
                    "property": "Placement.Base.x",
                    "expression": "10 mm + Design.Gap",
                },
                extension("create_set", name="DesignLimits", rules=RULES),
            ],
        )
        yield client


def evaluate(cad, document="Model", name="DesignLimits"):
    return cad.call(
        "run_query", document=document, capability="requirements.evaluate", arguments={"set": name}
    )["result"]


def set_gap(value):
    return {"op": "set_property", "object": "Design", "property": "Gap", "value": value}


def test_all_measurements_pass_without_changing_source_or_undo(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    report = evaluate(cad)
    assert report["all_passed"] and report["counts"] == {"pass": 5, "fail": 0, "error": 0}
    assert [row["value"] for row in report["rules"]] == pytest.approx([5, 1000, 0.00785, 10, 5])
    assert report["rules"][0]["unit"] == "mm"
    assert report["rules"][-1]["overlap_mm3"] == pytest.approx(0)
    assert cad.call("inspect_document", document="Model")["revision"] == before
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


def test_final_enforcement_rolls_back_whole_batch(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError, match="WorkingClearance"):
        cad.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Temporary", "length": 1, "width": 1, "height": 1},
                set_gap(1),
                extension("enforce", set="DesignLimits"),
            ],
        )
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert evaluate(cad)["all_passed"]
    cad.call(
        "apply_operations",
        document="Model",
        operations=[set_gap(3), extension("enforce", set="DesignLimits")],
    )
    assert evaluate(cad)["rules"][-1]["value"] == pytest.approx(3)
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["revision"] == before


def test_previews_show_rule_regressions_and_generated_apply_enforces_them(cad):
    before = cad.call("inspect_document", document="Model")["revision"]
    docs = cad.call("list_documents")
    report = cad.call(
        "run_query",
        document="Model",
        capability="studies.preview_changes",
        arguments={
            "changes": [{"object": "Design", "property": "Gap", "value": 1}],
            "objects": ["Moving"],
            "requirement_sets": ["DesignLimits"],
        },
    )["result"]
    assert report["requirements"]["before"][0]["all_passed"]
    assert not report["requirements"]["all_passed_after"]
    assert report["requirements"]["after"][0]["counts"] == {"pass": 3, "fail": 2, "error": 0}
    assert report["apply_arguments"]["operations"][-1]["capability"] == "requirements.enforce"
    with pytest.raises(CadError, match="Design requirements not satisfied"):
        cad.call("apply_operations", **report["apply_arguments"])
    assert cad.call("inspect_document", document="Model")["revision"] == before
    assert cad.call("list_documents") == docs


def test_zero_clearance_distinguishes_contact_from_overlap(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            extension(
                "update_set",
                set="DesignLimits",
                rules=[
                    {
                        "id": "NoOverlap",
                        "metric": "clearance",
                        "object": "Base",
                        "other": "Moving",
                        "minimum": 0,
                    }
                ],
            )
        ],
    )
    cad.call("apply_operations", document="Model", operations=[set_gap(0)])
    assert evaluate(cad)["all_passed"]  # Contact at zero requested clearance is allowed.
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            {"op": "clear_expression", "object": "Moving", "property": "Placement.Base.x"},
            {"op": "set_placement", "object": "Moving", "position": [5, 0, 0]},
        ],
    )
    report = evaluate(cad)
    assert not report["all_passed"]
    assert report["rules"][0]["value"] == pytest.approx(0)
    assert report["rules"][0]["overlap_mm3"] == pytest.approx(500)


def test_native_requirements_save_reopen_update_and_undo(cad, tmp_path):
    cad.call("save_document", document="Model", path="Requirements.FCStd")
    with HeadlessClient(tmp_path, find_freecad_cmd()) as other:
        name = other.call("open_document", path="Requirements.FCStd")["name"]
        assert evaluate(other, name)["all_passed"]
        info = other.call("inspect_object", document=name, object_name="DesignLimits")
        assert info["type"] == "App::FeaturePython"
    before = cad.call("inspect_document", document="Model")["revision"]
    updated = copy.deepcopy(RULES)
    updated[0]["minimum"] = 6
    cad.call(
        "apply_operations",
        document="Model",
        operations=[extension("update_set", set="DesignLimits", rules=updated)],
    )
    assert not evaluate(cad)["all_passed"]
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["revision"] == before


@pytest.mark.parametrize(
    "rule",
    [
        {"id": "A", "metric": "mass", "object": "Base", "maximum": 2},
        {"id": "A", "metric": "volume", "object": "Base", "minimum": -1},
        {
            "id": "A",
            "metric": "property",
            "object": "Design",
            "property": "Gap",
            "minimum": 10,
            "maximum": 5,
        },
        {"id": "A", "metric": "extent", "object": "Base", "minimum": 0},
        {"id": "A", "metric": "volume", "object": "Base", "maximum": 2, "property": "Length"},
        {"id": "A", "metric": "volume", "object": "Missing", "maximum": 2},
        {"id": "A", "metric": "clearance", "object": "Base", "other": "Base", "minimum": 0},
    ],
)
def test_invalid_definition_rolls_back_all_prior_edits(cad, rule):
    before = cad.call("inspect_document", document="Model")["revision"]
    with pytest.raises(CadError):
        cad.call(
            "apply_operations",
            document="Model",
            operations=[set_gap(3), extension("create_set", name="BadLimits", rules=[rule])],
        )
    assert cad.call("inspect_document", document="Model")["revision"] == before


def test_unmeasurable_rule_is_error_and_cannot_pass_enforcement(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            extension(
                "update_set",
                set="DesignLimits",
                rules=[
                    {"id": "BadMeasurement", "metric": "volume", "object": "Design", "minimum": 0}
                ],
            )
        ],
    )
    report = evaluate(cad)
    assert not report["all_passed"] and report["counts"]["error"] == 1
    with pytest.raises(CadError, match="BadMeasurement"):
        cad.call(
            "apply_operations",
            document="Model",
            operations=[set_gap(3), extension("enforce", set="DesignLimits")],
        )


def test_explicit_numeric_tolerance(cad):
    cad.call(
        "apply_operations",
        document="Model",
        operations=[
            extension(
                "update_set",
                set="DesignLimits",
                rules=[
                    {
                        "id": "Tolerance",
                        "metric": "volume",
                        "object": "Base",
                        "minimum": 1000.01,
                        "absolute_tolerance": 0.02,
                    }
                ],
            )
        ],
    )
    assert evaluate(cad)["all_passed"]


def test_replacing_native_target_by_same_name_does_not_rebind_saved_requirements(tmp_path):
    # A trusted test extension simulates native GUI deletion/recreation. The public
    # delete operation correctly refuses to delete an object with dependents.
    root = tmp_path / "extensions"
    folder = write_extension(
        root,
        name="native_edit",
        source=(
            "def answer(engine, doc, args):\n"
            "    doc.removeObject('Base')\n"
            "    obj = doc.addObject('Part::Box', 'Base')\n"
            "    obj.Length = obj.Width = obj.Height = 10\n"
            "    return {}\n"
        ),
    )
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["capabilities"]["answer"]["kind"] = "edit"
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with HeadlessClient(tmp_path / "models", find_freecad_cmd(), extension_dirs=[root]) as client:
        client.call("new_document", name="Model")
        client.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Base", "length": 10, "width": 10, "height": 10},
                extension(
                    "create_set",
                    name="DesignLimits",
                    rules=[
                        {
                            "id": "OriginalPart",
                            "metric": "volume",
                            "object": "Base",
                            "maximum": 1001,
                        }
                    ],
                ),
            ],
        )
        baseline_shape = client.call("inspect_object", document="Model", object_name="Base")[
            "shape"
        ]
        baseline_rules = evaluate(client)
        assert baseline_rules["all_passed"]
        client.call(
            "apply_operations",
            document="Model",
            operations=[{"op": "extension", "capability": "native_edit.answer", "arguments": {}}],
        )
        report = evaluate(client)
        assert not report["all_passed"] and report["counts"]["error"] == 1
        assert "source links changed" in report["rules"][0]["error"]
        with pytest.raises(CadError, match="OriginalPart"):
            client.call(
                "apply_operations",
                document="Model",
                operations=[extension("enforce", set="DesignLimits")],
            )
        client.call("undo_document", document="Model")
        # Native deletion Undo may reorder doc.Objects, which changes the
        # conservative document revision; verify restored geometry and links.
        assert (
            client.call("inspect_object", document="Model", object_name="Base")["shape"]
            == baseline_shape
        )
        restored = evaluate(client)
        assert restored["all_passed"]
        assert restored["definition_sha256"] == baseline_rules["definition_sha256"]
