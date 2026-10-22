"""Real private management HTTP tests; restart effects touch only a fixture database."""

import argparse
import asyncio
import concurrent.futures
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from freecad_mcp_host.management import PLUGIN_ID, RESTART_REASON, ReportingBackend, StatusCache
from mcp.types import CallToolResult, TextContent
from universal_tools.framework import ApplicationBackend
from universal_tools.management import (
    ManagedService,
    ManagedStatus,
    ManagementClient,
    RestartResult,
)


def initialize(root):
    root.mkdir(parents=True)
    with closing(sqlite3.connect(root / "ownership.sqlite3")) as db:
        db.executescript(
            "CREATE TABLE contexts(service_id,context_id,state); CREATE TABLE resources(resource_key);"
        )
    with closing(sqlite3.connect(root / "writes.sqlite3")) as db:
        db.execute("CREATE TABLE requests(request_id,status)")


def restart(client, row, key=None):
    return client.restart(
        row["app_id"], row["instance_id"], row["revision"], key or secrets.token_hex(16)
    )


async def concurrent_calls(cache):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []
    original = CallToolResult(
        content=[TextContent(type="text", text="opaque CAD result")],
        structuredContent={"revision": "unchanged", "value": 9223372036854775807},
    )

    async def invoke(_, name, arguments, *, relay=None):
        calls.append((name, arguments, relay))
        entered.set()
        await release.wait()
        return original

    backend = ReportingBackend(SimpleNamespace(_engine=object(), tray_status=cache))
    with patch.object(ApplicationBackend, "invoke", invoke):
        first = asyncio.create_task(backend.invoke("call_write_tool", {"opaque": 1}, relay="relay"))
        await entered.wait()
        entered.clear()
        second = asyncio.create_task(backend.invoke("call_read_tool", {"opaque": 2}))
        await entered.wait()
        assert cache.snapshot().active_operations == 2
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        assert cache.snapshot().active_operations == 1
        release.set()
        assert await second is original
    assert cache.snapshot().active_operations == 0
    assert calls == [
        ("call_write_tool", {"opaque": 1}, "relay"),
        ("call_read_tool", {"opaque": 2}, None),
    ]


def exercise(root):
    state = root / "state"
    initialize(state)
    stamp = [0.0]
    cache = StatusCache(state, root / "application.json", clock=lambda: stamp[0])
    assert cache.snapshot().state == "starting"
    cache.failed()
    assert cache.snapshot().state == "degraded"
    (root / "available-versions.json").write_text(
        json.dumps({"versions": {"app": "2.0.0", "framework": "0.20.0", "plugin": "0.9.0"}})
    )
    (root / "installed-plugin.json").write_text(
        json.dumps({"plugin_id": PLUGIN_ID, "version": "0.9.0"})
    )
    with patch("freecad_mcp_host.management.installed_version", return_value="1.0.0"):
        versions, journals = cache.collect()
    cache.refresh(versions, journals)
    value = cache.snapshot()
    assert value.versions["app"].installed == "1.0.0" and value.versions["app"].available == "2.0.0"
    assert value.versions["app"].update_pending and not value.versions["plugin"].update_pending
    assert value.versions["mcp"].available is None and value.versions["plugin"].running is None
    value.versions.pop("app")
    assert cache.snapshot().versions["app"].installed == "1.0.0"
    asyncio.run(concurrent_calls(cache))
    client = ManagementClient(root / "registry")
    with ManagedService(
        "freecad-mcp-server",
        "Fixture CAD host",
        cache.snapshot,
        restart=cache.refuse_restart,
        plugin_id=PLUGIN_ID,
        registry=root / "registry",
    ) as agent:
        # HTTP status must use only the cache, even if all producer reads fail.
        with patch.object(
            cache, "collect", side_effect=AssertionError("No producer work in status")
        ):
            row = client.snapshot()["services"][0]
        assert row["plugin_id"] == PLUGIN_ID and row["status"]["state"] == "running"
        assert row["status"]["restart_reason"] == RESTART_REASON
        assert not row["status"]["restart_allowed"]
        assert "token" not in json.dumps(row) and "endpoint" not in json.dumps(row)
        key = secrets.token_hex(16)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            receipts = list(pool.map(lambda _: restart(client, row, key), range(6)))
        assert all(r == receipts[0] and r["outcome"] == "blocked" for r in receipts)
        assert restart(client, dict(row, revision="f" * 64), key)["outcome"] == "uncertain"
        with cache.operation():
            busy = client.snapshot()["services"][0]
            assert busy["status"]["active_operations"] == 1
            assert restart(client, busy)["outcome"] == "blocked"
        stamp[0] = 11
        stale = client.snapshot()["services"][0]
        assert stale["status"]["state"] == "degraded" and not stale["status"]["restart_allowed"]
        assert restart(client, row)["outcome"] == "blocked"
        assert not agent.pending_restarts()
        first_id = agent.instance_id
    assert client.snapshot()["services"][0]["status"]["state"] == "stopped"
    second = ManagedService(
        "freecad-mcp-server", "Fixture CAD host", cache.snapshot, registry=root / "registry"
    )
    assert second.instance_id != first_id

    # This supervisor is a fixture only. Its independent effect ledger is never a CAD operation.
    ledger = root / "effects.sqlite3"
    with closing(sqlite3.connect(ledger)) as db:
        db.execute("CREATE TABLE effects(request_id TEXT PRIMARY KEY)")

    def count():
        with closing(sqlite3.connect(ledger)) as db:
            return db.execute("SELECT count(*) FROM effects").fetchone()[0]

    def effect(request):
        with closing(sqlite3.connect(ledger)) as db:
            db.execute("INSERT INTO effects VALUES (?)", (request.request_id,))
            db.commit()
        return RestartResult(outcome="accepted", message="Fixture supervisor accepted")

    def ambiguous(request):
        effect(request)
        raise RuntimeError("Private fixture failure after effect")

    class LostReply(ManagementClient):
        def _get(self, record, method, suffix, body=None):
            result = super()._get(record, method, suffix, body)
            if method == "POST":
                raise TimeoutError("Lost fixture receipt")
            return result

    def status():
        return ManagedStatus(restart_allowed=True, restart_reason="Fixture supervisor only")

    fixture_client = ManagementClient(root / "restart-fixture")
    with ManagedService(
        "fake-cad-supervisor",
        "Synthetic worker",
        status,
        restart=effect,
        registry=root / "restart-fixture",
    ):
        row = fixture_client.snapshot()["services"][0]
        key = secrets.token_hex(16)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            receipts = list(pool.map(lambda _: restart(fixture_client, row, key), range(8)))
        assert all(r["outcome"] == "accepted" for r in receipts) and count() == 1
        key = secrets.token_hex(16)
        assert restart(LostReply(root / "restart-fixture"), row, key)["outcome"] == "uncertain"
        assert count() == 2
        assert restart(fixture_client, row, key)["outcome"] == "accepted" and count() == 2
    with ManagedService(
        "fake-cad-supervisor",
        "Synthetic worker",
        status,
        restart=ambiguous,
        registry=root / "restart-fixture",
    ) as failed:
        row = next(
            r
            for r in fixture_client.snapshot()["services"]
            if r["instance_id"] == failed.instance_id
        )
        key = secrets.token_hex(16)
        assert restart(fixture_client, row, key)["outcome"] == "uncertain" and count() == 3
    with ManagedService(
        "fake-cad-supervisor",
        "Synthetic worker",
        status,
        restart=effect,
        registry=root / "restart-fixture",
    ) as later:
        row = next(
            r
            for r in fixture_client.snapshot()["services"]
            if r["instance_id"] == later.instance_id
        )
        assert not row["status"]["restart_allowed"] and len(later.pending_restarts()) == 1
        assert restart(fixture_client, row)["outcome"] == "blocked" and count() == 3
    crash_root = root / "crash-fixture"
    crash_root.mkdir()
    child = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--root",
            str(crash_root),
            "--crash-worker",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    try:
        deadline = time.monotonic() + 20
        while not (crash_root / "ready").exists():
            assert child.poll() is None and time.monotonic() < deadline
            time.sleep(0.1)
        crash_client = ManagementClient(crash_root / "registry")
        row = crash_client.snapshot()["services"][0]
        key = secrets.token_hex(16)
        assert restart(crash_client, row, key)["outcome"] == "uncertain"
        assert child.wait(timeout=10) == 29
        assert crash_client.snapshot()["services"][0]["status"]["state"] == "offline"
        with ManagedService(
            "fake-process-supervisor",
            "Synthetic replacement",
            status,
            restart=effect,
            registry=crash_root / "registry",
        ) as replacement:
            row = next(
                r
                for r in crash_client.snapshot()["services"]
                if r["instance_id"] == replacement.instance_id
            )
            assert not row["status"]["restart_allowed"]
            assert replacement.pending_restarts()[0]["request_id"] == key
            assert restart(crash_client, row)["outcome"] == "blocked" and count() == 3
        with closing(sqlite3.connect(crash_root / "effects.sqlite3")) as db:
            assert db.execute("SELECT count(*) FROM effects").fetchone()[0] == 1
    finally:
        if child.poll() is None:
            child.terminate()  # This disposable fixture process only.
            child.wait(timeout=10)
    (root / "management.json").write_text(
        json.dumps(
            {
                "cached_reporting": True,
                "concurrent_cad_calls_and_cancellation": True,
                "production_restart_enabled": False,
                "blocked_restart_effects": 0,
                "fixture_supervisor_effects": count(),
                "duplicates_and_lost_reply": True,
                "cross_instance_barrier": True,
                "process_restart_barrier": True,
                "native_dispatches": 0,
            },
            indent=2,
        )
    )


def crash_worker(root):
    with closing(sqlite3.connect(root / "effects.sqlite3")) as db:
        db.execute("CREATE TABLE effects(request_id)")

    def dispatch(request):
        with closing(sqlite3.connect(root / "effects.sqlite3")) as db:
            db.execute("INSERT INTO effects VALUES (?)", (request.request_id,))
            db.commit()
        os._exit(29)  # Abruptly lose this fake supervisor after one independently recorded effect.

    with ManagedService(
        "fake-process-supervisor",
        "Disposable process",
        lambda: ManagedStatus(restart_allowed=True),
        restart=dispatch,
        registry=root / "registry",
    ):
        (root / "ready").write_text("ready")
        threading.Event().wait(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--crash-worker", action="store_true")
    args = parser.parse_args()
    crash_worker(args.root) if args.crash_worker else exercise(args.root)
