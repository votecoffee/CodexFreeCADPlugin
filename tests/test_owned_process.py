"""Pure stubs only: no Win32 calls, MCP workers, subprocesses or native apps."""

import io
from types import SimpleNamespace

import pytest

import codex_freecad.owned_process as owned
import codex_freecad.resource_ownership as resources
from codex_freecad.client import HeadlessClient, LiveClient
from codex_freecad.engine import CadError


class Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def setup_spawn(monkeypatch, *, accepted=True):
    events, options = [], {}
    process = SimpleNamespace(pid=31, _handle=123)
    process.poll = lambda: None if "kill" not in events else 1
    process.kill = lambda: events.append("kill")
    process.wait = lambda **kwargs: events.append("wait")

    def popen(command, **kwargs):
        events.append("popen-suspended")
        options.update(kwargs)
        return process

    api = SimpleNamespace(
        AssignProcessToJobObject=lambda *args: events.append("assign") or accepted,
        CloseHandle=lambda handle: events.append(("close", handle)) or True,
    )

    class Claim:
        resource_id = "a" * 32

        def __init__(self, owner=None):
            events.append("reserve")

        def bind(self, process):
            events.append("durable-bind")

        def failed(self, reason):
            events.append("barrier")

        def closed(self):
            events.append("retire")

    monkeypatch.setattr(resources, "NativeClaim", Claim)
    monkeypatch.setattr(owned, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(owned, "_jobs", [1])
    monkeypatch.setattr(owned, "_kernel", lambda: api)
    monkeypatch.setattr(owned, "_make_job", lambda *args: 99)
    monkeypatch.setattr(owned, "subprocess", SimpleNamespace(Popen=popen))
    monkeypatch.setattr(owned, "_creation_time", lambda *args: events.append("identity") or 200)
    monkeypatch.setattr(owned, "_resume_created_process", lambda *args: events.append("resume"))
    return events, options, process


def test_worker_identity_and_containment_precede_execution(monkeypatch):
    events, options, process = setup_spawn(monkeypatch)
    result = owned.spawn_owned(["disposable-stub"])
    assert events == ["reserve", "popen-suspended", "identity", "assign", "durable-bind", "resume"]
    assert options["creationflags"] & 4 and options["creationflags"] & 0x08000000
    assert options["close_fds"] is True
    assert result.process is process and result.identity["creation_filetime"] == 200
    result.close_owned_tree()
    result.close_owned_tree()
    assert events.count(("close", 99)) == 1


def test_failed_assignment_never_resumes_and_uses_retained_process(monkeypatch):
    events, _, process = setup_spawn(monkeypatch, accepted=False)
    with pytest.raises(OSError, match="containment"):
        owned.spawn_owned(["disposable-stub"])
    assert events == [
        "reserve",
        "popen-suspended",
        "identity",
        "assign",
        "barrier",
        ("close", 99),
        "kill",
        "wait",
    ]
    assert process.poll() == 1


def test_resume_failure_retains_original_error_and_closes_owned_tree(monkeypatch):
    events, _, _ = setup_spawn(monkeypatch)

    def failed(*args):
        raise OSError("Synthetic identity change")

    monkeypatch.setattr(owned, "_resume_created_process", failed)
    with pytest.raises(OSError, match="identity change"):
        owned.spawn_owned(["disposable-stub"])
    assert events[-3:] == [("close", 99), "kill", "wait"]


def test_failed_job_close_retains_identity_and_handle():
    result = owned.OwnedProcess(
        SimpleNamespace(pid=31), job=99, api=SimpleNamespace(CloseHandle=lambda handle: False)
    )
    with pytest.raises(OSError, match="retained"):
        result.close_owned_tree()
    assert result.job == 99 and result.identity["cleanup"] == "uncertain"


def test_attached_gui_cleanup_never_contacts_or_terminates_it(tmp_path):
    client = LiveClient(tmp_path / "nonexistent.json")
    client.opener = SimpleNamespace(open=lambda *args: pytest.fail("Attached GUI was contacted"))
    client.close()
    assert client.resource_status()["ownership"] == "attached-user-owned"
    assert client.resource_status()["terminate_allowed"] is False


def test_reader_cleanup_is_bounded_and_refuses_new_workers(tmp_path, monkeypatch):
    import codex_freecad.client as client_module

    monkeypatch.setattr(client_module, "atexit", SimpleNamespace(register=lambda *args: None))
    client = HeadlessClient(tmp_path)
    streams = [io.StringIO() for _ in range(3)]
    process = SimpleNamespace(
        pid=31, stdin=streams[0], stdout=streams[1], stderr=streams[2], poll=lambda: 0
    )
    tree = owned.OwnedProcess(
        process, job=99, creation=200, api=SimpleNamespace(CloseHandle=lambda handle: True)
    )
    client.process = tree
    waits = []
    reader = SimpleNamespace(join=lambda timeout: waits.append(timeout), is_alive=lambda: True)
    client.readers = [(reader, streams[1])]
    client.close()
    assert client.failed and client.process is tree
    assert not streams[1].closed and all(0 <= t <= 2 for t in waits)
    with pytest.raises(CadError, match="disabled"):
        client._start()
    reader.is_alive = lambda: False
    client.close()
    assert client.process is None and streams[1].closed
    assert client.resource_status()["reader_cleanup"] == "closed"


@pytest.mark.parametrize(
    "thread_pid,creation,accepted", [(31, 200, True), (31, 201, False), (999, 200, False)]
)
def test_resume_revalidates_thread_owner_creation_identity(
    monkeypatch, thread_pid, creation, accepted
):
    events = []

    def first(snapshot, pointer):
        pointer._obj.owner, pointer._obj.id = 31, 77
        return True

    api = SimpleNamespace(
        **{
            name: Function(callback)
            for name, callback in {
                "CreateToolhelp32Snapshot": lambda *args: 88,
                "Thread32First": first,
                "Thread32Next": lambda *args: False,
                "OpenThread": lambda *args: 77,
                "GetProcessIdOfThread": lambda *args: thread_pid,
                "OpenProcess": lambda *args: 33,
                "ResumeThread": lambda *args: events.append("resume") or 1,
                "CloseHandle": lambda handle: events.append(("close", handle)) or True,
            }.items()
        }
    )
    monkeypatch.setattr(owned, "_creation_time", lambda *args: creation)
    process = SimpleNamespace(pid=31, poll=lambda: None)
    if accepted:
        owned._resume_created_process(api, process, 200)
    else:
        with pytest.raises(OSError, match="identity"):
            owned._resume_created_process(api, process, 200)
    assert ("resume" in events) is accepted
    assert ("close", 77) in events and ("close", 88) in events


def test_reader_start_failure_closes_new_owned_worker(tmp_path, monkeypatch):
    import codex_freecad.client as client_module

    monkeypatch.setattr(client_module, "atexit", SimpleNamespace(register=lambda *args: None))
    client = HeadlessClient(tmp_path)
    closed = []
    process = SimpleNamespace(
        pid=31, stdin=io.StringIO(), stdout=io.StringIO(), stderr=io.StringIO(), poll=lambda: 0
    )
    tree = owned.OwnedProcess(
        process,
        job=99,
        creation=200,
        api=SimpleNamespace(CloseHandle=lambda handle: closed.append(handle) or True),
    )
    monkeypatch.setattr(owned, "spawn_owned", lambda *args, **kwargs: tree)
    monkeypatch.setattr(resources, "api_owner", lambda *args: (SimpleNamespace(), False))
    monkeypatch.setattr(client_module, "find_freecad_cmd", lambda *args: "disposable-stub")

    class FailedReader:
        ident = None

        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("Synthetic reader startup failure")

        def is_alive(self):
            return False

        def join(self, **kwargs):
            pytest.fail("Unstarted thread must not be joined")

    monkeypatch.setattr(client_module, "threading", SimpleNamespace(Thread=FailedReader))
    with pytest.raises(RuntimeError, match="reader startup"):
        client._start()
    assert closed == [99] and client.process is None
