"""Opt-in harmless lock-owner death check; no FreeCAD or MCP process."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from codex_freecad.process_lifetime import ProcessSlots


@pytest.mark.resource_process
def test_native_lease_releases_after_abrupt_owner_exit(tmp_path):
    state = tmp_path / "native-pilot"
    child_code = """
import os, sys
sys.path.insert(0, sys.argv[1])
from codex_freecad.process_lifetime import ProcessSlots
with ProcessSlots(sys.argv[2], limit=1):
    print('admitted', flush=True)
    sys.stdin.buffer.read(1)
    os._exit(41)
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            child_code,
            str(Path(__file__).resolve().parents[1] / "src"),
            str(state),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        # communicate has a deadline; no test can block on an unbounded pipe read.
        # The file-lock observation establishes admission while the owner is alive.
        import time

        deadline = time.monotonic() + 10
        while ProcessSlots.occupied(state, limit=1) == 0:
            assert process.poll() is None
            if time.monotonic() >= deadline:
                pytest.fail("Harmless lock owner did not acquire capacity")
            time.sleep(0.01)
        with pytest.raises(RuntimeError, match="limit reached"):
            with ProcessSlots(state, limit=1):
                pytest.fail("Second native owner admitted")
        stdout, stderr = process.communicate(b"x", timeout=10)
        assert process.returncode == 41 and stdout.strip() == b"admitted", stderr
        with ProcessSlots(state, limit=1):
            assert ProcessSlots.occupied(state, limit=1) == 1
    finally:
        if process.poll() is None:
            process.kill()  # Exact original private fixture Popen handle only.
            process.communicate(timeout=10)
