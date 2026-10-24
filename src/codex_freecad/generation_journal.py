"""Bounded, durable surviving-supervisor observations and conservative recovery.

No process is terminated here. Native receipts, dirty state and barriers never
become successful outcomes merely because the original process generation died.
"""

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from .process_lifetime import ProcessSlots, process_tree_snapshot


class GenerationJournal:
    def __init__(self, owner, state):
        self.owner, self.state = owner, Path(state)
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.seen = {}
        self.thread = None
        self.path = self.state / "process-generations" / (owner.owner_id + ".json")
        self.record = {
            "schema_version": 1,
            "owner_id": owner.owner_id,
            "owner": owner.identity.model_dump(mode="json"),
            "lifecycle": "active",
            "actors": [],
            "inventory": "pending",
            "observation_policy": "retained job members; bounded samples, not a kernel event history",
        }

    def sample(self):
        from universal_tools.resources import durable_json

        with self.lock:
            if self.record["inventory"] == "uncertain":
                raise RuntimeError(
                    "Generation inventory is uncertain; retain the original observations"
                )
            try:
                tree = process_tree_snapshot(
                    capture_identity=self.owner.ledger.driver.capture_handle
                )
                self.record["current_job"] = tree
                if tree["state"] != "sampled-job-membership":
                    raise RuntimeError("Root job ownership is unavailable")
                for member in tree["owned_processes"]:
                    identity = member["identity"]
                    if int(identity["created"]) != member["creation_filetime"]:
                        raise RuntimeError("Job member generation changed during inventory")
                if self.record["owner"] not in [p["identity"] for p in tree["owned_processes"]]:
                    raise RuntimeError("The surviving supervisor is not in its own retained job")
            except BaseException:
                self.record["inventory"] = "uncertain"
                durable_json(self.path, self.record)
                raise
            for member in tree["owned_processes"]:
                identity = member["identity"]
                self.seen[(identity["pid"], identity["created"])] = identity
            self.record.update(
                actors=list(self.seen.values()),
                inventory="observed-job-membership",
                observed_at=time.time(),
                current_job=tree,
            )
            durable_json(self.path, self.record)

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with ProcessSlots(self.state / "history-admission", limit=1):
            if len(list(self.path.parent.glob("*.json"))) >= 256:
                raise RuntimeError(
                    "Process generation history full; retain/archive original evidence"
                )
            if self.path.exists():
                raise RuntimeError("Process generation already exists")
            self.sample()
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()

    def _poll(self):
        from universal_tools.resources import durable_json

        while not self.stop.wait(0.25):
            try:
                self.sample()
            except BaseException:
                with self.lock:
                    self.record["inventory"] = "uncertain"
                    durable_json(self.path, self.record)
                return

    def close(self, lifecycle):
        from universal_tools.resources import durable_json

        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise RuntimeError("Generation observer did not drain; preserve its history")
        with self.lock:
            if self.record["inventory"] != "uncertain":
                self.sample()
            self.record["lifecycle"] = lifecycle
            durable_json(self.path, self.record)


def reconcile_dead_claims(owner, state):
    """Retire only proven departed claims; keep exact before bytes and barriers."""
    from universal_tools.resources import TERMINAL, ResourceRecord, durable_json

    state = Path(state)
    folder = state / "recovery-observations"
    folder.mkdir(parents=True, exist_ok=True)
    observations = []
    lock = ProcessSlots(state / "recovery-admission", limit=1)
    try:
        lock.__enter__()
    except RuntimeError:
        # Another bounded observer may finish it. Metadata does not need to wait
        # or manufacture native capacity; no claim has been hidden or changed.
        return {"state": "another-recovery-pass-active", "observations": []}
    try:
        for record in owner.ledger.records():
            if record.app_id != owner.app_id or record.state in TERMINAL:
                continue
            row = {
                "resource_id": record.resource_id,
                "previous_revision": record.revision,
                "owner_state": owner.ledger.driver.state(record.owner.model_dump()),
                "action": "preserved",
            }
            observations.append(row)
            if row["owner_state"] not in {"absent", "different"}:
                row["reason"] = "live-or-unverifiable-owner"
                continue
            if record.receipt is not None or record.process is None:
                row["reason"] = "uncertain-cleanup-or-unbound-launch-intent"
                continue
            if record.ownership == "private":
                generation_path = state / "process-generations" / (record.owner_id + ".json")
                if not generation_path.exists():
                    row["reason"] = "legacy-claim-without-retained-generation-inventory"
                    continue
                generation = json.loads(generation_path.read_bytes())
                if (
                    generation["owner"] != record.owner.model_dump(mode="json")
                    or generation["inventory"] != "observed-job-membership"
                ):
                    row["reason"] = "generation-inventory-unverified"
                    continue
                identities = [
                    record.process.model_dump(),
                    *(p.model_dump() for p in record.members),
                    *generation["actors"],
                ]
                row["actor_states"] = [owner.ledger.driver.state(p) for p in identities]
                if any(s not in {"absent", "different"} for s in row["actor_states"]):
                    row["reason"] = "private-generation-still-live-or-unverifiable"
                    continue
            # The framework rechecks owner identity/revision under its ledger
            # lock. Shared/attached claims only release the dead owner's reference.
            before_path = owner.ledger._path(record.resource_id)
            before = before_path.read_bytes()
            if ResourceRecord.model_validate(json.loads(before)).revision != record.revision:
                raise RuntimeError("Resource changed before recovery; retain the intervening edit")
            backup = folder / (record.resource_id + "-" + record.revision + ".before.json")
            if backup.exists() and backup.read_bytes() != before:
                raise RuntimeError("Recovery before-image differs; preserve the original claim")
            if not backup.exists():
                with backup.open("xb") as stream:
                    stream.write(before)
                    stream.flush()
                    os.fsync(stream.fileno())
            retired = owner.reconcile(
                record.resource_id,
                record.revision,
                "Exact prior owner and all retained private actors are gone, or a departed shared/attached reference is released. Native/cleanup/write barriers remain retained; no operation replayed.",
            )
            row.update(
                action="released-departed-claim",
                before_sha256=hashlib.sha256(before).hexdigest(),
                new_revision=retired.revision,
                recovery_barrier=retired.recovery_barrier,
            )
        report = {
            "state": "observed",
            "actor": owner.identity.model_dump(mode="json"),
            "observations": observations,
            "processes_terminated": False,
            "native_receipts_changed": False,
        }
        durable_json(folder / (uuid.uuid4().hex + ".json"), report)
        return report
    finally:
        lock.__exit__(None, None, None)
