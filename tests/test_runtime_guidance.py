"""Hash-bound data and actual SDK progress/cache behavior without native CAD."""

import asyncio
import copy
import json
import threading

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver import Context

import codex_freecad.server as server_module
from codex_freecad.server import create_server
from codex_freecad.workflows import build_snapshot, describe_workflow, snapshot, validate


class Provider:
    def close(self):
        pass

    def call(self, method, **params):
        assert method == "apply_operations"
        return {"document": {"name": params["document"]}, "results": []}


ARGS = {
    "document": "Demo",
    "operations": [{"op": "create_box", "name": "Box", "length": 1, "width": 2, "height": 3}],
}


def test_guides_pin_identity_content_and_safe_inventory():
    original = build_snapshot()
    guide = describe_workflow(current=original)
    for row in guide["references"]:
        read = describe_workflow(
            reference=row["id"],
            expected_revision=guide["revision"],
            expected_sha256=row["sha256"],
            current=original,
        )
        assert read["sha256"] == row["sha256"]
    changed = copy.deepcopy(original["files"])
    changed["references/overview.md"] += "\nUpdated fixture.\n"
    updated = snapshot(changed)
    with pytest.raises(ValueError, match="Stale workflow revision"):
        describe_workflow(current=updated, expected_revision=guide["revision"])
    with pytest.raises(ValueError, match="hash"):
        describe_workflow(current=updated, expected_sha256=guide["sha256"])
    with pytest.raises(ValueError, match="Pin"):
        describe_workflow(current=original, reference="references/recovery.md")
    changed["references/../../outside.md"] = "bad"
    with pytest.raises(ValueError, match="resource"):
        snapshot(changed)
    original["files"]["references/overview.md"] += "tamper"
    with pytest.raises(ValueError, match="mismatch"):
        validate(original)


def test_sdk_request_progress_and_structured_fallback():
    async def exercise():
        progress = []

        async def observe(value, total, message):
            progress.append((value, total, message))

        async with Client(create_server(Provider()), mode="legacy") as client:
            tool = next(
                t for t in (await client.list_tools()).tools if t.name == "apply_operations"
            )
            assert "ctx" not in tool.input_schema["properties"]
            result = await client.call_tool("apply_operations", ARGS, progress_callback=observe)
            assert not result.is_error
            assert [row[0] for row in progress] == [0, 1, 2]
            assert all(row[1] is None for row in progress)
            assert (
                json.loads(result.content[0].text)["execution"]["native_stop_acknowledged"] is False
            )
            fallback = await client.call_tool("apply_operations", ARGS)
            assert json.loads(fallback.content[0].text)["execution"]["state"] == "reply_received"

    asyncio.run(exercise())


def test_inflight_cancellation_does_not_stop_the_synchronous_provider():
    started, release, effected = threading.Event(), threading.Event(), threading.Event()

    class Slow(Provider):
        def call(self, method, **params):
            started.set()
            assert release.wait(5)
            effected.set()
            return super().call(method, **params)

    async def exercise():
        async with Client(create_server(Slow()), mode="legacy") as client:
            task = asyncio.create_task(client.call_tool("apply_operations", ARGS))
            assert await asyncio.to_thread(started.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not effected.is_set()
            release.set()
            assert await asyncio.to_thread(effected.wait, 3)

    try:
        asyncio.run(exercise())
    finally:
        release.set()


def test_cancellation_before_dispatch_has_no_provider_effect(monkeypatch):
    queued, release = threading.Event(), threading.Event()
    calls = []
    original = server_module.report_stage

    def pause(context, progress, message):
        original(context, progress, message)
        if progress == 0:
            queued.set()
            assert release.wait(5)

    class Counted(Provider):
        def call(self, method, **params):
            calls.append(method)
            return super().call(method, **params)

    monkeypatch.setattr(server_module, "report_stage", pause)

    async def exercise():
        async with Client(create_server(Counted()), mode="legacy") as client:
            task = asyncio.create_task(client.call_tool("apply_operations", ARGS))
            assert await asyncio.to_thread(queued.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            # Give the transport's cancellation notification time to reach the request scope.
            await asyncio.sleep(0.1)
            release.set()
            await asyncio.sleep(0.1)
        assert calls == []

    try:
        asyncio.run(exercise())
    finally:
        release.set()


def test_private_discovery_cache_saves_roundtrips_and_notifications_invalidate(monkeypatch):
    calls = []
    original = MCPServer._handle_list_tools

    async def listing(self, ctx, params):
        calls.append(self)
        return await original(self, ctx, params)

    monkeypatch.setattr(MCPServer, "_handle_list_tools", listing)

    async def exercise():
        server = create_server(Provider(), modern_discovery=True)

        @server.tool()
        async def publish(ctx: Context) -> dict:
            @server.tool()
            def added() -> str:
                return "fixture"

            await ctx.notify_tools_changed()
            return {"added": True}

        async with Client(server, mode="2026-07-28") as first:
            for _ in range(3):
                await first.list_tools()
            assert len(calls) == 1  # Two eliminated tools/list protocol roundtrips.
            async with Client(server, mode="2026-07-28") as other:
                await other.list_tools()
                assert len(calls) == 2  # Never share a private cache across connections.
                async with first.listen(tools_list_changed=True) as changes:
                    await first.call_tool("publish", {})
                    async with asyncio.timeout(5):
                        await anext(changes)
                assert "added" in {t.name for t in (await first.list_tools()).tools}
                assert len(calls) == 3
        legacy = create_server(Provider())
        async with Client(legacy, mode="legacy") as client:
            before = len(calls)
            for _ in range(3):
                await client.list_tools()
            assert len(calls) - before == 3  # Selected legacy default remains uncached.

    asyncio.run(exercise())
