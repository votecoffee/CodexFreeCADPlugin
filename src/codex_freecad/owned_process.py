"""Exclusive native worker ownership, separate from attached user applications."""

import ctypes
import os
import subprocess
import uuid

from .process_lifetime import _jobs, _kernel, _make_job, _own_job


class OwnedProcess:
    def __init__(self, process, *, api=None, job=None, creation=None, claim=None):
        self.process, self.api, self.job = process, api, job
        self.claim = claim
        self.identity = {
            "resource_id": claim.resource_id if claim else uuid.uuid4().hex,
            "ownership": "exclusive-launched",
            "pid": process.pid,
            "creation_filetime": creation,
            "containment": "windows-job" if job else "unassessed-platform",
            "native_dirty_state": "not-inspected",
            "ledger_resource_id": claim.resource_id if claim else None,
        }

    def __getattr__(self, name):
        return getattr(self.process, name)

    def close_owned_tree(self):
        if self.job is not None:
            # Only this worker's retained job handle. No PID-based process-tree killing.
            if not self.api.CloseHandle(self.job):
                self.identity["cleanup"] = "uncertain"
                raise OSError("Cannot close the retained owned-worker job")
            self.job = None
            self.identity["cleanup"] = "closed"
        if self.claim is not None:
            self.claim.closed()
            self.claim = None


def _creation_time(api, handle):
    from ctypes import wintypes as w

    api.GetProcessTimes.argtypes = [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)]
    api.GetProcessTimes.restype = w.BOOL
    times = [w.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
        raise OSError("Cannot establish owned worker creation identity")
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def _resume_created_process(api, process, creation):
    from ctypes import wintypes as w

    class ThreadEntry(ctypes.Structure):
        _fields_ = [
            ("size", w.DWORD),
            ("usage", w.DWORD),
            ("id", w.DWORD),
            ("owner", w.DWORD),
            ("priority", w.LONG),
            ("delta", w.LONG),
            ("flags", w.DWORD),
        ]

    api.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    api.CreateToolhelp32Snapshot.restype = w.HANDLE
    for name in ("Thread32First", "Thread32Next"):
        function = getattr(api, name)
        function.argtypes, function.restype = [w.HANDLE, ctypes.POINTER(ThreadEntry)], w.BOOL
    api.OpenThread.argtypes, api.OpenThread.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    api.ResumeThread.argtypes, api.ResumeThread.restype = [w.HANDLE], w.DWORD
    api.GetProcessIdOfThread.argtypes, api.GetProcessIdOfThread.restype = [w.HANDLE], w.DWORD
    snapshot = api.CreateToolhelp32Snapshot(4, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Cannot identify the suspended owned worker thread")
    try:
        entry = ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        more = api.Thread32First(snapshot, ctypes.byref(entry))
        while more:
            if entry.owner == process.pid:
                thread = api.OpenThread(2 | 0x0800, False, entry.id)  # Suspend/resume + query.
                if not thread:
                    raise OSError("Cannot retain the owned worker thread")
                try:
                    if api.GetProcessIdOfThread(thread) != process.pid:
                        raise OSError("Owned worker thread identity changed")
                    owner = api.OpenProcess(0x1000, False, process.pid)
                    if not owner:
                        raise OSError("Cannot pin the owned thread's process identity")
                    try:
                        if _creation_time(api, owner) != creation or process.poll() is not None:
                            raise OSError("Owned worker creation identity changed")
                    finally:
                        api.CloseHandle(owner)
                    if api.ResumeThread(thread) != 1:
                        raise OSError(
                            "Owned worker did not resume from its initial suspended state"
                        )
                    return
                finally:
                    api.CloseHandle(thread)
            more = api.Thread32Next(snapshot, ctypes.byref(entry))
        raise OSError("Suspended owned worker thread was not found")
    finally:
        api.CloseHandle(snapshot)


def spawn_owned(command, *, resource_owner=None, **options):
    """Hold the new worker suspended until assigned to its exclusive lifetime job."""
    if os.name != "nt":
        raise OSError("Managed native process containment currently requires Windows")
    from .resource_ownership import NativeClaim

    claim = NativeClaim(resource_owner)
    api = _kernel()
    if not _jobs:
        _own_job(api, 32)  # Contain startup failures/death before the child-job assignment.
    job, process = _make_job(api, 8), None
    try:
        options["creationflags"] = options.get("creationflags", 0) | 4 | 0x08000000
        options["close_fds"] = True  # No inherited control/job handles or new consoles.
        process = subprocess.Popen(command, **options)
        handle = int(process._handle)  # Retained Popen process handle pins the creation identity.
        creation = _creation_time(api, handle)
        if not api.AssignProcessToJobObject(job, handle):
            raise OSError("Owned worker containment failed before execution")
        claim.bind(
            process
        )  # Durable identity must precede execution on the existing pipe transport.
        _resume_created_process(api, process, creation)
        return OwnedProcess(process, api=api, job=job, creation=creation, claim=claim)
    except BaseException:
        try:
            claim.failed(
                "Native launch/initialization did not complete; preserve this reservation and inspect the owned process"
            )
        finally:
            api.CloseHandle(job)
            if process is not None:
                if process.poll() is None:
                    process.kill()  # Popen uses the retained handle, never a recycled PID.
                process.wait(timeout=3)
        raise
