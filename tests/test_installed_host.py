import json
import sys

import pytest

from codex_freecad.framework_setup import publish
from codex_freecad.installed_host import selected_host, upgrade_plan


def test_unselected_installation_remains_direct_without_creating_files(tmp_path):
    output = tmp_path / "not-created"
    assert selected_host(output) is None
    assert not output.exists()


def test_selected_installation_preserves_binding_and_refuses_missing_runtime(tmp_path):
    output = tmp_path / "installation"
    root = output / "framework"
    python = root / "runtimes/release/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    (root / "application.json").write_text(json.dumps({"id": "freecad-mcp-server"}))
    (root / "plugin").mkdir()
    config = {
        "mcpServers": {
            "freecad": {
                "command": str(python),
                "args": [
                    "-m",
                    "freecad_mcp_host",
                    "--state",
                    str(root / "state"),
                    "--publication",
                    str(root / "application.json"),
                    "connect",
                ],
            }
        }
    }
    (root / "plugin/.mcp.json").write_text(json.dumps(config))
    marker = output / "framework-installation.json"
    value = {
        "schema_version": 1,
        "application_id": "freecad-mcp-server",
        "output": str(root),
        "python": str(python),
        "workspace": str(tmp_path / "CAD"),
    }
    marker.write_text(json.dumps(value))
    assert selected_host(output) == value
    python.unlink()
    with pytest.raises(ValueError, match="Invalid selected"):
        selected_host(output)
    python.write_bytes(b"fixture")
    value["python"] = str(python)
    marker.write_text(json.dumps(value))
    (root / "plugin/.mcp.json").write_text("{}")
    with pytest.raises(ValueError, match="Invalid selected"):
        selected_host(output)
    (root / "plugin/.mcp.json").write_text(json.dumps(config))
    value["python"] = sys.executable
    marker.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="Invalid selected"):
        selected_host(output)


@pytest.mark.parametrize("value", ["bad json", "null", "{}", "[]"])
def test_broken_selection_never_falls_back_to_direct_connection(tmp_path, value):
    (tmp_path / "framework-installation.json").write_text(value)
    with pytest.raises(ValueError, match="Invalid selected"):
        selected_host(tmp_path)


@pytest.mark.parametrize("mode", ["legacy", "auto", "2026-07-28"])
def test_upgrade_preserves_protocol_workspace_and_refuses_changed_policy(tmp_path, mode):
    output = tmp_path / "local"
    root = output / "framework"
    python = root / "runtimes/current/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    workspace = tmp_path / "CAD"
    publish(workspace, root, python, installed=True, protocol_mode=mode)
    marker = output / "framework-installation.json"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "application_id": "freecad-mcp-server",
                "python": str(python),
                "output": str(root),
                "workspace": str(workspace),
            }
        )
    )
    result = upgrade_plan(output)
    assert result["protocol_mode"] == mode and result["workspace"] == str(workspace)
    assert result["extension_dirs"] == [] and result["freecad_cmd"] is None
    publication = root / "application.json"
    definition = json.loads(publication.read_bytes())
    definition["backends"][0]["service"]["allow_writes"] = False
    publication.write_text(json.dumps(definition))
    before = publication.read_bytes()
    with pytest.raises(ValueError, match="Custom backend policy"):
        upgrade_plan(output)
    assert publication.read_bytes() == before
