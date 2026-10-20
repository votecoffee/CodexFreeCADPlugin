"""Read-only upgrade guards; never acknowledge receipts or release native contexts."""

import sqlite3
from contextlib import closing
from pathlib import Path


def journal_status(state):
    state = Path(state).resolve()
    try:
        with closing(
            sqlite3.connect((state / "ownership.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as db:
            contexts = db.execute("SELECT service_id, context_id, state FROM contexts").fetchall()
            resources = db.execute("SELECT count(*) FROM resources").fetchone()[0]
        with closing(
            sqlite3.connect((state / "writes.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as db:
            requests = db.execute(
                "SELECT request_id, status FROM requests WHERE status!='completed'"
            ).fetchall()
            completed = db.execute(
                "SELECT count(*) FROM requests WHERE status='completed'"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise ValueError(
            "Cannot inspect existing journals; preserve and repair the installation"
        ) from exc
    return {
        "idle": not contexts and not resources and not requests,
        "contexts": [
            {"service_id": row[0], "context_id": row[1], "state": row[2]} for row in contexts
        ],
        "resource_reservations": resources,
        "unresolved_writes": [{"request_id": row[0], "status": row[1]} for row in requests],
        "completed_writes": completed,
    }


def require_idle(state):
    result = journal_status(state)
    if not result["idle"]:
        raise ValueError(
            "Upgrade requires released contexts and resolved write outcomes; "
            "save/release work or reconcile it through app administration first. Journals were preserved."
        )
    return result
