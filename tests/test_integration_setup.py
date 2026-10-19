import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import Client

from codex_freecad.broker_catalog import installation_catalog
from codex_freecad.extension_runtime import Registry
from codex_freecad.integration import WRITE_TOOLS, connection_plan, execute_plan
from codex_freecad.server import create_server
from codex_freecad.setup import generate


@pytest.fixture
def installation(tmp_path):
    output = tmp_path / "setup & [CAD]!"
    generate(tmp_path / "CAD models", output)
    return output


def cached_broker(home, tmp_path, *, enabled=True):
    state = tmp_path / "broker state"
    state.mkdir(exist_ok=True)
    (state / "settings.json").write_text("{}")
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text(
        '[plugins."universal-tools@test-market"]\nenabled = ' + str(enabled).lower() + "\n"
    )
    cache = home / "plugins/cache/test-market/universal-tools/1.0.0"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "plugin.json").write_text(json.dumps({"name": "universal-tools"}))
    runtime = {"python": sys.executable, "state": str(state)}
    (cache / "runtime.json").write_text(json.dumps(runtime))
    return cache, runtime


def test_absent_broker_selects_own_plugin_and_generated_marketplace(installation, tmp_path):
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
    assert not home.exists()  # Planning does not install anything.


def test_enabled_broker_skips_plugin_install_and_scopes_write_tools(installation, tmp_path):
    home = tmp_path / "codex"
    _, runtime = cached_broker(home, tmp_path)
    plan = connection_plan(installation, codex_home=home)
    assert plan["integration"] == "broker" and plan["broker"] == runtime
    assert len(plan["commands"]) == 2
    for command in plan["commands"]:
        assert command[:3] == [sys.executable, "-m", "universal_tools"]
        assert "--replace" not in command and "plugin" not in command
        manifest = json.loads(Path(command[-1]).read_text())
        assert manifest["session_mode"] == "exclusive"
        assert manifest["allowed_write_tools"] == WRITE_TOOLS
        assert "--broker-catalog" in manifest["transport"]["args"]
    assert not (Path(runtime["state"]) / "services").exists()


def test_disabled_or_merely_cached_broker_does_not_suppress_standalone(installation, tmp_path):
    home = tmp_path / "codex"
    cached_broker(home, tmp_path, enabled=False)
    assert connection_plan(installation, codex_home=home)["integration"] == "standalone"
    (home / "config.toml").write_text("")
    assert connection_plan(installation, codex_home=home)["integration"] == "standalone"


def test_enabled_but_broken_broker_fails_without_plugin_fallback(installation, tmp_path):
    home = tmp_path / "codex"
    cache, _ = cached_broker(home, tmp_path)
    (cache / "runtime.json").write_text("{}")
    with pytest.raises(ValueError, match="invalid cached runtime"):
        connection_plan(installation, codex_home=home)


def test_ambiguous_broker_runtimes_need_explicit_selection(installation, tmp_path):
    home = tmp_path / "codex"
    cache, runtime = cached_broker(home, tmp_path)
    other_state = tmp_path / "other broker"
    other_state.mkdir()
    (other_state / "settings.json").write_text("{}")
    other = cache.parent / "2.0.0"
    other.mkdir()
    (other / "plugin.json").write_text(json.dumps({"name": "universal-tools"}))
    (other / "runtime.json").write_text(json.dumps({**runtime, "state": str(other_state)}))
    with pytest.raises(ValueError, match="ambiguous"):
        connection_plan(installation, codex_home=home)
    plan = connection_plan(
        installation,
        codex_home=home,
        broker_python=runtime["python"],
        broker_state=runtime["state"],
    )
    assert plan["broker"] == runtime


def test_standalone_override_and_none_remain_available(installation, tmp_path):
    home = tmp_path / "codex"
    cached_broker(home, tmp_path)
    assert (
        connection_plan(installation, codex_home=home, integration="standalone")["integration"]
        == "standalone"
    )
    execute_plan(connection_plan(installation, integration="none"))
    assert connection_plan(installation, integration="none") == {
        "integration": "none",
        "commands": [],
    }


@pytest.mark.parametrize(
    "setting",
    [
        '[mcp_servers.freecad-headless]\ncommand = "python"\n',
        '[plugins."freecad-modeling@freecad-development"]\nenabled = true\n',
    ],
)
def test_broker_migration_preserves_existing_direct_connections(installation, tmp_path, setting):
    home = tmp_path / "codex"
    cached_broker(home, tmp_path)
    config = home / "config.toml"
    config.write_text(config.read_text() + setting)
    before = config.read_bytes()
    with pytest.raises(ValueError, match="disable it explicitly"):
        connection_plan(installation, codex_home=home)
    assert config.read_bytes() == before


def test_registration_preflight_is_idempotent_and_preserves_conflicts(installation, tmp_path):
    home = tmp_path / "codex"
    _, runtime = cached_broker(home, tmp_path)
    services = Path(runtime["state"]) / "services"
    services.mkdir()
    for name in ("freecad-live", "freecad-headless"):
        source = installation / "broker" / (name + ".service.json")
        normalized = {
            **json.loads(source.read_text()),
            "read_only_tools": [],
            "lease_seconds": 900.0,
        }
        (services / (name + ".json")).write_text(json.dumps(normalized))
    assert connection_plan(installation, codex_home=home)["commands"] == []
    checks = []
    execute_plan(
        connection_plan(installation, codex_home=home), run=lambda cmd, **kwargs: checks.append(cmd)
    )
    assert len(checks) == 1 and checks[0][1] == "-c"
    conflict = services / "freecad-headless.json"
    wrong = json.loads(conflict.read_text())
    wrong["allow_writes"] = False
    conflict.write_text(json.dumps(wrong))
    before = conflict.read_bytes()
    with pytest.raises(ValueError, match="review and replace"):
        connection_plan(installation, codex_home=home)
    assert conflict.read_bytes() == before


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


def test_malformed_codex_sections_stop_planning(installation, tmp_path):
    home = tmp_path / "codex"
    home.mkdir()
    (home / "config.toml").write_text('plugins = ["invalid"]')
    with pytest.raises(ValueError, match="Cannot read Codex configuration"):
        connection_plan(installation, codex_home=home)


def test_broker_requires_a_real_install_and_complete_explicit_paths(installation, tmp_path):
    with pytest.raises(ValueError, match="No enabled"):
        connection_plan(installation, integration="broker", codex_home=tmp_path / "empty")
    with pytest.raises(ValueError, match="both"):
        connection_plan(installation, codex_home=tmp_path / "empty", broker_python=sys.executable)


def test_incompatible_runtime_stops_before_either_registration(installation, tmp_path):
    import subprocess

    home = tmp_path / "codex"
    cached_broker(home, tmp_path)
    plan = connection_plan(installation, codex_home=home)
    calls = []

    def reject(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(ValueError, match="No services were registered"):
        execute_plan(plan, run=reject)
    assert len(calls) == 1 and calls[0][1] == "-c"
    assert calls[0][-2:] == [command[-1] for command in plan["commands"]]


def test_installation_catalog_never_imports_extension_code_or_native_backend(tmp_path):
    root = tmp_path / "extensions"
    extension = root / "example"
    extension.mkdir(parents=True)
    (extension / "__init__.py").write_text(
        'raise RuntimeError("Must never execute during metadata")'
    )
    (extension / "manifest.json").write_text(
        json.dumps(
            {
                "id": "example",
                "version": "1.0.0",
                "api_version": 1,
                "description": "example",
                "ui": False,
                "capabilities": {
                    "inspect": {
                        "kind": "query",
                        "description": "Inspect example",
                        "handler": "inspect",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    }
                },
            }
        )
    )
    before = set(sys.modules)
    result = installation_catalog([root])
    assert "FreeCAD" not in set(sys.modules) - before
    assert not any(name.startswith("_codex_cad_extension_") for name in set(sys.modules) - before)
    assert next(c for c in result["capabilities"] if c["id"] == "example.inspect")["discovery"] == {
        "tool": "describe_capability",
        "arguments": {"capability": "example.inspect"},
    }
    (extension / "__init__.py").write_text('raise RuntimeError("Changed installed code")')
    assert installation_catalog([root])["catalog_revision"] != result["catalog_revision"]


def test_installation_and_native_catalog_revisions_match_for_same_sources():
    registry = Registry()
    try:
        catalog = installation_catalog()
        assert catalog["catalog_revision"] == registry.catalog()["catalog_revision"]
        assert {c["id"] for c in catalog["capabilities"]} == {
            c["name"] for c in registry.catalog()["capabilities"]
        }
    finally:
        registry.active.close()


def test_broker_adds_only_readonly_metadata_and_keeps_direct_schemas():
    class NoNativeCalls:
        def call(self, *args, **kwargs):
            raise AssertionError("Discovery contacted a native backend")

        def close(self):
            pass

    async def run():
        async with Client(create_server(NoNativeCalls())) as direct:
            baseline = (await direct.list_tools()).tools
        async with Client(create_server(NoNativeCalls(), broker_extensions=[])) as broker:
            tools = (await broker.list_tools()).tools
            assert [t.model_dump() for t in tools if t.name != "list_broker_capabilities"] == [
                t.model_dump() for t in baseline
            ]
            provider = next(t for t in tools if t.name == "list_broker_capabilities")
            assert provider.annotations.read_only_hint is True
            catalog = await broker.call_tool("list_broker_capabilities", {})
            assert not catalog.is_error
            contents = catalog.structured_content or json.loads(catalog.content[0].text)
            assert contents["schema_version"] == 1
            assert {t.name for t in tools if t.annotations.read_only_hint is not True} == set(
                WRITE_TOOLS
            )

    asyncio.run(run())
