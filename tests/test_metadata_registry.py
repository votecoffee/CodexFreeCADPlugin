"""Source-only short-transaction admission; no native software or process control."""

import threading
from contextlib import contextmanager

import pytest
from universal_tools.management import ManagementRegistry
from universal_tools.models import BrokerError
from universal_tools.resources import ResourceLedger

from codex_freecad.metadata_registry import AppManagementRegistry, AppResourceLedger, _gate


def test_framework_ledger_holder_releases_before_single_transaction_body(tmp_path):
    old = ResourceLedger(tmp_path)
    new = AppResourceLedger(tmp_path)
    ready, entered = threading.Event(), threading.Event()

    def holder():
        with old._locked():
            ready.set()
            assert entered.wait(1)

    thread = threading.Thread(target=holder)
    thread.start()
    assert ready.wait(1)
    release = threading.Timer(0.03, entered.set)
    release.start()
    try:
        with new._locked():
            assert entered.is_set()
    finally:
        release.join(timeout=1)
        thread.join(timeout=1)
    assert not thread.is_alive()


def test_known_lock_error_in_body_is_never_replayed(tmp_path):
    calls = []
    with pytest.raises(BrokerError, match="another process"):
        with AppResourceLedger(tmp_path)._locked():
            calls.append("body")
            raise BrokerError("another process already owns this state directory")
    assert calls == ["body"]


def test_unexpected_admission_error_is_not_retried(tmp_path, monkeypatch):
    calls = []

    @contextmanager
    def denied(self):
        calls.append("enter")
        raise PermissionError("Uncertain external permissions")
        yield

    monkeypatch.setattr(ResourceLedger, "_locked", denied)
    with pytest.raises(PermissionError):
        with AppResourceLedger(tmp_path)._locked():
            pytest.fail("Body admitted")
    assert calls == ["enter"]


def test_registry_publication_failure_is_not_retried_and_releases_gate(tmp_path, monkeypatch):
    calls = []

    def denied(self, record):
        calls.append(record)
        raise PermissionError("Uncertain publication")

    monkeypatch.setattr(ManagementRegistry, "publish", denied)
    registry = AppManagementRegistry(tmp_path)
    with pytest.raises(PermissionError):
        registry.publish("one")
    assert calls == ["one"] and _gate(registry.directory).depth == 0


def test_nested_registry_prepare_uses_one_reentrant_publication_gate(tmp_path, monkeypatch):
    calls = []

    def prepare(self):
        calls.append(_gate(self.directory).depth)

    def publish(self, record):
        self.prepare()

    monkeypatch.setattr(ManagementRegistry, "prepare", prepare)
    monkeypatch.setattr(ManagementRegistry, "publish", publish)
    registry = AppManagementRegistry(tmp_path)
    registry.publish(None)
    assert calls == [2] and _gate(registry.directory).depth == 0


def test_contended_original_ledger_deadline_never_enters_body(tmp_path, monkeypatch):
    from codex_freecad import metadata_registry

    monkeypatch.setattr(metadata_registry, "ADMISSION_SECONDS", 0.02)
    with ResourceLedger(tmp_path)._locked():
        with pytest.raises(RuntimeError, match="resource metadata admission"):
            with AppResourceLedger(tmp_path)._locked():
                pytest.fail("Body ran before original framework lock admission")
    assert _gate(tmp_path.resolve()).depth == 0
