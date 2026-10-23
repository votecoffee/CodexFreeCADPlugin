"""Exact-generation reconciliation policy; synthetic identities, no termination."""

import hashlib
import json
import os

import pytest

from codex_freecad.generation_journal import reconcile_dead_claims
from codex_freecad.resource_ownership import APPLICATION_ID

resources = pytest.importorskip("universal_tools.resources")


class Driver:
    def __init__(self):
        self.processes = {}
        self.unknown = set()

    def add(self, pid, created):
        identity = {
            "host_id": "a" * 64,
            "pid": pid,
            "created": str(created),
            "executable": os.path.normcase("C:/fixture/pythonw.exe"),
        }
        self.processes[pid] = identity
        return identity

    def capture(self, pid):
        if pid not in self.processes:
            raise ProcessLookupError()
        return self.processes[pid]

    def state(self, identity):
        if identity["pid"] in self.unknown:
            return "unknown"
        current = self.processes.get(identity["pid"])
        return "absent" if current is None else "alive" if current == identity else "different"


def rig(tmp_path):
    driver = Driver()
    driver.add(os.getpid(), 100)
    ledger = resources.ResourceLedger(tmp_path / "registry", driver=driver)
    old = ledger.owner(APPLICATION_ID)
    return driver, ledger, old


def change_owner(driver, ledger):
    driver.add(os.getpid(), 500)
    return ledger.owner(APPLICATION_ID)


def generation(state, owner, actors):
    path = state / "process-generations" / (owner.owner_id + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "owner": owner.identity.model_dump(mode="json"),
                "inventory": "observed-job-membership",
                "actors": actors,
            }
        )
    )


def test_recovery_requires_every_private_actor_gone_and_keeps_barrier_and_original_bytes(tmp_path):
    driver, ledger, old = rig(tmp_path)
    worker = driver.add(12001, 200)
    helper = driver.add(12002, 250)
    claim = old.remember_process(worker["pid"], "Harmless private fixture", ownership="private")
    old.set_recovery_barrier(
        claim.resource_id, "Uncertain native work remains inspected separately"
    )
    state = tmp_path / "state"
    generation(state, old, [old.identity.model_dump(), worker, helper])
    receipt = state / "native-receipts/original.json"
    receipt.parent.mkdir()
    receipt.write_bytes(b'{"state":"uncertain","replay_allowed":false}')
    original_receipt = receipt.read_bytes()
    before = ledger._path(claim.resource_id).read_bytes()
    new = change_owner(driver, ledger)
    del driver.processes[worker["pid"]]
    report = reconcile_dead_claims(new, state)
    assert report["observations"][0]["reason"] == "private-generation-still-live-or-unverifiable"
    assert ledger.get(claim.resource_id).state == "active"
    del driver.processes[helper["pid"]]
    report = reconcile_dead_claims(new, state)
    retired = ledger.get(claim.resource_id)
    assert retired.state == "released" and retired.recovery_barrier
    assert report["observations"][0]["before_sha256"] == hashlib.sha256(before).hexdigest()
    assert next((state / "recovery-observations").glob("*.before.json")).read_bytes() == before
    assert receipt.read_bytes() == original_receipt


@pytest.mark.parametrize("ownership", ["attached", "shared"])
def test_departed_attachment_releases_reference_and_preserves_live_external_process(
    tmp_path, ownership
):
    driver, ledger, old = rig(tmp_path)
    external = driver.add(12003, 50)
    claim = old.remember_process(external["pid"], "External dirty GUI", ownership=ownership)
    old.set_recovery_barrier(claim.resource_id, "Attached document outcome unknown")
    new = change_owner(driver, ledger)
    reconcile_dead_claims(new, tmp_path / "state")
    assert ledger.get(claim.resource_id).state == "released"
    assert ledger.get(claim.resource_id).recovery_barrier
    assert driver.capture(external["pid"]) == external


def test_live_unknown_unbound_and_legacy_claims_are_reported_and_preserved(tmp_path):
    driver, ledger, old = rig(tmp_path)
    worker = driver.add(12004, 200)
    legacy = old.remember_process(worker["pid"], "Legacy private fixture", ownership="private")
    intent = old.begin_launch("Unbound uncertain intent")
    new = change_owner(driver, ledger)
    live = new.begin_launch("Current live peer")
    del driver.processes[worker["pid"]]
    report = reconcile_dead_claims(new, tmp_path / "state")
    reasons = {r["resource_id"]: r["reason"] for r in report["observations"]}
    assert reasons[legacy.resource_id] == "legacy-claim-without-retained-generation-inventory"
    assert reasons[intent.resource_id] == "uncertain-cleanup-or-unbound-launch-intent"
    assert reasons[live.resource_id] == "live-or-unverifiable-owner"
    driver.unknown.add(os.getpid())
    report = reconcile_dead_claims(new, tmp_path / "state")
    assert all(r["action"] == "preserved" for r in report["observations"])
    assert all(ledger.get(r).state not in resources.TERMINAL for r in reasons)
