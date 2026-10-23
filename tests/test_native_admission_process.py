"""Opt-in harmless lock-owner death check; no FreeCAD or MCP process."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from codex_freecad.process_lifetime import ProcessSlots


@pytest.mark.resource_process
@pytest.mark.parametrize("limit,abrupt", [(1, True), (4, False), (4, True)])
def test_native_capacity_and_frontend_leases_release_after_owner_exit(tmp_path, limit, abrupt):
    state = tmp_path / ("native-pilot" if limit == 1 else "native-frontends")
    child_code = """
import os, sys
sys.path.insert(0, sys.argv[1])
from codex_freecad.process_lifetime import ProcessSlots
with ProcessSlots(sys.argv[2], limit=int(sys.argv[3])):
    print('admitted', flush=True)
    sys.stdin.buffer.read(1)
    if sys.argv[4] == 'abrupt':
        os._exit(41)
"""
    processes = []
    try:
        for _ in range(limit):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-S",
                        "-B",
                        "-c",
                        child_code,
                        str(Path(__file__).resolve().parents[1] / "src"),
                        str(state),
                        str(limit),
                        "abrupt" if abrupt else "eof",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            )
        # communicate has a deadline; no test can block on an unbounded pipe read.
        # The file-lock observation establishes admission while the owner is alive.
        import time

        deadline = time.monotonic() + 10
        while ProcessSlots.occupied(state, limit=limit) < limit:
            assert all(process.poll() is None for process in processes)
            if time.monotonic() >= deadline:
                pytest.fail("Harmless lock owner did not acquire capacity")
            time.sleep(0.01)
        with pytest.raises(RuntimeError, match="limit reached"):
            with ProcessSlots(state, limit=limit):
                pytest.fail("Capacity exceeded")
        process = processes[0]
        stdout, stderr = process.communicate(b"x", timeout=10)
        assert process.returncode == (41 if abrupt else 0) and stdout.strip() == b"admitted", stderr
        assert ProcessSlots.occupied(state, limit=limit) == limit - 1
        with ProcessSlots(state, limit=limit):
            assert ProcessSlots.occupied(state, limit=limit) == limit
    finally:
        for process in processes:
            if process.poll() is None:
                try:
                    process.communicate(timeout=5)  # Real EOF; only our fixture handles.
                except subprocess.TimeoutExpired:
                    process.kill()  # Exact original private fixture Popen handle only.
                    process.communicate(timeout=10)
