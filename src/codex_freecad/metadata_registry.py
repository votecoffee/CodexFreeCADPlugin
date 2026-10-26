"""Bounded host-registry admission; no operation replay or native-engine imports."""

import threading
import time
from contextlib import ExitStack, contextmanager

from universal_tools.instance_lock import InstanceLock
from universal_tools.management import ManagementRegistry
from universal_tools.models import BrokerError
from universal_tools.resources import ResourceLedger

from .private_directories import ensure_private
from .process_lifetime import ProcessSlots

_gates = {}
_gates_lock = threading.Lock()
ADMISSION_SECONDS = 5


class _PublicationGate:
    def __init__(self, directory):
        self.directory = directory
        self.mutex = threading.RLock()
        self.depth = 0
        self.lease = None

    @contextmanager
    def operation(self, deadline):
        if not self.mutex.acquire(timeout=max(0, deadline - time.monotonic())):
            raise RuntimeError("FreeCAD metadata publication admission exceeded 5 seconds")
        try:
            if self.depth == 0:
                self.lease = ProcessSlots(
                    self.directory / "freecad-metadata-publication",
                    limit=1,
                    timeout=max(0, deadline - time.monotonic()),
                    label="FreeCAD metadata publication admission (5 second deadline)",
                )
                self.lease.__enter__()
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1
                if self.depth == 0:
                    self.lease.__exit__(None, None, None)
                    self.lease = None
        finally:
            self.mutex.release()


def _gate(directory):
    directory = directory.resolve()
    with _gates_lock:
        return _gates.setdefault(directory, _PublicationGate(directory))


class AppManagementRegistry(ManagementRegistry):
    def prepare(self):
        with _gate(self.directory).operation(time.monotonic() + ADMISSION_SECONDS):
            ensure_private(self.directory)
            ensure_private(self.directory / "instances")

    def publish(self, record):
        with _gate(self.directory).operation(time.monotonic() + ADMISSION_SECONDS):
            return super().publish(record)  # Exactly one publication attempt.

    def records(self):
        with _gate(self.directory).operation(time.monotonic() + ADMISSION_SECONDS):
            self.prepare()
            return super().records()


class AppResourceLedger(ResourceLedger):
    @contextmanager
    def _locked(self):
        deadline = time.monotonic() + ADMISSION_SECONDS
        with _gate(self.directory.parent).operation(deadline), ExitStack() as acquired:
            ensure_private(self.directory.parent)
            ensure_private(self.directory)
            lock = self.directory / "ledger.lock"
            if lock.exists() and (
                lock.is_symlink() or getattr(lock.stat(), "st_file_attributes", 0) & 0x400
            ):
                raise ValueError("resource lock must be an ordinary file")
            acquired.enter_context(self._mutex)
            while True:
                try:
                    # Same framework lock/path and transaction bodies; ACL checks are read-only.
                    acquired.enter_context(InstanceLock(lock))
                    break
                except BrokerError as error:
                    if str(error) != "another process already owns this state directory":
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError(
                            "FreeCAD resource metadata admission exceeded 5 seconds"
                        ) from error
                    time.sleep(min(0.02, remaining))
            yield  # Exceptions here propagate; the transaction body is never retried.


def managed_service(*args, registry=None, **kwargs):
    from universal_tools.management import ManagedService

    service = ManagedService(*args, registry=registry, **kwargs)
    service.registry = AppManagementRegistry(registry)
    return service
