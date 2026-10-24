"""App-owned process limits. No native CAD, MCP calls or background startup here."""

import ctypes
import os
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

_jobs = []  # Non-inheritable handles deliberately live until process exit.
METADATA_CONNECTIONS = 16
METADATA_MEMORY_BYTES = 128 * 1024 * 1024
_metadata_memory = False


def run_stdio(server, *, exit_process=os._exit, close_resources=True):
    """CLI boundary: exit after SDK cleanup, even if an orphan reader thread remains.

    The OS closes slot/job handles. This function must not be used by in-process
    clients or libraries; it owns this entire adapter process.
    """
    result = 0
    try:
        server.run(transport="stdio")
    except BaseException:
        result = 1
        traceback.print_exc(file=sys.stderr)
    finally:
        try:
            from .resource_ownership import close_session

            if close_resources:
                close_session()
        except BaseException:
            result = 1
            traceback.print_exc(file=sys.stderr)
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (OSError, ValueError):
                pass
        exit_process(result)


class ProcessSlots:
    """Bound live frontends with OS-owned locks; process death releases a slot."""

    def __init__(self, directory, limit=8, *, timeout=0, label="FreeCAD frontend"):
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("Invalid process slot limit")
        self.directory, self.limit = Path(directory), limit
        if type(timeout) not in {int, float} or not 0 <= timeout <= 5:
            raise ValueError("Invalid admission wait bound")
        self.timeout = timeout
        self.label = label
        self.stream = None
        self.index = None

    def __enter__(self):
        if self.stream is not None:
            raise RuntimeError("Frontend lease is already held")
        deadline = time.monotonic() + self.timeout
        while True:
            if self._acquire():
                return self
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"{self.label} limit reached; close unused connections before retrying"
                )
            time.sleep(min(0.02, remaining))

    def _acquire(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        for index in range(self.limit):
            stream = (self.directory / f"frontend-{index}.lock").open("a+b")
            try:
                if stream.seek(0, 2) == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.stream = stream
                self.index = index
                return True
            except OSError:
                stream.close()
        return False

    def __exit__(self, *_):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
            self.index = None

    @staticmethod
    def occupied(directory, limit=8):
        """Sample only our bounded lock files; never launch or terminate anything."""
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("Invalid process slot limit")
        count = 0
        for index in range(limit):
            path = Path(directory) / f"frontend-{index}.lock"
            if not path.exists():
                continue
            try:
                with path.open("r+b") as stream:
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                count += 1  # An unavailable slot is never counted as free.
        return count


def process_tree_snapshot(*, capture_identity=None):
    """Read members of our retained job, verifying membership and creation identity."""
    result = {
        "state": "unassessed",
        "owned_processes": [],
        "unverified_members": [],
        "maximum_processes": None,
        "inventory_capacity": 32,
        "attached_gui_policy": "external-detach-only",
        "durable_ledger": "framework-0.20-native-claims",
        "shared_last_owner_cleanup": "blocked-awaiting-complete-client-admission-and-drain-fence",
    }
    if os.name != "nt" or not _jobs:
        return result
    from ctypes import wintypes as w

    from .owned_process import _creation_time

    class Members(ctypes.Structure):
        _fields_ = [("assigned", w.DWORD), ("count", w.DWORD), ("ids", ctypes.c_size_t * 32)]

    api = _kernel()
    api.QueryInformationJobObject.argtypes = [
        w.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        w.DWORD,
        ctypes.c_void_p,
    ]
    api.QueryInformationJobObject.restype = w.BOOL
    api.IsProcessInJob.argtypes, api.IsProcessInJob.restype = (
        [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)],
        w.BOOL,
    )
    members = Members()
    if not api.QueryInformationJobObject(
        _jobs[0], 3, ctypes.byref(members), ctypes.sizeof(members), None
    ):
        raise OSError("Cannot inspect our retained process job")
    if members.count > 32:
        raise OSError("Owned process inventory exceeded its bound")
    result["maximum_processes"] = _job_capacity(api, _jobs[0])
    result["memory"] = job_memory_status()
    for pid in members.ids[: members.count]:
        process = api.OpenProcess(0x101000, False, pid)
        if not process:
            result["unverified_members"].append({"pid": pid, "reason": "cannot-pin-job-member"})
            continue
        try:
            ours = w.BOOL()
            if not api.IsProcessInJob(process, _jobs[0], ctypes.byref(ours)):
                raise OSError("Cannot verify process ownership")
            if ours.value:
                member = {
                    "pid": pid,
                    "creation_filetime": _creation_time(api, process),
                    "ownership": "owned-process-tree",
                }
                if capture_identity is not None:
                    try:
                        member["identity"] = capture_identity(process, pid)
                    except OSError:
                        result["unverified_members"].append(
                            {"pid": pid, "reason": "image-identity-unavailable"}
                        )
                        continue
                result["owned_processes"].append(member)
            else:
                result["unverified_members"].append(
                    {"pid": pid, "reason": "membership-changed-before-pin"}
                )
        finally:
            api.CloseHandle(process)
    result["state"] = (
        "sampled-job-membership" if not result["unverified_members"] else "unverified-job-members"
    )
    return result


def _job_capacity(api, job):
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", w.DWORD),
            ("min_working_set", ctypes.c_size_t),
            ("max_working_set", ctypes.c_size_t),
            ("active_processes", w.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", w.DWORD),
            ("scheduling", w.DWORD),
        ]

    limits = Basic()
    if (
        not api.QueryInformationJobObject(job, 2, ctypes.byref(limits), ctypes.sizeof(limits), None)
        or not limits.flags & 0x8
    ):
        raise OSError("Cannot verify the retained job's actual process bound")
    return limits.active_processes


def _kernel():
    from ctypes import wintypes as w

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "GetCurrentProcess": ([], w.HANDLE),
        "GetStdHandle": ([w.DWORD], w.HANDLE),
        "GetFileType": ([w.HANDLE], w.DWORD),
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "DuplicateHandle": (
            [w.HANDLE, w.HANDLE, w.HANDLE, ctypes.POINTER(w.HANDLE), w.DWORD, w.BOOL, w.DWORD],
            w.BOOL,
        ),
        "PeekNamedPipe": (
            [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
            w.BOOL,
        ),
        "CloseHandle": ([w.HANDLE], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def _extended_layout():
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", w.DWORD),
            ("min_working_set", ctypes.c_size_t),
            ("max_working_set", ctypes.c_size_t),
            ("active_processes", w.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", w.DWORD),
            ("scheduling", w.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io_counters", ctypes.c_ulonglong * 6),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    return Extended


def _job_extended(api):
    from ctypes import wintypes as w

    info = _extended_layout()()
    api.QueryInformationJobObject.argtypes = [
        w.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        w.DWORD,
        ctypes.c_void_p,
    ]
    api.QueryInformationJobObject.restype = w.BOOL
    if not api.QueryInformationJobObject(
        _jobs[0], 9, ctypes.byref(info), ctypes.sizeof(info), None
    ):
        raise OSError("Cannot inspect the retained job memory policy")
    return info


def job_memory_status():
    if os.name != "nt" or not _jobs:
        return {"limit_bytes": None, "peak_commit_bytes": None, "state": "unassessed"}
    info = _job_extended(_kernel())
    return {
        "limit_bytes": info.job_memory if info.basic.flags & 0x200 else None,
        "peak_commit_bytes": info.peak_job_memory,
        "state": "metadata-budget" if info.basic.flags & 0x200 else "original-native-policy",
    }


def _set_metadata_memory(limit):
    api = _kernel()
    info = _job_extended(api)
    # Modify only our retained job's memory flag; keep KILL_ON_CLOSE and the
    # original native four-process containment and all other limits intact.
    info.basic.flags = (info.basic.flags | 0x200) if limit else (info.basic.flags & ~0x200)
    info.job_memory = limit or 0
    if not api.SetInformationJobObject(_jobs[0], 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError("Cannot configure the metadata memory budget")
    observed = _job_extended(api)
    if bool(observed.basic.flags & 0x200) != bool(limit) or (
        limit and observed.job_memory != limit
    ):
        raise OSError("Metadata memory budget readback differs")


def start_metadata_memory_budget():
    global _metadata_memory
    if os.name == "nt" and _jobs:
        _set_metadata_memory(METADATA_MEMORY_BYTES)
        _metadata_memory = True


def admit_native_memory():
    """Only after acquiring the existing single native lease, before dispatch.

    Native CAD retains its previous memory policy. No new memory limit is imposed
    on FreeCAD, user GUIs or attached/shared processes. The root still owns its job.
    """
    global _metadata_memory
    if _metadata_memory:
        _set_metadata_memory(None)
        _metadata_memory = False


def _make_job(api, limit):

    job = api.CreateJobObjectW(None, None)
    if not job:
        raise OSError("Cannot create FreeCAD process ownership job")
    info = _extended_layout()()
    info.basic.flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS
    info.basic.active_processes = limit
    if not api.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        api.CloseHandle(job)
        raise OSError("Cannot configure FreeCAD process limits")
    return job


def _own_job(api, limit):
    job = _make_job(api, limit)
    if not api.AssignProcessToJobObject(job, api.GetCurrentProcess()):
        api.CloseHandle(job)
        raise OSError("Cannot establish FreeCAD process ownership; no workers were started")
    _jobs.append(job)


def _watch_disconnect(api, stop, pipe, parent, *, grace=10, terminate=os._exit):
    """Observe the wire without consuming bytes, even after SDK fd diversion.

    A synchronous PeekNamedPipe can block behind the SDK's ReadFile. The
    independent parent-only guard must never share this thread or its handles.
    """
    try:
        while not stop.wait(0.25):
            parent_gone = api.WaitForSingleObject(parent, 0) in {0, 0xFFFFFFFF}
            broken_pipe = False
            if pipe and not api.PeekNamedPipe(pipe, None, 0, None, None, None):
                broken_pipe = True  # Lost/invalid observation also fails closed.
            if parent_gone or broken_pipe:
                # SDK/lifespan cleanup gets a bounded grace period; no receipt is acknowledged.
                if not stop.wait(grace):
                    terminate(1)
                return
    finally:
        if pipe:
            api.CloseHandle(pipe)
        api.CloseHandle(parent)


def _watch_parent(api, stop, parent, *, grace=10, terminate=os._exit):
    """Pin parent death independently of synchronous pipe I/O or inherited writers."""
    try:
        while not stop.wait(0.25):
            if api.WaitForSingleObject(parent, 0) in {0, 0xFFFFFFFF}:
                if not stop.wait(grace):
                    terminate(1)
                return
    finally:
        api.CloseHandle(parent)


def _start_guards(
    api, stopped, pipe, parent, *, grace=10, terminate=os._exit, thread_factory=threading.Thread
):
    """Take ownership of these handles, including partial thread-start failures."""
    from ctypes import wintypes as w

    parent_copy = w.HANDLE()
    watchers = []
    started = []
    try:
        owner = api.GetCurrentProcess()
        if not api.DuplicateHandle(owner, parent, owner, ctypes.byref(parent_copy), 0, False, 2):
            raise OSError("Cannot independently observe the FreeCAD frontend parent")
        options = {"grace": grace, "terminate": terminate}
        watchers = [
            thread_factory(
                target=_watch_parent,
                args=(api, stopped, parent_copy.value),
                kwargs=options,
                daemon=True,
            ),
            thread_factory(
                target=_watch_disconnect,
                args=(api, stopped, pipe, parent),
                kwargs=options,
                daemon=True,
            ),
        ]
        for watcher in watchers:
            watcher.start()
            started.append(watcher)
        return watchers
    except BaseException:
        stopped.set()
        for watcher in started:
            watcher.join(timeout=1)
        if not started and parent_copy.value:
            api.CloseHandle(parent_copy.value)
        if len(started) < 2:
            if pipe:
                api.CloseHandle(pipe)
            api.CloseHandle(parent)
        raise


@contextmanager
def process_lifetime(*, stdio=False, limit=32):
    """Windows descendants die with this owner; stdio EOF/parent exit is bounded.

    An explicitly started HTTP host is the root owner. Its lifetime does not follow
    an installer parent. Existing external FreeCAD GUIs are never assigned here.
    Non-Windows process-tree acceptance is not implemented.
    """
    if os.name != "nt":
        yield
        return
    api = _kernel()
    if not _jobs:
        _own_job(api, limit)
    stopped, watchers = threading.Event(), []
    if stdio:
        from ctypes import wintypes as w

        parent = api.OpenProcess(0x100000, False, os.getppid())  # SYNCHRONIZE; pin identity once.
        if not parent:
            raise OSError("Cannot observe the FreeCAD frontend parent")
        pipe = w.HANDLE()
        wire = api.GetStdHandle(w.DWORD(-10).value)
        if api.GetFileType(wire) == 3:  # FILE_TYPE_PIPE; interactive consoles have no wire.
            owner = api.GetCurrentProcess()
            if not api.DuplicateHandle(owner, wire, owner, ctypes.byref(pipe), 0, False, 2):
                api.CloseHandle(parent)
                raise OSError("Cannot observe the FreeCAD frontend input pipe")
        watchers = _start_guards(api, stopped, pipe.value, parent)
    try:
        yield
    finally:
        stopped.set()
        for watcher in watchers:
            watcher.join(timeout=1)
