"""Opt-in harmless Python processes only; never FreeCAD or an MCP server."""

import json
import os
import subprocess
import sys
import time

import pytest

from codex_freecad import resource_ownership as app
from codex_freecad.owned_process import spawn_owned

ResourceLedger = pytest.importorskip("universal_tools.resources").ResourceLedger

pytestmark = [
    pytest.mark.resource_process,
    pytest.mark.skipif(
        os.name != "nt" or os.environ.get("FREECAD_RUN_RESOURCE_FIXTURES") != "1",
        reason="Explicit isolated harmless-process validation only",
    ),
]


def test_owned_pipe_worker_exit_closes_its_harmless_grandchild(tmp_path):
    ledger = ResourceLedger(tmp_path / "private-registry")
    owner = ledger.owner(app.APPLICATION_ID)
    code = (
        "import json,subprocess,sys; "
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "print(json.dumps({'pid':p.pid}),flush=True); input()"
    )
    import subprocess

    worker = spawn_owned(
        [sys.executable, "-u", "-c", code],
        resource_owner=owner,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        message = json.loads(worker.stdout.readline())
        child = ledger.driver.capture(message["pid"])
        record = ledger.get(worker.identity["ledger_resource_id"])
        assert record.state == "active" and record.process.pid == worker.pid
        worker.stdin.write("\n")
        worker.stdin.flush()
        worker.wait(timeout=5)
    finally:
        worker.close_owned_tree()
        for stream in (worker.stdin, worker.stdout, worker.stderr):
            stream.close()
    deadline = time.monotonic() + 5
    while ledger.driver.state(child) not in {"absent", "different"}:
        assert time.monotonic() < deadline, "Owned harmless grandchild survived close"
        time.sleep(0.02)
    assert ledger.get(record.resource_id).state == "released"
    assert ledger.get(record.resource_id).recovery_barrier
    owner.close()


def test_binding_failure_stops_suspended_fixture_before_its_marker(tmp_path, monkeypatch):
    ledger = ResourceLedger(tmp_path / "private-registry")
    owner = ledger.owner(app.APPLICATION_ID)
    marker = tmp_path / "must-not-execute.txt"
    original = app.NativeClaim.bind

    def failed(self, process):
        original(self, process)
        raise RuntimeError("Injected binding handoff failure")

    monkeypatch.setattr(app.NativeClaim, "bind", failed)
    code = "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('executed')"
    with pytest.raises(RuntimeError, match="binding handoff"):
        spawn_owned([sys.executable, "-c", code, str(marker)], resource_owner=owner)
    records = ledger.records()
    assert len(records) == 1 and records[0].recovery_barrier
    assert ledger.driver.state(records[0].process.model_dump()) in {"absent", "different"}
    assert not marker.exists()


def test_abrupt_harmless_supervisor_exit_retains_barrier_and_stops_worker(tmp_path):
    registry = tmp_path / "private-registry"
    code = (
        "import json,os,subprocess,sys; "
        "from universal_tools.resources import ResourceLedger; "
        "from codex_freecad.owned_process import spawn_owned; "
        "owner=ResourceLedger(sys.argv[1]).owner('freecad-mcp-server'); "
        "worker=spawn_owned([sys.executable,'-c','import time;time.sleep(60)'],resource_owner=owner,"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "print(json.dumps({'resource_id':worker.identity['ledger_resource_id']}),flush=True); "
        "os._exit(23)"
    )
    parent = subprocess.run(
        [sys.executable, "-c", code, str(registry)],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert parent.returncode == 23, parent.stderr
    ledger = ResourceLedger(registry)
    record = ledger.get(json.loads(parent.stdout)["resource_id"])
    deadline = time.monotonic() + 5
    while ledger.driver.state(record.process.model_dump()) not in {"absent", "different"}:
        assert time.monotonic() < deadline, "Owned harmless worker survived supervisor death"
        time.sleep(0.02)
    assert record.recovery_barrier and record.state == "active"
    assert ledger.plan(record.resource_id)["eligible"] is False
