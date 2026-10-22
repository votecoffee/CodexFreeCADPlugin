"""Connected HTTP Skills and ordinary-tool parity inside disposable app profiles."""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import PaginatedRequestParams, Request
from universal_tools.skill_catalog import SkillGet, SkillList, SkillParams
from universal_tools.skill_client import SkillClient


async def exercise_guidance(root, publication, settings, call, data, *, modern_discovery=False):
    from codex_freecad.framework_setup import atomic_json
    from codex_freecad.workflows import digest, snapshot

    current = data(await call("get_workflow"))
    initial_revision = current["revision"]
    active = publication.parent / "guidance/active.json"
    files = json.loads(active.read_bytes())["files"]
    actions = []
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + settings.token}, trust_env=False
    ) as http:
        async with Client(
            streamable_http_client(settings.url + "/mcp", http_client=http),
            mode="2026-07-28",
            extensions=[SkillClient()],
            cache=None,
        ) as client:
            if modern_discovery:
                async with client.listen(resource_subscriptions=["broker://catalog"]) as changes:
                    assert data(await call("fixture_catalog_publish"))["published"]
                    async with asyncio.timeout(10):
                        await anext(changes)
                assert data(await call("fixture_catalog_added")) == {"fixture": True}

            async def parity():
                listing = await client.session.send_request(
                    Request(method="skills/list", params=PaginatedRequestParams()), SkillList
                )
                assert len(listing.skills) == 1
                uri = listing.skills[0]["uri"]
                assert uri == "skill://freecad-modeling/SKILL.md"
                got = await client.session.send_request(
                    Request(method="skills/get", params=SkillParams(uri=uri)), SkillGet
                )
                assert got.skill == listing.skills[0]
                guide = data(await call("get_workflow"))
                for row in guide["references"]:
                    result = await client.read_resource(row["uri"])
                    item = result.contents[0]
                    raw = (
                        item.text.encode() if hasattr(item, "text") else base64.b64decode(item.blob)
                    )
                    ordinary = data(
                        await call(
                            "get_workflow",
                            {
                                "reference": row["id"],
                                "expected_revision": guide["revision"],
                                "expected_sha256": row["sha256"],
                            },
                        )
                    )
                    assert raw == ordinary["guidance"].encode() and digest(raw) == row["sha256"]
                return guide

            await parity()

            async def stage(candidate, expected, status):
                result_path = publication.parent / "guidance/result.json"
                before = result_path.read_bytes() if result_path.exists() else None
                atomic_json(
                    publication.parent / "guidance/desired.json",
                    {
                        "expected_revision": expected,
                        "snapshot": candidate,
                    },
                )
                deadline = time.monotonic() + 12
                while True:
                    if result_path.exists() and result_path.read_bytes() != before:
                        result = json.loads(result_path.read_bytes())
                        assert result["status"] == status, result
                        return result
                    assert time.monotonic() < deadline, "Guide publication timed out"
                    await asyncio.sleep(0.05)

            async with client.listen(resource_subscriptions=["broker://skills"]) as changes:
                files["references/demo.md"] = "# Disposable reference\nVersion one.\n"
                candidate = snapshot(files)
                await stage(candidate, current["revision"], "applied")
                async with asyncio.timeout(5):
                    await anext(changes)
                current = await parity()
                actions.append("add")
                assert (
                    await call("get_workflow", {"expected_revision": initial_revision})
                ).is_error
                files["references/demo.md"] = "# Disposable reference\nVersion two.\n"
                await stage(snapshot(files), current["revision"], "applied")
                current = await parity()
                actions.append("update")
                del files["references/demo.md"]
                await stage(snapshot(files), current["revision"], "applied")
                current = await parity()
                actions.append("remove")
                try:
                    await client.read_resource("skill://freecad-modeling/references/demo.md")
                except MCPError:
                    pass
                else:
                    raise AssertionError("Removed reference remained readable")
                invalid = dict(files)
                invalid["SKILL.md"] = "invalid skill frontmatter"
                await stage(snapshot(invalid), current["revision"], "rejected")
                assert (await parity())["revision"] == current["revision"]
                actions.append("failed_candidate_preserved")
    (root / "guidance.json").write_text(
        json.dumps(
            {
                "actions": actions,
                "same_connections": True,
                "sha256_parity": True,
                "native_codex_skill_loading": "unassessed; importer is a static snapshot",
            },
            indent=2,
        )
    )


def transaction_checks(root):
    """No transports/native provider: preserve both views through cancellation/failure."""
    from freecad_mcp_host.guidance import GuidanceCatalog

    from codex_freecad.framework_setup import atomic_json, publish
    from codex_freecad.workflows import snapshot

    publication = Path(publish(root / "models", root / "candidate", sys.executable)["publication"])
    host = SimpleNamespace(definition=SimpleNamespace(backends=[]))

    async def exercise():
        guides = GuidanceCatalog(publication)
        files = dict(guides.current["files"])
        files["references/overview.md"] += "\nPersisted guide-only fixture.\n"
        candidate = snapshot(files)
        desired = guides.root / "desired.json"
        atomic_json(
            desired, {"expected_revision": guides.current["revision"], "snapshot": candidate}
        )
        await guides.refresh(host)
        assert guides.current == candidate
        assert GuidanceCatalog(publication).current == candidate
        previous = (guides.root / "active.json").read_bytes()
        revision = guides.catalog.revision
        entered, release = asyncio.Event(), asyncio.Event()

        async def failed(*args, **kwargs):
            entered.set()
            await release.wait()
            raise ValueError("Synthetic publish failure after cancellation")

        guides.catalog.publish = failed
        files["references/overview.md"] += "\nRejected update.\n"
        atomic_json(
            desired, {"expected_revision": candidate["revision"], "snapshot": snapshot(files)}
        )
        task = asyncio.create_task(guides.refresh(host))
        await entered.wait()
        task.cancel()
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert guides.current == candidate and guides.catalog.revision == revision
        assert (guides.root / "active.json").read_bytes() == previous

    asyncio.run(exercise())
