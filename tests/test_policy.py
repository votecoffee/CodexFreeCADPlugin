import hashlib
import json
import tomllib

import pytest
from pydantic import TypeAdapter, ValidationError

from codex_freecad.engine import CadError, Workspace, number, validate_operation
from codex_freecad.schemas import Edit
from codex_freecad.setup import generate


@pytest.mark.parametrize("path", ["../outside.FCStd", "nested/../../escape.step", "x.py"])
def test_workspace_blocks_escape_and_scripts(tmp_path, path):
    with pytest.raises(CadError):
        Workspace(tmp_path).path(path, {".fcstd", ".step"})


def test_overwrite_requires_opt_in_and_preserves_source_bytes(tmp_path):
    workspace = Workspace(tmp_path)
    original = tmp_path / "part.FCStd"
    original.write_bytes(b"original CAD source\x00\xff")
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    with pytest.raises(CadError, match="File exists"):
        workspace.prepare_write("part.FCStd", {".fcstd"})
    target, backup = workspace.prepare_write("part.FCStd", {".fcstd"}, overwrite=True)
    target.write_bytes(b"new version")
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "12"])
def test_numbers_are_finite_and_typed(value):
    with pytest.raises(CadError):
        number(value)


def test_operation_schema_rejects_unknown_fields_and_negative_dimensions():
    adapter = TypeAdapter(Edit)
    for value in [
        {"op": "execute_python", "code": "arbitrary code"},
        {"op": "create_sphere", "name": "Ball", "radius": -2},
        {"op": "create_body", "name": "Body", "script": "hidden field"},
        {"op": "fillet", "name": "Bad", "base": "Block", "edges": [], "size": 1},
        {"op": "chamfer", "name": "Bad", "base": "Block", "edges": ["Edge1"], "size": -1},
        {"op": "mesh_to_solid", "name": "Bad", "mesh": "Mesh", "tolerance": float("nan")},
        {
            "op": "linear_pattern",
            "name": "Bad",
            "source": "Source",
            "count": True,
            "step": [1, 0, 0],
        },
        {
            "op": "create_sketch",
            "name": "Bad",
            "geometry": [{"type": "rectangle", "origin": [0, 0], "width": -1, "height": 2}],
        },
    ]:
        with pytest.raises(ValidationError):
            adapter.validate_python(value)
    with pytest.raises(CadError):
        validate_operation({"op": "create_body", "name": "Body", "script": "hidden field"})


def test_generated_configuration_has_absolute_local_commands(tmp_path):
    result = generate(tmp_path / "CAD models", tmp_path / "setup")
    config = tomllib.loads((tmp_path / "setup" / "codex-mcp.toml").read_text())
    assert set(config["mcp_servers"]) == {"freecad-live", "freecad-headless"}
    manifest = json.loads((tmp_path / "setup/plugin/.codex-plugin/plugin.json").read_text())
    assert manifest["mcpServers"] == "./.mcp.json"
    assert result["workspace"] == str((tmp_path / "CAD models").resolve())
    start_code = (tmp_path / "setup/StartBridge.FCMacro").read_text()
    assert "importlib.reload" in start_code
    compile(start_code, "StartBridge.FCMacro", "exec")
