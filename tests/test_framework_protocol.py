"""Opt-in MCP 2.3 profile with independently packaged app-host and CAD backend processes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import codex_freecad


@pytest.mark.framework
def test_app_host_startup_and_reconnect_without_native_dispatch(tmp_path):
    configured = os.environ.get("FREECAD_FRAMEWORK_PYTHON")
    if not configured:
        pytest.skip("Set FREECAD_FRAMEWORK_PYTHON to an isolated app-host runtime")
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            str(Path(configured).resolve()),
            str(root / "tests/host_lifecycle_checks.py"),
            "--root",
            str(tmp_path),
            "--host-source",
            str(root / "framework-host/src"),
            "--backend-source",
            str(Path(codex_freecad.__file__).parent),
            "--backend-python",
            sys.executable,
        ],
        capture_output=True,
        timeout=150,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-10000:]
    assert json.loads((tmp_path / "lifecycle.json").read_bytes())["native_dispatches"] == 0


@pytest.mark.framework
@pytest.mark.parametrize(
    "protocol_mode,frontend_mode",
    [("legacy", "legacy"), ("auto", "2026-07-28"), ("2026-07-28", "legacy")],
)
def test_app_owned_framework_profile_with_disposable_provider(
    tmp_path, protocol_mode, frontend_mode
):
    configured = os.environ.get("FREECAD_FRAMEWORK_PYTHON")
    if not configured:
        pytest.skip("Set FREECAD_FRAMEWORK_PYTHON to an isolated FreeCAD app-host environment")
    command = [
        str(Path(configured).resolve()),
        str(Path(__file__).with_name("framework_protocol_checks.py")),
        "--root",
        str(tmp_path),
        "--source",
        str(Path(codex_freecad.__file__).parent),
        "--backend-python",
        sys.executable,
        "--protocol-mode",
        protocol_mode,
        "--frontend-mode",
        frontend_mode,
    ]
    log = tmp_path / "profile.log"
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    with log.open("wb") as output:
        result = subprocess.run(
            command, stdout=output, stderr=subprocess.STDOUT, timeout=180, **options
        )
    assert result.returncode == 0, log.read_text(encoding="utf-8", errors="replace")[-10000:]
    evidence = json.loads((tmp_path / "profile.json").read_bytes())
    assert evidence["framework"] == "0.16.0" and evidence["frontend_tools"] == 14
    assert evidence["framework_sdk"] == "2.3.0" and evidence["durable_recovery_barrier"]
    assert evidence["native_dispatches"] == 0 and evidence["same_session_refresh"]
    assert evidence["structural_budget_rejections"] == ["depth", "nodes"]
    assert evidence["backend_protocol_mode"] == protocol_mode
    assert evidence["frontend_protocol_mode"] == frontend_mode
    assert evidence["backend_negotiated_protocol"] == (
        "2025-11-25" if protocol_mode == "legacy" else "2026-07-28"
    )
