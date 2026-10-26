"""Single-process offline admission and identity; no child resources or CAD state."""

import threading
from contextlib import contextmanager
from pathlib import Path

from . import __package_version__, __version__

_root_state = None
_root_limit = 1
_root_lease = None


@contextmanager
def root_lifetime(state, *, process_limit=1):
    """Early bootstrap guard, before dependency hashing/import or protocol startup."""
    global _root_state, _root_limit, _root_lease
    from .process_lifetime import (
        METADATA_CONNECTIONS,
        ProcessSlots,
        _jobs,
        metadata_slot_memory,
        process_lifetime,
        start_metadata_memory_budget,
    )

    state = Path(state).resolve()
    if type(process_limit) is not int or process_limit not in {1, 4}:
        raise ValueError("Choose the offline one-process or native four-process root budget")
    if _root_state is not None:
        if state != _root_state or process_limit != _root_limit:
            raise RuntimeError("Offline state differs from its admitted bootstrap root")
        yield
        return
    if _jobs:
        raise RuntimeError(
            "Offline profile requires a fresh root process with its own one-process job"
        )
    native = process_limit == 4
    # Reuse the SAME pool and slot indices as 101538. Old owners reserve 128 MiB
    # in slots 0..15; additional slots have a reviewed smaller reservation. No
    # overlapping generation can hide behind another pool or erase an old lease.
    directory = state / ("metadata-frontdoors-v2" if native else "frontends")
    lease = ProcessSlots(
        directory,
        limit=METADATA_CONNECTIONS if native else 4,
        label="FreeCAD shared metadata connection (48; native capacity is separate)"
        if native
        else "FreeCAD frontend",
    )
    with (
        lease,
        process_lifetime(stdio=True, limit=process_limit),
    ):
        if native:
            start_metadata_memory_budget(metadata_slot_memory(lease.index))
        _root_state = state
        _root_limit = process_limit
        _root_lease = lease
        try:
            yield
        finally:
            _root_state = None
            _root_limit = 1
            _root_lease = None


def connection_admission():
    from .process_lifetime import (
        COMPAT_METADATA_CONNECTIONS,
        EXPANDED_METADATA_MEMORY_BYTES,
        METADATA_CONNECTIONS,
        METADATA_MEMORY_BYTES,
        METADATA_RECONNECT_CONNECTIONS,
        METADATA_STEADY_CONNECTIONS,
        ProcessSlots,
        metadata_commit_budget,
        metadata_slot_memory,
    )

    if _root_state is None or _root_lease is None:
        return {"state": "not-admitted"}
    native = _root_limit == 4
    occupied = ProcessSlots.occupied_indices(_root_lease.directory, limit=_root_lease.limit)
    return {
        "state": "admitted",
        "pool": str(_root_lease.directory),
        "slot": _root_lease.index,
        "metadata_limit": METADATA_CONNECTIONS if native else 4,
        "metadata_memory_limit_bytes": metadata_slot_memory(_root_lease.index) if native else None,
        "metadata_commit_reservation_bytes": metadata_commit_budget() if native else None,
        "metadata_occupied_commit_reservation_bytes": sum(metadata_slot_memory(i) for i in occupied)
        if native
        else None,
        "metadata_occupied_slots": occupied,
        "metadata_memory_scope": "metadata-only jobs; native admission restores the original memory policy; pre-101538 legacy jobs are separate",
        "compatibility_slots": COMPAT_METADATA_CONNECTIONS if native else None,
        "compatibility_slot_commit_bytes": METADATA_MEMORY_BYTES if native else None,
        "expanded_slot_commit_bytes": EXPANDED_METADATA_MEMORY_BYTES if native else None,
        "expected_steady_connections": METADATA_STEADY_CONNECTIONS if native else None,
        "expected_reconnect_overlap": METADATA_RECONNECT_CONNECTIONS if native else None,
        "accounting_scope": "all versions use metadata-frontdoors-v2 slot locks; slots 0..15 count existing 101538 owners",
        "metadata_occupied": len(occupied),
        "legacy_limit": 4,
        "legacy_occupied": ProcessSlots.occupied(_root_state / "frontends", limit=4),
        "native_limit": 1,
        "native_occupied": ProcessSlots.occupied(_root_state / "native-pilot", limit=1),
        "native_queue_limit": 0,
    }


class Admission:
    def __init__(self):
        self.lock = threading.Lock()

    @contextmanager
    def operation(self):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("Offline request capacity reached; retry after the active read")
        try:
            yield
        finally:
            self.lock.release()


@contextmanager
def offline_session(state, registry, admission):
    from universal_tools.management import (
        ComponentVersion,
        ManagedService,
        ManagedStatus,
        private_directory,
    )
    from universal_tools.resources import durable_json

    from .process_lifetime import ProcessSlots
    from .resource_ownership import resource_session

    # This is the surviving stdio process, not an installer/helper. The root is
    # externally launched; it launches zero children and takes no attachments.
    state = Path(state)
    private_directory(state)
    with root_lifetime(state), resource_session(registry, state=state) as owner:
        folder = state / "sessions"
        private_directory(folder)
        path = folder / (owner.owner_id + ".json")
        record = {
            "schema_version": 1,
            "profile": "direct-standalone-offline",
            "app_version": __version__,
            "app_package_version": __package_version__,
            "owner_id": owner.owner_id,
            "owner": owner.identity.model_dump(mode="json"),
            "state": "active",
            "child_processes": [],
            "native_execution": False,
            "note": "Root identity record; not a child-resource termination authorization",
        }
        with ProcessSlots(
            state / "history-admission",
            limit=1,
            timeout=5,
            label="FreeCAD offline history writer contention (5 second deadline)",
        ):
            if len(list(folder.glob("*.json"))) >= 256:
                raise RuntimeError(
                    "Offline session history full; preserve/archive evidence explicitly"
                )
            if path.exists():
                raise RuntimeError("Offline session generation already exists")
            durable_json(path, record)

        def status():
            from .stable_launcher import deployment_info

            deployment = deployment_info()
            update_pending = bool(
                deployment["selected_package_version"]
                and (
                    deployment["selected_package_version"] != __package_version__
                    or deployment.get("selected_snapshot") != deployment.get("running_snapshot")
                )
            )
            return ManagedStatus(
                state="busy" if admission.lock.locked() else "running",
                message=f"FreeCAD {__version__}; read-only offline profile; zero child processes.",
                active_operations=int(admission.lock.locked()),
                versions={
                    "app": ComponentVersion(
                        installed=deployment["selected_package_version"] or "not-reporting",
                        running=__package_version__,
                        update_pending=update_pending,
                    )
                },
                restart_allowed=False,
                restart_reason="Offline root is owned by its calling client; close that connection.",
            )

        outcome = "closed"
        try:
            with ManagedService(
                "freecad-mcp-server",
                "FreeCADMCPServer (offline)",
                status,
                plugin_id="freecad-modeling@freecad-development",
                registry=registry,
            ):
                yield record
        except BaseException:
            outcome = "failed"
            raise
        finally:
            durable_json(path, {**record, "state": outcome})


def run_offline(server, session, *, exit_process):
    from .process_lifetime import run_stdio

    result = []
    try:
        with session:
            # Defer the hard process exit until manager/identity/slot cleanup ran.
            run_stdio(server, exit_process=result.append)
    finally:
        exit_process(result[0] if result else 1)
