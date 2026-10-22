"""Fixed release identities; no engineering server or native CAD process is started."""

import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from packaging.version import Version

from codex_freecad import __package_version__, __version__
from codex_freecad.framework_setup import publish
from codex_freecad.setup import generate
from codex_freecad.versioning import (
    apply_mcp_identity,
    canonical_version,
    release_from_utc,
    same_version,
    timestamp_forms,
    version_key,
)

ROOT = Path(__file__).parents[1]


def test_padded_display_has_pep440_and_numeric_semver_package_identity():
    forms = timestamp_forms("26.0101.000001")
    assert forms == {
        "display_version": "26.0101.000001",
        "package_version": "26.101.1",
        "assembly_file_version": "26.101.0.1",
    }
    assert str(Version(forms["package_version"])) == forms["package_version"]
    assert same_version(forms["display_version"], forms["package_version"])
    assert version_key("26.0101.000010") > version_key("26.101.9")
    assert version_key("26.0101.000001") > version_key("0.9.0")
    assert canonical_version("00.0101.000000") == "0.101.0"


@pytest.mark.parametrize("value", [None, "1.2", "1.2.3.4", "1.2.-3", "1.2.3rc1", " 1.2.3"])
def test_non_numeric_release_identities_are_rejected(value):
    with pytest.raises(ValueError):
        canonical_version(value)


@pytest.mark.parametrize(
    "value",
    [
        "26.0230.000000",
        "26.0101.240000",
        "26.0101.006000",
        "26.0101.000060",
        "26.229.123456",
        "25.0229.000000",
    ],
)
def test_timestamp_requires_real_calendar_and_full_padding(value):
    with pytest.raises(ValueError):
        timestamp_forms(value)


def test_assembly_mapping_stays_within_four_uint16_components():
    for display in ("00.0101.000000", "28.0229.010203", "99.1231.235959"):
        parts = tuple(map(int, timestamp_forms(display)["assembly_file_version"].split(".")))
        assert len(parts) == 4 and all(0 <= part < 65535 for part in parts)
    assert timestamp_forms("99.1231.235959")["assembly_file_version"] == "99.1231.2359.59"


@pytest.mark.parametrize(
    ("utc", "display", "local"),
    [
        ("2026-01-01T05:00:01Z", "26.0101.000001", "2026-01-01T00:00:01-05:00"),
        ("2026-03-08T06:59:59Z", "26.0308.015959", "2026-03-08T01:59:59-05:00"),
        ("2026-03-08T07:00:00Z", "26.0308.030000", "2026-03-08T03:00:00-04:00"),
        ("2026-11-01T05:59:59Z", "26.1101.015959", "2026-11-01T01:59:59-04:00"),
        ("2026-11-01T06:00:00Z", "26.1101.010000", "2026-11-01T01:00:00-05:00"),
    ],
)
def test_explicit_utc_conversion_handles_new_york_dst(utc, display, local):
    release = release_from_utc(utc)
    assert release["display_version"] == display and release["stamped_at"] == local
    assert release["stamped_utc"] == utc and release["timezone"] == "America/New_York"


@pytest.mark.parametrize(
    "value",
    [
        "2026-01-01T00:00:00",
        "2026-01-01T00:00:00.1Z",
        "1999-01-01T05:00:00Z",
        "2100-01-01T05:00:00Z",
    ],
)
def test_stamp_rejects_ambiguous_precision_and_unsupported_years(value):
    with pytest.raises(ValueError):
        release_from_utc(value)


def test_release_requires_explicit_utc_and_rejects_duplicate_or_backward_local_stamps(tmp_path):
    with pytest.raises(ValueError, match="explicit UTC"):
        release_from_utc("2026-01-01T00:00:00-05:00")
    spec = importlib.util.spec_from_file_location(
        "stamp_version", ROOT / "scripts/stamp_version.py"
    )
    stamp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stamp)
    package = tmp_path / "src/codex_freecad"
    package.mkdir(parents=True)
    previous = release_from_utc("2026-11-01T05:00:00Z")
    (package / "release.json").write_text(json.dumps(previous))
    with pytest.raises(ValueError, match="collision"):
        stamp.stamp(tmp_path, "2026-11-01T06:00:00Z")
    with pytest.raises(ValueError, match="moves backward"):
        stamp.stamp(tmp_path, "2026-11-01T04:59:59Z")
    assert json.loads((package / "release.json").read_bytes()) == previous


def test_committed_manifests_and_package_mirrors_share_one_checkpoint():
    backend = json.loads((ROOT / "src/codex_freecad/release.json").read_bytes())
    host = json.loads((ROOT / "framework-host/src/freecad_mcp_host/release.json").read_bytes())
    assert backend == host == release_from_utc(backend["stamped_utc"])
    assert __version__ == backend["display_version"]
    assert __package_version__ == backend["package_version"]
    for project in (ROOT / "pyproject.toml", ROOT / "framework-host/pyproject.toml"):
        assert tomllib.loads(project.read_text())["project"]["version"] == __package_version__


def test_generated_direct_and_host_plugins_use_canonical_versions_with_fixed_display(tmp_path):
    generate(tmp_path / "models", tmp_path / "direct")
    result = publish(tmp_path / "models", tmp_path / "host", sys.executable)
    assert result["app_version"] == __version__ and result["framework"] == "0.20.0"
    for root in (tmp_path / "direct/plugin", Path(result["plugin"])):
        manifest = json.loads((root / ".codex-plugin/plugin.json").read_bytes())
        release = json.loads((root / "release.json").read_bytes())
        assert manifest["version"] == release["package_version"] == __package_version__
        assert __version__ in manifest["description"]
        skill = (root / "skills/freecad-modeling/SKILL.md").read_text()
        assert f'version: "{__package_version__}"' in skill
        assert f'display_version: "{__version__}"' in skill


def test_mcp_server_info_uses_app_version_without_constructing_a_server():
    server = SimpleNamespace(_lowlevel_server=SimpleNamespace(version="0.20.0"))
    assert apply_mcp_identity(server) is server
    assert server._lowlevel_server.version == __version__


def test_portable_native_package_preserves_fixed_manifest(tmp_path):
    from codex_freecad.native_package import copy_native_package

    copy_native_package(tmp_path / "codex_freecad")
    assert (tmp_path / "codex_freecad/release.json").read_bytes() == (
        ROOT / "src/codex_freecad/release.json"
    ).read_bytes()


def test_manager_compares_normalized_versions_and_reports_display_separately():
    pytest.importorskip("universal_tools.framework")
    from freecad_mcp_host.management import StatusCache, newer

    assert not newer("26.0101.000001", "26.101.1")
    assert newer("26.0101.000010", "26.101.9")
    assert not newer("unknown", "26.101.1")
    cache = StatusCache(Path("unused-state"), Path("unused-publication"))
    assert cache.running["app"] == cache.running["host"] == __package_version__
    assert __version__ in cache.snapshot().message


def test_cli_version_exits_before_client_or_lifetime_creation(capsys):
    from codex_freecad import server

    with (
        patch.object(sys, "argv", ["codex-freecad", "--version"]),
        patch.object(
            server, "HeadlessClient", side_effect=AssertionError("native client constructed")
        ),
        pytest.raises(SystemExit) as stopped,
    ):
        server.main()
    assert stopped.value.code == 0 and capsys.readouterr().out.strip() == __version__


def test_host_cli_version_exits_before_runtime_or_state_check(capsys):
    pytest.importorskip("universal_tools.framework")
    from freecad_mcp_host import __main__ as host

    with (
        patch.object(sys, "argv", ["freecad-mcp-host", "--version"]),
        patch.object(host, "check_runtime", side_effect=AssertionError("host runtime touched")),
        pytest.raises(SystemExit) as stopped,
    ):
        host.main()
    assert stopped.value.code == 0 and capsys.readouterr().out.strip() == __version__


def test_explicit_stamp_updates_all_mirrors_idempotently_and_validates_before_writes(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "stamp_version", ROOT / "scripts/stamp_version.py"
    )
    stamp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stamp)
    for package in ("src/codex_freecad", "framework-host/src/freecad_mcp_host"):
        (tmp_path / package).mkdir(parents=True)
    for project in ("pyproject.toml", "framework-host/pyproject.toml"):
        (tmp_path / project).write_text('[project]\nversion = "0.9.0"\n')
    skill = tmp_path / "src/codex_freecad/standalone_skill.md"
    skill.write_text("---\nname: example\ndescription: Example skill\n---\nBody.\n")
    stamp.stamp(tmp_path, "2026-01-01T05:00:01Z")
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    stamp.stamp(tmp_path, "2026-01-01T05:00:01Z")
    assert all(p.read_bytes() == raw for p, raw in files.items())
    (tmp_path / "framework-host/pyproject.toml").write_text("invalid")
    with pytest.raises(ValueError, match="version is missing"):
        stamp.stamp(tmp_path, "2026-01-02T05:00:01Z")
    assert (tmp_path / "src/codex_freecad/release.json").read_bytes() == files[
        tmp_path / "src/codex_freecad/release.json"
    ]
