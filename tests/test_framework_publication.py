import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import codex_freecad
from codex_freecad.framework_setup import publish


@pytest.fixture
def source_package(tmp_path):
    source = tmp_path / "source" / "codex_freecad"
    shutil.copytree(
        Path(codex_freecad.__file__).parent,
        source,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return source


def candidate(tmp_path, source=None, **kwargs):
    return publish(
        tmp_path / "CAD models",
        tmp_path / "candidate",
        sys.executable,
        source_package=source,
        **kwargs,
    )


def test_framework_dependency_is_separate_from_sdk2_backend():
    root = Path(__file__).parents[1]
    backend = tomllib.loads((root / "pyproject.toml").read_text())
    host = tomllib.loads((root / "framework-host/pyproject.toml").read_text())
    assert backend["project"]["dependencies"] == ["mcp==2.3.0"]
    assert host["project"]["dependencies"] == ["universal-codex-tools==0.20.0", "mcp==2.3.0"]
    assert "mcp==2.3.0" in (root / "framework-host/requirements.lock").read_text()


def test_candidate_keeps_standalone_plugin_and_has_no_installation_side_effects(tmp_path):
    result = candidate(tmp_path)
    definition = json.loads(Path(result["publication"]).read_bytes())
    assert definition["id"] == "freecad-mcp-server"
    assert {b["service"]["id"] for b in definition["backends"]} == {
        "freecad-live",
        "freecad-headless",
    }
    assert all(b["service"]["session_mode"] == "exclusive" for b in definition["backends"])
    assert not Path(result["state"]).exists()
    assert not (tmp_path / "CAD models").exists()
    plugin = Path(result["plugin"])
    config = json.loads((plugin / ".mcp.json").read_bytes())
    assert set(config["mcpServers"]) == {"freecad"}
    server = config["mcpServers"]["freecad"]
    assert server["args"][1] == "freecad_mcp_host" and server["args"][-1] == "proxy"
    assert (plugin / "skills/freecad-modeling/SKILL.md").is_file()
    assert "own standalone connection" in definition["instructions"]
    for backend in definition["backends"]:
        service = backend["service"]
        assert service["capability_catalog"]["tool"] == "list_host_capabilities"
        assert "--broker-catalog" not in service["transport"]["args"]
        assert "protocol_mode" not in service  # Preserve the legacy framework default.
        assert "watch_catalog" not in service and "discovery_cache_ttl_seconds" not in service
        assert service["max_argument_depth"] == 64
        assert service["max_argument_nodes"] == 100_000


def test_explicit_installed_publication_replaces_own_marketplace_and_starts_only_app_host(tmp_path):
    result = candidate(tmp_path, installed=True)
    output = Path(result["plugin"]).parent
    marketplace = json.loads((output / ".agents/plugins/marketplace.json").read_bytes())
    assert marketplace["name"] == "freecad-development"
    config = json.loads((Path(result["plugin"]) / ".mcp.json").read_bytes())
    assert set(config["mcpServers"]) == {"freecad"}
    assert config["mcpServers"]["freecad"]["args"][-1] == "connect"
    assert not Path(result["state"]).exists()  # Generation alone never activates a host.


@pytest.mark.parametrize("protocol_mode", ["auto", "2026-07-28"])
def test_protocol_opt_in_binds_publication_but_preserves_resource_identity(tmp_path, protocol_mode):
    first = candidate(tmp_path)
    old = json.loads(Path(first["publication"]).read_bytes())
    second = candidate(tmp_path, protocol_mode=protocol_mode)
    new = json.loads(Path(second["publication"]).read_bytes())
    assert first["deployment"] == second["deployment"]
    assert second["protocol_mode"] == protocol_mode
    for previous, updated in zip(old["backends"], new["backends"], strict=True):
        assert previous["revision"] != updated["revision"]
        assert previous["service"]["resource_id"] == updated["service"]["resource_id"]
        assert updated["service"]["protocol_mode"] == protocol_mode
        assert (
            previous["service"]["allowed_write_tools"] == updated["service"]["allowed_write_tools"]
        )


def test_invalid_protocol_choice_preserves_publication_and_creates_no_new_files(tmp_path):
    first = candidate(tmp_path)
    publication = Path(first["publication"])
    before = publication.read_bytes()
    with pytest.raises(ValueError, match="protocol mode"):
        candidate(tmp_path, protocol_mode="unsupported")
    assert publication.read_bytes() == before
    empty = tmp_path / "unused"
    with pytest.raises(ValueError, match="protocol mode"):
        publish(tmp_path / "models", empty, sys.executable, protocol_mode="unsupported")
    assert not empty.exists() and not (tmp_path / "models").exists()


def test_legacy_rejects_modern_watch_opt_in_before_writing(tmp_path):
    empty = tmp_path / "invalid"
    with pytest.raises(ValueError, match="explicit auto/modern"):
        publish(tmp_path / "models", empty, sys.executable, modern_discovery=True)
    assert not empty.exists()


def test_source_changes_publish_new_immutable_closure_with_same_resource_ids(
    tmp_path, source_package
):
    first = candidate(tmp_path, source_package)
    original = json.loads(Path(first["publication"]).read_bytes())
    frozen = Path(first["deployment"]) / "package/codex_freecad/workflows.py"
    before = frozen.read_bytes()
    with (source_package / "workflows.py").open("a") as stream:
        stream.write("\n# New immutable backend publication\n")
    second = candidate(tmp_path, source_package)
    updated = json.loads(Path(second["publication"]).read_bytes())
    assert first["deployment"] != second["deployment"]
    assert frozen.read_bytes() == before
    assert [b["service"]["resource_id"] for b in original["backends"]] == [
        b["service"]["resource_id"] for b in updated["backends"]
    ]
    assert all(
        a["revision"] != b["revision"]
        for a, b in zip(original["backends"], updated["backends"], strict=True)
    )


def test_repeat_publication_is_idempotent_and_rejects_modified_deployment(tmp_path):
    first = candidate(tmp_path)
    assert candidate(tmp_path)["deployment"] == first["deployment"]
    original = Path(first["publication"]).read_bytes()
    bad = Path(first["deployment"]) / "package/codex_freecad/workflows.py"
    bad.write_text("# Unexpected change")
    with pytest.raises(ValueError, match="immutable backend deployment changed"):
        candidate(tmp_path)
    assert Path(first["publication"]).read_bytes() == original
    assert bad.read_text() == "# Unexpected change"


@pytest.mark.parametrize("change", ["source", "extra", "manifest"])
def test_bootstrap_verifies_complete_declared_closure_before_loading_backend(tmp_path, change):
    result = candidate(tmp_path)
    deployment = Path(result["deployment"])
    good = subprocess.run(
        [sys.executable, "-B", str(deployment / "launcher.py"), "--help"],
        capture_output=True,
        timeout=30,
    )
    assert good.returncode == 0 and b"--framework-backend" in good.stdout
    target = {
        "source": "package/codex_freecad/server.py",
        "extra": "extra.py",
        "manifest": "closure.json",
    }[change]
    (deployment / target).write_text("# Modified closure")
    bad = subprocess.run(
        [sys.executable, "-B", str(deployment / "launcher.py"), "--help"],
        capture_output=True,
        timeout=30,
    )
    assert bad.returncode != 0 and b"Backend closure" in bad.stderr
    assert not (tmp_path / "CAD models").exists()


def test_custom_extensions_are_frozen_in_both_backend_publications(tmp_path):
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "resource.txt").write_text("Original installed resource")
    result = candidate(tmp_path, extension_dirs=[installed])
    definition = json.loads(Path(result["publication"]).read_bytes())
    snapshot = str(Path(result["deployment"]) / "extensions/0")
    for backend in definition["backends"]:
        args = backend["service"]["transport"]["args"]
        assert args.count("--extensions") == 1 and args[args.index("--extensions") + 1] == snapshot
        assert str(installed) not in args
    assert (Path(snapshot) / "resource.txt").read_text() == "Original installed resource"


def test_workflow_guidance_is_available_without_native_target():
    from codex_freecad.workflows import describe_workflow

    assert describe_workflow()["schema_version"] == 1
    assert "Never replay" in describe_workflow("recovery")["guidance"]
    with pytest.raises(ValueError, match="Unknown"):
        describe_workflow("arbitrary-python")
