import hashlib
import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "freecad_maintenance",
    Path(__file__).parents[1] / "framework-host/src/freecad_mcp_host/maintenance.py",
)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


@pytest.fixture
def state(tmp_path):
    with closing(sqlite3.connect(tmp_path / "ownership.sqlite3")) as db:
        db.executescript(
            "CREATE TABLE contexts(service_id,context_id,state); CREATE TABLE resources(resource_key);"
        )
    with closing(sqlite3.connect(tmp_path / "writes.sqlite3")) as db:
        db.execute("CREATE TABLE requests(request_id,status)")
    return tmp_path


def hashes(state):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in state.glob("*.sqlite3")
    }


def test_idle_guard_preserves_completed_receipts_and_database_bytes(state):
    with closing(sqlite3.connect(state / "writes.sqlite3")) as db:
        db.execute("INSERT INTO requests VALUES ('old-completed-id','completed')")
        db.commit()
    before = hashes(state)
    result = maintenance.require_idle(state)
    assert result["idle"] and result["completed_writes"] == 1
    assert hashes(state) == before


@pytest.mark.parametrize("context_state", ["opening", "active", "retiring", "lost"])
def test_retained_or_lost_context_prevents_upgrade_without_clearing_it(state, context_state):
    with closing(sqlite3.connect(state / "ownership.sqlite3")) as db:
        db.execute(
            "INSERT INTO contexts VALUES ('freecad-headless','context-id',?)", (context_state,)
        )
        db.commit()
    before = hashes(state)
    with pytest.raises(ValueError, match="released contexts"):
        maintenance.require_idle(state)
    assert hashes(state) == before


@pytest.mark.parametrize("status", ["in_progress", "uncertain", "failed"])
def test_unresolved_receipt_prevents_upgrade_without_acknowledgment(state, status):
    with closing(sqlite3.connect(state / "writes.sqlite3")) as db:
        db.execute("INSERT INTO requests VALUES ('retained-write-id',?)", (status,))
        db.commit()
    before = hashes(state)
    with pytest.raises(ValueError, match="resolved write outcomes"):
        maintenance.require_idle(state)
    assert hashes(state) == before


def test_orphan_reservation_and_missing_journals_fail_closed(state, tmp_path):
    with closing(sqlite3.connect(state / "ownership.sqlite3")) as db:
        db.execute("INSERT INTO resources VALUES ('native-resource')")
        db.commit()
    with pytest.raises(ValueError, match="released contexts"):
        maintenance.require_idle(state)
    empty = tmp_path / "missing"
    empty.mkdir()
    with pytest.raises(ValueError, match="Cannot inspect"):
        maintenance.require_idle(empty)
    assert not list(empty.iterdir())
