"""Source-only lifecycle checks: no process spawning, MCP or native CAD."""

from types import SimpleNamespace

import pytest

from codex_freecad.process_lifetime import ProcessSlots, _own_job, _watch_disconnect, run_stdio


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
