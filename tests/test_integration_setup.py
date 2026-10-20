import json
import subprocess
import sys

import pytest

from codex_freecad.integration import connection_plan, execute_plan
from codex_freecad.setup import generate


@pytest.fixture
def installation(tmp_path):
    output = tmp_path / "setup & [CAD]!"
    result = generate(tmp_path / "CAD models", output)
    assert "broker_manifests" not in result
    assert not (output / "broker").exists()
    return output


def test_standalone_plan_generates_no_client_changes(installation, tmp_path):
    home = tmp_path / "empty home"
    plan = connection_plan(installation, codex_home=home)
    assert plan["integration"] == "standalone"
    assert plan["commands"] == [
        ["codex", "plugin", "marketplace", "add", str(installation)],
        ["codex", "plugin", "add", "freecad-modeling@freecad-development"],
    ]
    market = json.loads((installation / ".agents/plugins/marketplace.json").read_text())
    assert market["plugins"][0]["source"]["path"] == "./plugin"
    assert (installation / "plugin/.mcp.json").is_file()
    assert not home.exists()


def test_other_plugins_do_not_select_a_different_route(installation, tmp_path):
    home = tmp_path / "codex"
    home.mkdir()
    config = home / "config.toml"
    config.write_text('[plugins."universal-tools@old-market"]\nenabled = true\n')
    before = config.read_bytes()
    plan = connection_plan(installation, codex_home=home)
    assert plan["integration"] == "standalone"
    assert all(command[0] == "codex" for command in plan["commands"])
    assert config.read_bytes() == before


def test_none_does_not_read_configuration_or_run_commands(tmp_path):
    home = tmp_path / "codex"
    home.mkdir()
    (home / "config.toml").write_text("invalid configuration")
    plan = connection_plan(tmp_path, integration="none", codex_home=home)
    assert plan == {"integration": "none", "commands": []}
    execute_plan(plan, run=lambda *args, **kwargs: pytest.fail("none executed a command"))


@pytest.mark.parametrize("route", ["broker", "auto"])
def test_removed_routes_are_rejected_before_configuration_access(tmp_path, route):
    with pytest.raises(ValueError, match="standalone or none"):
        connection_plan(tmp_path, integration=route)
    with pytest.raises(ValueError, match="Only standalone"):
        execute_plan({"integration": route}, run=lambda *a, **k: pytest.fail("Executed old route"))


@pytest.mark.parametrize("enabled", [True, False])
def test_existing_direct_connections_are_preserved(installation, tmp_path, enabled):
    home = tmp_path / "codex"
    home.mkdir()
    config = home / "config.toml"
    config.write_text("[mcp_servers.freecad-headless]\nenabled = " + str(enabled).lower())
    before = config.read_bytes()
    with pytest.raises(ValueError, match="Direct FreeCAD MCP entries already exist"):
        connection_plan(installation, codex_home=home)
    assert config.read_bytes() == before


def test_execution_preserves_argv_environment_and_stops_on_failure(installation, tmp_path):
    plan = connection_plan(installation, codex_home=tmp_path / "isolated")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))

    execute_plan(plan, run=run)
    assert [call[0] for call in calls] == plan["commands"]
    assert all(call[1]["env"]["CODEX_HOME"] == str(tmp_path / "isolated") for call in calls)
    assert all(call[1]["check"] is True and "shell" not in call[1] for call in calls)

    def fail(command, **kwargs):
        raise OSError("fixture failure")

    with pytest.raises(OSError, match="fixture failure"):
        execute_plan(plan, run=fail)


@pytest.mark.parametrize("config", ['plugins = ["invalid"]', "mcp_servers = []", "invalid toml"])
def test_malformed_configuration_stops_planning(installation, tmp_path, config):
    home = tmp_path / "codex"
    home.mkdir()
    (home / "config.toml").write_text(config)
    with pytest.raises(ValueError, match="Cannot read Codex configuration"):
        connection_plan(installation, codex_home=home)


@pytest.mark.parametrize(
    "options",
    [["--integration", "broker"], ["--integration", "auto"], ["--broker-python", "python"]],
)
def test_cli_refuses_removed_options_without_creating_configuration(tmp_path, options):
    output = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_freecad.integration",
            "--output",
            str(output),
            "--apply",
            *options,
        ],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert not output.exists()


def test_server_refuses_old_catalog_flag_before_creating_a_native_client(tmp_path):
    workspace = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_freecad.server",
            "--mode",
            "headless",
            "--workspace",
            str(workspace),
            "--broker-catalog",
        ],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert not workspace.exists()
