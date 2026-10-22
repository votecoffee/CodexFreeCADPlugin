"""Source-only lifecycle checks: no process spawning, MCP or native CAD."""

import threading
from types import SimpleNamespace

import pytest

from codex_freecad.process_lifetime import (
    ProcessSlots,
    _own_job,
    _start_guards,
    _watch_disconnect,
    _watch_parent,
    run_stdio,
)


def test_stdio_boundary_exits_after_adapter_cleanup_without_spawning_anything():
    events = []
    server = SimpleNamespace(run=lambda **kwargs: events.append("sdk_cleanup_returned"))
    run_stdio(server, exit_process=events.append)
    assert events == ["sdk_cleanup_returned", 0]


def test_stdio_boundary_retains_failure_exit_status(capsys):
    exits = []

    def failed(**kwargs):
        raise RuntimeError("Synthetic adapter error")

    run_stdio(SimpleNamespace(run=failed), exit_process=exits.append)
    assert exits == [1] and "Synthetic adapter error" in capsys.readouterr().err


def test_frontend_slot_limit_and_explicit_release(tmp_path):
    with ProcessSlots(tmp_path, limit=1):
        assert ProcessSlots.occupied(tmp_path, limit=1) == 1
        with pytest.raises(RuntimeError, match="limit reached"):
            with ProcessSlots(tmp_path, limit=1):
                raise AssertionError("Concurrent frontend admitted")
    with ProcessSlots(tmp_path, limit=1):
        pass
    assert ProcessSlots.occupied(tmp_path, limit=1) == 0


def test_invalid_slot_limit_creates_nothing(tmp_path):
    with pytest.raises(ValueError):
        ProcessSlots(tmp_path / "unused", limit=0)
    assert not (tmp_path / "unused").exists()


def test_job_configuration_failure_closes_handle_before_any_assignment():
    closed = []
    api = SimpleNamespace(
        CreateJobObjectW=lambda *args: 42,
        SetInformationJobObject=lambda *args: False,
        CloseHandle=closed.append,
    )
    with pytest.raises(OSError, match="configure"):
        _own_job(api, 32)
    assert closed == [42]


def test_parent_exit_waits_for_grace_and_never_reads_wire_bytes():
    waits, closed, exits = [], [], []

    class Signal:
        def wait(self, timeout):
            waits.append(timeout)
            return False

    api = SimpleNamespace(
        WaitForSingleObject=lambda *args: 0,
        PeekNamedPipe=lambda *args: True,
        CloseHandle=closed.append,
    )
    _watch_disconnect(api, Signal(), 11, 12, grace=10, terminate=exits.append)
    assert waits == [0.25, 10] and exits == [1] and closed == [11, 12]


def test_cleanup_within_grace_avoids_forced_exit():
    outcomes = iter([False, True])
    closed, exits = [], []
    api = SimpleNamespace(
        WaitForSingleObject=lambda *args: 0,
        PeekNamedPipe=lambda *args: True,
        CloseHandle=closed.append,
    )
    _watch_disconnect(
        api, SimpleNamespace(wait=lambda timeout: next(outcomes)), 11, 12, terminate=exits.append
    )
    assert exits == [] and closed == [11, 12]


def test_parent_only_guard_never_calls_pipe_io():
    waits, closed, exits = [], [], []

    def wait(timeout):
        waits.append(timeout)
        return False

    api = SimpleNamespace(
        WaitForSingleObject=lambda *_: 0,
        CloseHandle=closed.append,
        PeekNamedPipe=lambda *_: pytest.fail("Parent guard touched synchronous pipe I/O"),
    )
    _watch_parent(api, SimpleNamespace(wait=wait), 13, terminate=exits.append)
    assert waits == [0.25, 10] and exits == [1] and closed == [13]


def test_blocked_pipe_cannot_hide_parent_death_and_guards_own_distinct_handles():
    stopped = threading.Event()
    pipe_blocked = threading.Event()
    release_pipe = threading.Event()
    parent_dead = threading.Event()
    exited = threading.Event()
    closed = []
    observed = []

    def duplicate(owner, handle, destination, pointer, *_):
        assert handle == 12
        pointer._obj.value = 13
        return True

    def peek(*_):
        pipe_blocked.set()
        release_pipe.wait(2)
        return True

    def terminate(code):
        observed.append(code)
        exited.set()

    api = SimpleNamespace(
        GetCurrentProcess=lambda: 99,
        DuplicateHandle=duplicate,
        WaitForSingleObject=lambda *_: 0 if parent_dead.is_set() else 258,
        PeekNamedPipe=peek,
        CloseHandle=closed.append,
    )
    guards = _start_guards(api, stopped, 11, 12, grace=0.01, terminate=terminate)
    try:
        assert pipe_blocked.wait(1)
        parent_dead.set()
        assert exited.wait(0.75), "Blocked pipe prevented parent-only watchdog"
        assert observed == [1]
    finally:
        stopped.set()
        release_pipe.set()
        for guard in guards:
            guard.join(timeout=1)
    assert sorted(closed) == [11, 12, 13]


@pytest.mark.parametrize("failure", ["duplicate", "first-thread", "second-thread"])
def test_guard_start_failure_closes_untransferred_handles(failure):
    closed = []
    count = [0]

    def duplicate(owner, handle, destination, pointer, *_):
        if failure == "duplicate":
            return False
        pointer._obj.value = 13
        return True

    class Thread:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.index = count[0]
            count[0] += 1

        def start(self):
            if (failure == "first-thread" and self.index == 0) or (
                failure == "second-thread" and self.index == 1
            ):
                raise OSError("Injected thread-start failure")

        def join(self, timeout):
            self.options["target"](*self.options["args"], **self.options["kwargs"])

    api = SimpleNamespace(
        GetCurrentProcess=lambda: 99, DuplicateHandle=duplicate, CloseHandle=closed.append
    )
    with pytest.raises(OSError):
        _start_guards(api, threading.Event(), 11, 12, thread_factory=Thread)
    assert sorted(closed) == ([11, 12] if failure == "duplicate" else [11, 12, 13])
