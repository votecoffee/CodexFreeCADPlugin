import copy
import json
import os
import sys
from types import SimpleNamespace

import pytest

from codex_freecad.engine import CadError, Engine
from codex_freecad.extension_runtime import Registry
from codex_freecad.extension_schema import check_schema, validate


def write_extension(root, *, name="demo", source=None):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": name,
        "version": "1.0.0",
        "api_version": 1,
        "description": "Test extension",
        "ui": False,
        "capabilities": {
            "answer": {
                "kind": "query",
                "description": "Test answer",
                "handler": "answer",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            }
        },
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "__init__.py").write_text(
        source or "def answer(engine, doc, args):\n    return {'value': 1}\n", encoding="utf-8"
    )
    return folder


@pytest.fixture
def installed(tmp_path):
    root = tmp_path / "installed"
    folder = write_extension(root)
    registry = Registry(builtin=root)
    yield registry, folder
    registry.active.close()


def publish(registry):
    previous = registry.active
    candidate = registry.prepare()
    assert candidate is not None
    registry.active = candidate
    previous.close()


def answer(registry):
    return registry.invoke(None, None, "demo.answer", {}, "query")["result"]["value"]


def test_reload_reads_fresh_relative_helpers_even_with_identical_mtime_and_size(installed):
    registry, folder = installed
    (folder / "__init__.py").write_text(
        "from .helper import VALUE\ndef answer(engine, doc, args):\n    return {'value': VALUE}\n"
    )
    helper = folder / "helper.py"
    helper.write_text("VALUE = 11\n")
    publish(registry)
    assert answer(registry) == 11
    previous_namespace = registry.active.modules["demo"].__name__
    stamp = helper.stat()
    helper.write_text("VALUE = 22\n")
    os.utime(helper, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    publish(registry)
    assert answer(registry) == 22
    assert previous_namespace not in sys.modules
    assert registry.prepare() is None


@pytest.mark.parametrize(
    "failure",
    ["syntax", "missing_handler", "bad_schema", "bad_api", "extra_manifest_field", "invalid_json"],
)
def test_failed_reload_keeps_working_generation_and_cleans_staging(installed, failure):
    registry, folder = installed
    previous = registry.active
    old_names = {name for name in sys.modules if name.startswith("_codex_cad_extension_")}
    manifest = json.loads((folder / "manifest.json").read_text())
    if failure == "syntax":
        (folder / "__init__.py").write_text("def invalid(:\n")
    elif failure == "missing_handler":
        (folder / "__init__.py").write_text("VALUE = 2\n")
    elif failure == "bad_schema":
        manifest["capabilities"]["answer"]["parameters"]["$ref"] = "remote schema"
    elif failure == "bad_api":
        manifest["api_version"] = 2
    elif failure == "extra_manifest_field":
        manifest["execute"] = "code"
    if failure == "invalid_json":
        (folder / "manifest.json").write_text("{")
    else:
        (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(CadError):
        registry.prepare()
    assert registry.active is previous
    assert answer(registry) == 1
    assert {name for name in sys.modules if name.startswith("_codex_cad_extension_")} == old_names


def test_catalog_schema_is_copied_and_stale_or_wrong_kind_calls_are_rejected(installed):
    registry, folder = installed
    revision = registry.active.revision
    described = registry.describe("demo.answer")
    described["parameters"]["properties"]["hidden"] = {"type": "string"}
    assert not registry.describe("demo.answer")["parameters"]["properties"]
    with pytest.raises(CadError, match="entry point"):
        registry.invoke(None, None, "demo.answer", {}, "edit")
    with pytest.raises(CadError, match="Unknown installed"):
        registry.describe("../../arbitrary.py")
    (folder / "__init__.py").write_text("def answer(engine, doc, args):\n    return {'value': 2}\n")
    publish(registry)
    with pytest.raises(CadError, match="catalog changed"):
        registry.invoke(None, None, "demo.answer", {}, "query", revision)


def test_new_capability_and_removal_are_catalog_changes(installed):
    registry, folder = installed
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["capabilities"]["another"] = copy.deepcopy(manifest["capabilities"]["answer"])
    (folder / "manifest.json").write_text(json.dumps(manifest))
    publish(registry)
    assert {x["name"] for x in registry.catalog()["capabilities"]} == {
        "demo.answer",
        "demo.another",
    }
    (folder / "manifest.json").unlink()
    publish(registry)
    assert registry.catalog()["capabilities"] == []


def test_candidate_is_atomic_across_multiple_extensions(installed):
    registry, folder = installed
    write_extension(folder.parent, name="broken", source="raise RuntimeError('staging failed')\n")
    with pytest.raises(CadError, match="previous generation retained"):
        registry.prepare()
    assert answer(registry) == 1
    assert len(registry.active.modules) == 1


@pytest.mark.parametrize(
    "schema,value",
    [
        ({"type": "number"}, True),
        ({"type": "integer"}, 2.0),
        ({"type": "number"}, float("inf")),
        ({"type": "string", "pattern": "^[A-Z]+$"}, "lower"),
        ({"type": "array", "items": {"type": "number"}, "minItems": 2}, [1]),
        ({"type": "object", "properties": {}, "additionalProperties": False}, {"unknown": 1}),
        ({"type": "number", "exclusiveMinimum": 0}, 0),
    ],
)
def test_runtime_schema_validation_rejects_malformed_values(schema, value):
    check_schema(schema)
    with pytest.raises(CadError):
        validate(schema, value)


def test_runtime_schema_defaults_nested_arrays_and_strict_fields():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["axis"],
        "properties": {
            "axis": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            "enabled": {"type": "boolean", "default": True},
        },
    }
    check_schema(schema)
    arguments = {"axis": [0, 0, 1]}
    assert validate(schema, arguments) == {"axis": [0, 0, 1], "enabled": True}
    assert "enabled" not in arguments


def test_rejected_update_does_not_change_late_relative_imports(installed):
    registry, folder = installed
    (folder / "__init__.py").write_text(
        "def answer(engine, doc, args):\n    from .helper import VALUE\n    return {'value': VALUE}\n"
    )
    (folder / "helper.py").write_text("VALUE = 31\n")
    publish(registry)
    # The old snapshot has not imported helper yet. A rejected update must not leak new bytes.
    (folder / "helper.py").write_text("VALUE = 99\n")
    (folder / "manifest.json").write_text("{")
    with pytest.raises(CadError):
        registry.prepare()
    assert answer(registry) == 31


@pytest.mark.parametrize("restore_fails", [False, True])
def test_ui_lifecycle_commit_and_rollback_contract_without_a_gui(
    tmp_path, monkeypatch, restore_fails
):
    """Exercise registry publication and stable UI facade with lifecycle doubles only."""
    from codex_freecad import extension_runtime

    root = tmp_path / "installed"
    folder = write_extension(root, name="cad_panel")
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest.update(ui=True, capabilities={})
    (folder / "manifest.json").write_text(json.dumps(manifest))

    def source(version, fail=False):
        return (
            "import sys\ncontext = sys.modules['_extension_ui_test_context']\n"
            + f"VERSION={version}\nFAIL={fail!r}\n"
            + "def show(workspace):\n    return None\n"
            + "def capture_state():\n    return {'workspace':'test', 'selection':'kept'}\n"
            + "def shutdown():\n    context.events.append(('shutdown',VERSION))\n"
            + "def restore_state(state):\n    context.events.append(('restore',VERSION))\n    if FAIL: raise RuntimeError('restore failed')\n    context.restored = state\n    context.version = VERSION\n"
        )

    (folder / "__init__.py").write_text(source(1))
    context = SimpleNamespace(events=[], restored=None, version=1)
    monkeypatch.setitem(sys.modules, "_extension_ui_test_context", context)
    registry = Registry(builtin=root)
    monkeypatch.setitem(
        sys.modules,
        "FreeCADGui",
        SimpleNamespace(Control=SimpleNamespace(activeDialog=lambda: None)),
    )
    monkeypatch.setattr(extension_runtime, "_registry", registry)
    engine = Engine.__new__(Engine)
    engine.app = SimpleNamespace(listDocuments=lambda: {}, getActiveTransaction=lambda: None)
    engine.gui = True
    engine.registry = registry
    before = registry.active
    (folder / "__init__.py").write_text(source(2, restore_fails))
    try:
        if restore_fails:
            with pytest.raises(CadError, match="previous generation restored"):
                engine.reload_extensions()
            assert registry.active is before
            assert context.version == 1
            assert context.events == [
                ("shutdown", 1),
                ("restore", 2),
                ("shutdown", 2),
                ("restore", 1),
            ]
        else:
            result = engine.reload_extensions()
            assert result["panel_rebuilt"] and result["reloaded"]
            assert context.version == 2
            assert before.modules["cad_panel"].__name__ not in sys.modules
        assert context.restored["selection"] == "kept"
    finally:
        registry.active.close()
