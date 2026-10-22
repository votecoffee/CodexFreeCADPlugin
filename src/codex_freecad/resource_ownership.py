"""Framework resource records; never import this module into FreeCAD's native engine."""

import threading
from contextlib import contextmanager

APPLICATION_ID = "freecad-mcp-server"
_owner = None
_references = []
_lock = threading.RLock()


def create_owner(registry=None):
    try:
        from universal_tools import __version__ as framework_version
        from universal_tools.resources import ResourceLedger
    except ImportError as exc:
        raise RuntimeError(
            "Managed FreeCAD requires the verified shared framework 0.20 runtime"
        ) from exc
    if framework_version != "0.20.0":
        raise RuntimeError("Managed FreeCAD requires the exact verified framework 0.20.0")
    return ResourceLedger(registry, max_active_per_app=32).owner(APPLICATION_ID)


def current_owner():
    with _lock:
        if _owner is None:
            raise RuntimeError(
                "Configure a resource owner in the surviving FreeCAD adapter before launch"
            )
        return _owner


def api_owner(registry=None):
    """The caller's real, surviving process owns API resources, never a helper PID."""
    with _lock:
        return (_owner, False) if _owner is not None else (create_owner(registry), True)


@contextmanager
def resource_session(registry=None, *, owner=None):
    global _owner
    with _lock:
        if _owner is not None:
            raise RuntimeError("This process already has a resource supervisor generation")
        _owner = owner or create_owner(registry)
    try:
        yield _owner
    finally:
        close_session()


def close_session():
    global _owner
    with _lock:
        if _owner is None:
            return
        for resource_id in list(_references):
            _owner.release_attachment(resource_id)  # Shared endpoint references only.
            _references.remove(resource_id)
        _owner.close()  # Barriers/unknown outcomes refuse; no automatic reconciliation.
        _owner = None


def supervisor_status():
    with _lock:
        if _owner is None:
            return {"state": "unconfigured"}
        records = [r for r in _owner.ledger.records() if r.app_id == APPLICATION_ID]
        return {
            "supervisor": _owner.identity.model_dump(mode="json"),
            "owner_id": _owner.owner_id,
            "records": len(records),
            "unretired": sum(r.state not in {"released", "terminated", "failed"} for r in records),
            "recovery_barriers": sum(bool(r.recovery_barrier) for r in records),
            "coverage": "native workers/attachments; SDK launcher registration pending",
        }


def share_supervisor(identity):
    """Record a frontend reference, without acquiring termination rights over its host."""
    owner = current_owner()
    record = owner.remember_process(
        identity["pid"], "FreeCAD shared host reference", ownership="shared", kind="app-host"
    )
    if record.process.model_dump(mode="json") != identity:
        owner.set_recovery_barrier(record.resource_id, "Shared endpoint creation identity changed")
        raise RuntimeError(
            "FreeCAD host identity changed; do not reconnect or reroute automatically"
        )
    _references.append(record.resource_id)
    return record


class NativeClaim:
    def __init__(self, owner=None):
        self.owner = owner or current_owner()
        self.record = self.owner.begin_launch(
            "FreeCADCmd native worker", kind="native-cad", cleanup_mode="report"
        )
        self.resource_id = self.record.resource_id
        self.owner.set_recovery_barrier(
            self.resource_id,
            "Native document/write state requires app-owned inspection; manager termination is prohibited",
        )

    def bind(self, process):
        bound = self.owner.bind_process(self.resource_id, process.pid)
        observed = self.owner.ledger.driver.capture_handle(int(process._handle), process.pid)
        if bound.process.model_dump(mode="json") != observed:
            self.failed("Native process identity changed before execution")
            raise RuntimeError("Native resource identity changed before execution")
        self.record = bound
        return bound

    def failed(self, reason):
        self.owner.set_recovery_barrier(self.resource_id, reason)

    def closed(self):
        record = self.owner.ledger.get(self.resource_id)
        if record.process is None or self.owner.ledger.driver.state(
            record.process.model_dump()
        ) not in {"absent", "different"}:
            self.failed("Native process closure is unverified; retain the original record")
            raise RuntimeError("Native resource closure is unverified")
        self.record = self.owner.reconcile(
            self.resource_id,
            record.revision,
            "Observed the exact private process exit after app-owned teardown; native/write barriers remain retained",
        )


class Attachment:
    def __init__(self, pid, owner=None):
        self.owner = owner or current_owner()
        self.record = self.owner.remember_process(
            pid, "FreeCAD user GUI attachment", ownership="attached", kind="native-cad"
        )

    def verify(self, pid):
        identity = self.record.process.model_dump(mode="json")
        if identity["pid"] != pid or self.owner.ledger.driver.state(identity) != "alive":
            self.owner.set_recovery_barrier(
                self.record.resource_id, "Attached GUI identity changed or is unverifiable"
            )
            raise RuntimeError("Attached GUI identity changed; inspect the original session")

    def close(self):
        self.owner.release_attachment(self.record.resource_id)

    def uncertain(self):
        self.owner.set_recovery_barrier(
            self.record.resource_id,
            "Live bridge reply was lost; inspect the intended GUI before further writes",
        )
