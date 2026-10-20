import json
import sys

import pytest

from codex_freecad.installed_host import selected_host


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
