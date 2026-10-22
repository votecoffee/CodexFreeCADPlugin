"""Real 0.20 ledger contracts with a fake process driver; no MCP/native processes."""

import io
import json
import os
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from codex_freecad import resource_ownership as app
from codex_freecad.client import LiveClient

ResourceLedger = pytest.importorskip("universal_tools.resources").ResourceLedger


class Driver:
    def __init__(self):
        self.processes = {}
        self.add(os.getpid(), "100")

    def add(self, pid=100001, created="200"):
        self.processes[pid] = {
            "host_id": "f" * 64,
            "pid": pid,
            "created": created,
            "executable": r"c:\fixture\harmless.exe",
        }
        return self.processes[pid]

    def capture(self, pid):
        if pid not in self.processes:
            raise ProcessLookupError("gone")
        return self.processes[pid]

    def capture_handle(self, handle, pid):
        return self.capture(pid)

    def state(self, identity):
        observed = self.processes.get(identity["pid"])
        return "absent" if observed is None else "alive" if observed == identity else "different"


@pytest.fixture
def rig(tmp_path):
    driver = Driver()
    ledger = ResourceLedger(tmp_path / "private-registry", driver=driver)
    owner = ledger.owner(app.APPLICATION_ID)
    return owner, ledger, driver


def test_private_native_reservation_binding_barrier_and_verified_close(rig):
    owner, ledger, driver = rig
    claim = app.NativeClaim(owner)
    reservation = ledger.get(claim.resource_id)
    assert reservation.state == "launching" and reservation.process is None
    assert reservation.cleanup_mode == "report" and reservation.recovery_barrier
    identity = driver.add()
    claim.bind(SimpleNamespace(pid=identity["pid"], _handle=123))
    bound = ledger.get(claim.resource_id)
    assert bound.owner.pid == os.getpid() and bound.owner_id == owner.owner_id
    assert bound.process.created == "200"
    with pytest.raises(RuntimeError, match="unverified"):
        claim.closed()
    driver.processes.pop(identity["pid"])
    claim.closed()
    retired = ledger.get(claim.resource_id)
    assert retired.state == "released" and retired.recovery_barrier
    assert retired.reconciliation and retired.barrier_resolution is None
    owner.close()


def test_failed_launch_preserves_unbound_reservation(rig):
    owner, ledger, _ = rig
    claim = app.NativeClaim(owner)
    claim.failed("Injected launcher failure; do not guess a PID")
    record = ledger.get(claim.resource_id)
    assert record.state == "launching" and record.process is None and record.recovery_barrier
    with pytest.raises(ValueError, match="recovery"):
        owner.close()


def test_attachment_pid_reuse_is_refused_and_detach_never_terminates(rig):
    owner, ledger, driver = rig
    identity = driver.add(created="50")
    attached = app.Attachment(identity["pid"], owner)
    attached.verify(identity["pid"])
    replacement = driver.add(created="300")
    with pytest.raises(RuntimeError, match="identity changed"):
        attached.verify(identity["pid"])
    attached.close()
    record = ledger.get(attached.record.resource_id)
    assert record.ownership == "attached" and record.cleanup_mode == "report"
    assert record.state == "released" and driver.capture(replacement["pid"]) == replacement


def test_shared_reference_release_preserves_host_and_owner_is_real_supervisor(rig):
    owner, ledger, driver = rig
    host = driver.add(created="50")
    with app.resource_session(owner=owner):
        record = app.share_supervisor(host)
        assert record.ownership == "shared" and record.cleanup_mode == "report"
        assert app.supervisor_status()["supervisor"]["pid"] == os.getpid()
    assert ledger.get(record.resource_id).state == "released"
    assert driver.capture(host["pid"]) == host


def test_changed_binding_keeps_barrier(rig, monkeypatch):
    owner, ledger, driver = rig
    driver.add()
    claim = app.NativeClaim(owner)
    monkeypatch.setattr(
        driver, "capture_handle", lambda *args: {**driver.capture(100001), "created": "999"}
    )
    with pytest.raises(RuntimeError, match="identity changed"):
        claim.bind(SimpleNamespace(pid=100001, _handle=123))
    assert ledger.get(claim.resource_id).recovery_barrier


def test_native_bridge_startup_probe_needs_no_framework_or_process_control(tmp_path, monkeypatch):
    state = tmp_path / "bridge.json"
    state.write_text(json.dumps({"port": 12345, "token": "fixture-token"}))
    client = LiveClient(state, managed=False)
    client.opener = SimpleNamespace(
        open=lambda *args, **kwargs: io.BytesIO(b'{"result":{"fixture":true}}')
    )
    monkeypatch.setattr(
        app, "api_owner", lambda *args: pytest.fail("Native probe imported ownership runtime")
    )
    assert client.call("status") == {"fixture": True}
    client.close()


def test_lost_live_reply_retains_barrier_after_detach(rig, tmp_path):
    owner, ledger, driver = rig
    gui = driver.add(created="50")
    state = tmp_path / "bridge.json"
    state.write_text(json.dumps({"port": 12345, "token": "fixture-token", "pid": gui["pid"]}))
    client = LiveClient(state)
    client.resource_owner = owner

    def lost(*args, **kwargs):
        raise URLError("Injected lost reply")

    client.opener = SimpleNamespace(open=lost)
    with pytest.raises(ValueError, match="Inspect the model"):
        client.call("status")
    resource_id = client.attachment.record.resource_id
    client.close()
    record = ledger.get(resource_id)
    assert record.state == "released" and record.recovery_barrier
    assert driver.capture(gui["pid"]) == gui
