"""MCP 2.3 app-host profile against frozen CAD handlers and disposable providers."""

import argparse
import asyncio
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import time
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import version
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from universal_tools.cli import probe
from universal_tools.models import load_settings


def data(result):
    assert not result.is_error, result
    value = result.structured_content or json.loads(result.content[0].text)
    if isinstance(value, dict) and set(value) == {"result"} and isinstance(value["result"], list):
        return value["result"]
    return value


def complete(result):
    return result.model_dump(mode="json", by_alias=True, exclude_none=True)


@asynccontextmanager
async def connected(command, *, mode="legacy"):
    async with Client(
        StdioServerParameters(command=command[0], args=command[1:]), mode=mode
    ) as client:
        yield client


def run_cli(command):
    result = subprocess.run(
        command,
        capture_output=True,
        timeout=30,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


async def exercise(args):
    # The standard-library publisher does not import or execute a native CAD provider.
    sys.path.insert(0, str(args.source.parent))
    from codex_freecad.framework_setup import publish

    source = args.root / "fixture-source/codex_freecad"
    shutil.copytree(args.source, source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    provider = Path(__file__).parent / "fixtures/framework_provider.py"
    shutil.copyfile(provider, source / "fixture_provider.py")
    workspace, output = args.root / "disposable-models", args.root / "candidate"
    native_marker = workspace / "native-dispatch-forbidden.txt"
    with (source / "client.py").open("a") as stream:
        stream.write(
            "\ndef _forbidden_native(*args, **kwargs):\n"
            f"    marker = Path({str(native_marker)!r})\n"
            "    marker.parent.mkdir(parents=True, exist_ok=True)\n"
            "    marker.write_text('Native dispatch blocked by disposable-provider test')\n"
            "    raise AssertionError('Native dispatch is forbidden in this profile')\n"
            "HeadlessClient._start = LiveClient.call = _forbidden_native\n"
            "from .fixture_provider import FixtureClient\nHeadlessClient = LiveClient = FixtureClient\n"
        )
    result = publish(
        workspace,
        output,
        sys.executable,
        backend_python=args.backend_python,
        source_package=source,
        protocol_mode=args.protocol_mode,
    )
    publication = Path(result["publication"])
    initial = json.loads(publication.read_bytes())
    state = Path(result["state"])
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = [
        sys.executable,
        "-m",
        "freecad_mcp_host",
        "--state",
        str(state),
        "--publication",
        str(publication),
        "--management-registry",
        str(args.root / "management-registry"),
    ]
    run_cli([*base, "init", "--port", str(port)])
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    log = (args.root / "host.log").open("wb")
    child = subprocess.Popen(
        [*base, "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=log, **options
    )
    measurements = {"direct_ms": [], "hosted_ms": []}
    try:
        settings = load_settings(state)
        deadline = time.monotonic() + 30
        while probe(settings) is None:
            assert child.poll() is None, (args.root / "host.log").read_text(errors="replace")
            assert time.monotonic() < deadline, "Disposable app host startup timed out"
            await asyncio.sleep(0.05)
        backend = next(b for b in initial["backends"] if b["service"]["id"] == "freecad-headless")
        direct_command = [
            backend["service"]["transport"]["command"],
            *backend["service"]["transport"]["args"],
        ]
        async with AsyncExitStack() as stack:
            owner = await stack.enter_async_context(
                connected([*base, "proxy"], mode=args.frontend_mode)
            )
            other = await stack.enter_async_context(
                connected([*base, "proxy"], mode=args.frontend_mode)
            )
            # Modern SDK results add serverInfo metadata; compare the same protocol on both paths.
            direct = await stack.enter_async_context(
                connected(direct_command, mode=args.protocol_mode)
            )
            baseline = (await owner.list_tools()).model_dump(mode="json", by_alias=True)
            assert len(baseline["tools"]) == 14
            status = data(await owner.call_tool("broker_status", {}))
            assert status["application_id"] == "freecad-mcp-server"
            assert not (workspace / "effects.jsonl").exists()
            context = data(
                await owner.call_tool("acquire_service", {"service_id": "freecad-headless"})
            )["context_id"]
            described = data(
                await owner.call_tool("describe_service", {"service_id": "freecad-headless"})
            )
            negotiated = described["initialization"]["protocolVersion"]
            assert negotiated == ("2025-11-25" if args.protocol_mode == "legacy" else "2026-07-28")

            async def call(name, arguments=None, *, request=None, frontend=owner):
                description = data(
                    await frontend.call_tool(
                        "describe_tool", {"tool_id": "freecad-headless/" + name}
                    )
                )
                payload = {
                    "tool_id": "freecad-headless/" + name,
                    "catalog_revision": description["catalog_revision"],
                    "arguments": arguments or {},
                    "context_id": context,
                }
                if request:
                    payload["request_id"] = "fixture-" + request
                return await frontend.call_tool(
                    "call_write_tool" if request else "call_read_tool", payload
                )

            for tool in (await direct.list_tools()).tools:
                hosted = data(
                    await owner.call_tool(
                        "describe_tool", {"tool_id": "freecad-headless/" + tool.name}
                    )
                )
                assert hosted["definition"] == tool.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
            info = data(await call("freecad_status"))
            assert info["fixture"] and info["generation"] == 1
            assert (await call("freecad_status", frontend=other)).is_error
            guide = await call("get_workflow")
            direct_guide = await direct.call_tool("get_workflow", {})
            comparison = {"hosted": complete(guide), "direct": complete(direct_guide)}
            (args.root / "workflow-results.json").write_text(json.dumps(comparison, indent=2))
            assert comparison["hosted"] == comparison["direct"], comparison
            created = await call("new_document", {"name": "Compare"}, request="create")
            direct_created = await direct.call_tool("new_document", {"name": "Compare"})
            assert complete(created) == complete(direct_created), (
                complete(created),
                complete(direct_created),
            )
            arguments = {
                "document": "Compare",
                "expected_revision": "0",
                "operations": [
                    {"op": "create_box", "name": "Box", "length": 2, "width": 3, "height": 4}
                ],
            }
            edited = await call("apply_operations", arguments, request="edit")
            assert complete(edited) == complete(
                await direct.call_tool("apply_operations", arguments)
            )
            audit = workspace / "effects.jsonl"
            effects_before = len(audit.read_text().splitlines())
            assert (await call("apply_operations", arguments, request="edit")).is_error
            assert (await call("apply_operations", arguments, request="stale")).is_error
            assert len(audit.read_text().splitlines()) == effects_before
            # Structural limits precede native/provider dispatch, schema validation and write claims.
            deep = {}
            for _ in range(70):
                deep = {"nested": deep}
            calls_audit = workspace / "calls.jsonl"
            calls_before = calls_audit.read_bytes()
            for budget, extension_arguments in (
                ("depth", deep),
                ("nodes", {"items": [0] * 100_001}),
            ):
                oversized = {
                    "document": "Compare",
                    "expected_revision": "1",
                    "operations": [
                        {
                            "op": "extension",
                            "capability": "test.budget",
                            "arguments": extension_arguments,
                        }
                    ],
                }
                rejected = await call("apply_operations", oversized, request="budget-" + budget)
                assert rejected.is_error and "budget" in json.dumps(complete(rejected))
                unclaimed = await owner.call_tool(
                    "get_request_status", {"request_id": "fixture-budget-" + budget}
                )
                assert unclaimed.is_error and "unknown request_id" in json.dumps(
                    complete(unclaimed)
                )
                assert calls_audit.read_bytes() == calls_before
                assert len(audit.read_text().splitlines()) == effects_before
            image = await call("capture_view", {"document": "Compare"}, request="image")
            assert complete(image) == complete(
                await direct.call_tool("capture_view", {"document": "Compare"})
            )
            assert image.content[0].type == "image" and image.content[0].mime_type == "image/png"
            for _ in range(5):
                start = time.perf_counter()
                await direct.call_tool("inspect_document", {"document": "Compare"})
                measurements["direct_ms"].append((time.perf_counter() - start) * 1000)
                start = time.perf_counter()
                await call("inspect_document", {"document": "Compare"})
                measurements["hosted_ms"].append((time.perf_counter() - start) * 1000)

            # A new tool behind the original server and fake provider; no frontend schema update.
            before_publication = data(await call("inspect_document", {"document": "Compare"}))
            server = source / "server.py"
            original_server = server.read_text(encoding="utf-8")
            server.write_text(
                original_server.replace(
                    "    return server\n",
                    "    @server.tool(annotations=READ)\n    def publication_probe() -> dict:\n        return {'generation': 2}\n\n    return server\n",
                ),
                encoding="utf-8",
            )
            publish(
                workspace,
                output,
                sys.executable,
                backend_python=args.backend_python,
                source_package=source,
                protocol_mode=args.protocol_mode,
            )
            refresh = data(await owner.call_tool("refresh_services", {}))
            assert any(row["status"] == "deferred" for row in refresh["backend_publications"])
            assert data(await call("freecad_status"))["pid"] == info["pid"]
            assert (
                data(await call("inspect_document", {"document": "Compare"})) == before_publication
            )
            undone = data(
                await call(
                    "undo_document",
                    {"document": "Compare", "expected_revision": before_publication["revision"]},
                    request="undo-after-refresh",
                )
            )
            assert undone["objects"] == []
            data(
                await owner.call_tool(
                    "release_service", {"service_id": "freecad-headless", "context_id": context}
                )
            )
            refresh = data(await owner.call_tool("refresh_services", {}))
            # The stale fixture write remains an app-error receipt; publication must defer.
            assert any(
                row.get("reason") == "app_write_reconciliation_required"
                for row in refresh["backend_publications"]
            )
            # Preserve that barrier. Test successful replacement on the independent live fixture.
            live_context = data(
                await owner.call_tool("acquire_service", {"service_id": "freecad-live"})
            )["context_id"]
            live = data(
                await owner.call_tool(
                    "describe_tool", {"tool_id": "freecad-live/publication_probe"}
                )
            )
            queried = await owner.call_tool(
                "call_read_tool",
                {
                    "tool_id": "freecad-live/publication_probe",
                    "catalog_revision": live["catalog_revision"],
                    "arguments": {},
                    "context_id": live_context,
                },
            )
            assert data(queried) == {"generation": 2}
            data(
                await owner.call_tool(
                    "release_service", {"service_id": "freecad-live", "context_id": live_context}
                )
            )
            assert (await owner.list_tools()).model_dump(mode="json", by_alias=True) == baseline
            # Invalid candidate discovery retains the selected working publication.
            server.write_text(
                server.read_text(encoding="utf-8").replace(
                    "{'generation': 2}", "{'generation': 3}"
                ),
                encoding="utf-8",
            )
            publish(
                workspace,
                output,
                sys.executable,
                backend_python=args.backend_python,
                source_package=source,
                protocol_mode=args.protocol_mode,
            )
            selected = json.loads(publication.read_bytes())
            live_backend = next(
                b for b in selected["backends"] if b["service"]["id"] == "freecad-live"
            )
            broken = (
                Path(live_backend["artifact"]["path"]).parent / "package/codex_freecad/server.py"
            )
            broken.write_text("invalid python !", encoding="utf-8")
            failed = data(await owner.call_tool("refresh_services", {}))
            assert any(
                row["status"] == "rejected" for row in failed.get("backend_publications", [])
            ) or any(s["status"] != "available" for s in failed["services"])
            assert (await owner.list_tools()).model_dump(mode="json", by_alias=True) == baseline
            live_context = data(
                await owner.call_tool("acquire_service", {"service_id": "freecad-live"})
            )["context_id"]
            live = data(
                await owner.call_tool(
                    "describe_tool", {"tool_id": "freecad-live/publication_probe"}
                )
            )
            assert data(
                await owner.call_tool(
                    "call_read_tool",
                    {
                        "tool_id": "freecad-live/publication_probe",
                        "catalog_revision": live["catalog_revision"],
                        "arguments": {},
                        "context_id": live_context,
                    },
                )
            ) == {"generation": 2}
            data(
                await owner.call_tool(
                    "release_service", {"service_id": "freecad-live", "context_id": live_context}
                )
            )

            context = data(
                await owner.call_tool("acquire_service", {"service_id": "freecad-headless"})
            )["context_id"]
            data(await call("new_document", {"name": "LostReply"}, request="lost-doc"))
            before_lost = len(audit.read_text().splitlines())
            lost = {
                "document": "LostReply",
                "expected_revision": "0",
                "operations": [
                    {"op": "create_box", "name": "Effect", "length": 1, "width": 1, "height": 1}
                ],
            }
            assert (await call("apply_operations", lost, request="lost-write")).is_error
            assert len(audit.read_text().splitlines()) == before_lost + 1
            receipt = data(
                await owner.call_tool("get_request_status", {"request_id": "fixture-lost-write"})
            )
            assert receipt["status"] == "uncertain"
            assert (await call("apply_operations", lost, request="lost-write")).is_error
            assert len(audit.read_text().splitlines()) == before_lost + 1
            assert (
                await other.call_tool("acquire_service", {"service_id": "freecad-headless"})
            ).is_error
        # Restart this disposable app host only; retain its journals and blocked native resource.
        run_cli([*base, "stop"])
        child.wait(timeout=30)
        child = subprocess.Popen(
            [*base, "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=log, **options
        )
        deadline = time.monotonic() + 30
        while probe(settings) is None:
            assert child.poll() is None and time.monotonic() < deadline
            await asyncio.sleep(0.05)
        async with connected([*base, "proxy"], mode=args.frontend_mode) as fresh:
            assert (
                await fresh.call_tool("acquire_service", {"service_id": "freecad-headless"})
            ).is_error
            assert (
                data(
                    await fresh.call_tool(
                        "get_request_status", {"request_id": "fixture-lost-write"}
                    )
                )["status"]
                == "uncertain"
            )
        assert len(audit.read_text().splitlines()) == before_lost + 1
        assert not native_marker.exists(), "A native dispatch was attempted in the fixture profile"
        record = {
            "framework": version("universal-codex-tools"),
            "framework_sdk": version("mcp"),
            "backend_protocol_mode": args.protocol_mode,
            "backend_negotiated_protocol": negotiated,
            "frontend_protocol_mode": args.frontend_mode,
            "frontend_tools": 14,
            "native_dispatches": int(native_marker.exists()),
            "same_session_refresh": True,
            "durable_recovery_barrier": True,
            "structural_budget_rejections": ["depth", "nodes"],
            "samples": measurements,
            "measurement_scope": "Five warm direct calls versus host describe_tool plus call_read_tool; same clients",
            "median_ms": {k: statistics.median(v) for k, v in measurements.items()},
            "limits": [
                "fake provider, no native geometry or Codex UI acceptance",
            ],
        }
        (args.root / "profile.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    finally:
        run_cli([*base, "stop"])
        child.wait(timeout=30)
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--backend-python", required=True)
    parser.add_argument(
        "--protocol-mode", choices=["legacy", "auto", "2026-07-28"], default="legacy"
    )
    parser.add_argument("--frontend-mode", choices=["legacy", "2026-07-28"], default="legacy")
    args = parser.parse_args()
    asyncio.run(exercise(args))


if __name__ == "__main__":
    main()
