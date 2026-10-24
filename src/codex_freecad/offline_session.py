"""Single-process offline admission and identity; no child resources or CAD state."""

import threading
from contextlib import contextmanager
from pathlib import Path

from . import __package_version__, __version__

_root_state = None
_root_limit = 1


@contextmanager
def root_lifetime(state, *, process_limit=1):
    """Early bootstrap guard, before dependency hashing/import or protocol startup."""
    global _root_state, _root_limit
    from .process_lifetime import ProcessSlots, _jobs, process_lifetime

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
    with (
        ProcessSlots(state / "frontends", limit=4),
        process_lifetime(stdio=True, limit=process_limit),
    ):
        _root_state = state
        _root_limit = process_limit
        try:
            yield
        finally:
            _root_state = None
            _root_limit = 1


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
        with ProcessSlots(state / "history-admission", limit=1, timeout=5):
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
