"""Source-only lifecycle checks: no process spawning, MCP or native CAD."""

import threading
from contextlib import ExitStack
from types import SimpleNamespace

import pytest

from codex_freecad.process_lifetime import (
    COMPAT_METADATA_CONNECTIONS,
    EXPANDED_METADATA_MEMORY_BYTES,
    METADATA_CONNECTIONS,
    METADATA_MEMORY_BYTES,
    ProcessSlots,
    _own_job,
    _start_guards,
    _watch_disconnect,
    _watch_parent,
    metadata_commit_budget,
    metadata_slot_memory,
    run_stdio,
    start_metadata_memory_budget,
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


def test_shared_metadata_pool_counts_compatible_owners_and_reconnects(tmp_path):
    directory = tmp_path / "metadata-frontdoors-v2"
    with ExitStack() as old, ExitStack() as new:
        previous = [old.enter_context(ProcessSlots(directory, limit=16)) for _ in range(16)]
        current = [
            new.enter_context(ProcessSlots(directory, limit=METADATA_CONNECTIONS))
            for _ in range(METADATA_CONNECTIONS - 16)
        ]
        assert [p.index for p in previous] == list(range(16))
        assert [p.index for p in current] == list(range(16, 48))
        assert ProcessSlots.occupied_indices(directory, limit=48) == list(range(48))
        with pytest.raises(RuntimeError, match="limit=48"):
            ProcessSlots(directory, limit=48).__enter__()
        assert ProcessSlots.occupied(directory, limit=16) == 16  # Old observer's limited view.
        previous[0].__exit__()
        with ProcessSlots(directory, limit=48) as replacement:
            assert replacement.index == 0
            assert metadata_slot_memory(replacement.index) == METADATA_MEMORY_BYTES
    assert ProcessSlots.occupied(directory, limit=48) == 0


def test_metadata_reservations_include_old_slots_and_lower_cost_expansion():
    assert COMPAT_METADATA_CONNECTIONS == 16
    assert metadata_commit_budget() == 5 * 1024**3
    assert sum(metadata_slot_memory(i) for i in range(24)) == 2816 * 1024**2
    assert all(metadata_slot_memory(i) == METADATA_MEMORY_BYTES for i in range(16))
    assert all(metadata_slot_memory(i) == EXPANDED_METADATA_MEMORY_BYTES for i in range(16, 48))


def test_admission_reports_occupied_tiers_including_compatible_and_legacy_owners(
    tmp_path, monkeypatch
):
    from codex_freecad import offline_session

    with ExitStack() as stack:
        for _ in range(16):
            stack.enter_context(ProcessSlots(tmp_path / "metadata-frontdoors-v2", limit=16))
        lease = stack.enter_context(ProcessSlots(tmp_path / "metadata-frontdoors-v2", limit=48))
        stack.enter_context(ProcessSlots(tmp_path / "frontends", limit=4))
        monkeypatch.setattr(offline_session, "_root_state", tmp_path)
        monkeypatch.setattr(offline_session, "_root_limit", 4)
        monkeypatch.setattr(offline_session, "_root_lease", lease)
        report = offline_session.connection_admission()
        assert report["slot"] == 16 and report["metadata_occupied"] == 17
        assert report["metadata_occupied_slots"] == list(range(17))
        assert report["metadata_occupied_commit_reservation_bytes"] == 2144 * 1024**2
        assert report["metadata_commit_reservation_bytes"] == 5 * 1024**3
        assert report["metadata_memory_limit_bytes"] == 96 * 1024**2
        assert report["expected_steady_connections"] == report["expected_reconnect_overlap"] == 24
        assert report["legacy_occupied"] == 1 and report["native_occupied"] == 0


@pytest.mark.parametrize("index", [-1, 48, True, 16.0, "16"])
def test_unreviewed_metadata_slot_is_rejected(index):
    with pytest.raises(ValueError, match="Invalid shared metadata slot"):
        metadata_slot_memory(index)


@pytest.mark.parametrize("limit", [0, 1, 96.0 * 1024**2, True, 256 * 1024**2])
def test_unreviewed_metadata_reservation_is_rejected_without_job_changes(limit):
    with pytest.raises(ValueError, match="Unreviewed metadata memory reservation"):
        start_metadata_memory_budget(limit)


def test_metadata_admission_wait_is_bounded_and_does_not_change_capacity(tmp_path):
    held = ProcessSlots(tmp_path, limit=1).__enter__()
    with pytest.raises(RuntimeError, match="limit reached"):
        ProcessSlots(tmp_path, limit=1, timeout=0.02).__enter__()
    release = threading.Timer(0.02, held.__exit__)
    release.start()
    try:
        with ProcessSlots(tmp_path, limit=1, timeout=1):
            assert ProcessSlots.occupied(tmp_path, limit=1) == 1
    finally:
        release.join(timeout=1)
        held.__exit__()


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
