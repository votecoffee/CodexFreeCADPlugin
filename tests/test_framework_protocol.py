"""Opt-in protocol profile; the framework and CAD backend keep conflicting SDKs isolated."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import codex_freecad


@pytest.mark.framework
def test_app_owned_framework_profile_with_disposable_provider(tmp_path):
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
    ]
    log = tmp_path / "profile.log"
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    with log.open("wb") as output:
        result = subprocess.run(
            command, stdout=output, stderr=subprocess.STDOUT, timeout=180, **options
        )
    assert result.returncode == 0, log.read_text(encoding="utf-8", errors="replace")[-10000:]
    evidence = json.loads((tmp_path / "profile.json").read_bytes())
    assert evidence["framework"] == "0.13.0" and evidence["frontend_tools"] == 14
    assert evidence["native_dispatches"] == 0 and evidence["same_session_refresh"]
