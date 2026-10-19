"""Opt-in real broker/SDK routing against a disposable native FreeCAD document."""

import asyncio
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from codex_freecad.client import find_freecad_cmd
from codex_freecad.engine import CadError
from codex_freecad.integration import connection_plan, execute_plan
from codex_freecad.setup import generate

pytestmark = [pytest.mark.native, pytest.mark.broker]


def data(result):
    assert not result.is_error, result
    contents = result.structured_content or json.loads(result.content[0].text)
    if (
        isinstance(contents, dict)
        and set(contents) == {"result"}
        and isinstance(contents["result"], list)
    ):
        return contents["result"]  # SDK 2's legacy protocol envelope for array returns.
    return contents


@pytest.fixture
def broker_installation(tmp_path):
    configured = os.environ.get("FREECAD_BROKER_PYTHON")
    if not configured:
        pytest.skip("Set FREECAD_BROKER_PYTHON for isolated broker interoperability checks")
    python = Path(configured).resolve()
    if not python.is_file():
        pytest.fail("FREECAD_BROKER_PYTHON must point to an installed broker runtime")
    try:
        freecad = find_freecad_cmd()
    except CadError:
        pytest.skip("Native FreeCADCmd is not installed")
    state = tmp_path / "broker state"
    setup = tmp_path / "setup"
    workspace = tmp_path / "models"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    base = [str(python), "-m", "universal_tools", "--state", str(state)]
    subprocess.run([*base, "init", "--port", str(port)], check=True, capture_output=True, **options)
    generate(workspace, setup, freecad)
    plan = connection_plan(
        setup,
        integration="broker",
        codex_home=tmp_path / "isolated codex",
        broker_python=python,
        broker_state=state,
    )
    execute_plan(plan)
    assert (
        connection_plan(
            setup,
            integration="broker",
            codex_home=tmp_path / "isolated codex",
            broker_python=python,
            broker_state=state,
        )["commands"]
        == []
    )
    try:
        yield base, workspace
    finally:
        subprocess.run([*base, "stop"], check=True, capture_output=True, timeout=30, **options)


def test_real_broker_discovery_retained_native_undo_ownership_and_reopen(broker_installation):
    base, workspace = broker_installation

    async def run():
        parameters = StdioServerParameters(command=base[0], args=[*base[1:], "proxy"])
        async with (
            Client(parameters, mode="legacy", read_timeout_seconds=180) as owner,
            Client(parameters, mode="legacy", read_timeout_seconds=180) as other,
        ):
            services = data(await owner.call_tool("refresh_services", {}))["services"]
            assert {s["service_id"] for s in services} == {"freecad-live", "freecad-headless"}
            assert all(s["status"] == "available" for s in services), services
            assert not (workspace / ".runtime").exists()  # Metadata never launched FreeCADCmd.
            found = data(
                await owner.call_tool(
                    "search_tools", {"query": "bolt_circle", "kind": "capability"}
                )
            )
            assert "holes.bolt_circle" in json.dumps(found)
            assert not (workspace / ".runtime").exists()
            context = data(
                await owner.call_tool("acquire_service", {"service_id": "freecad-headless"})
            )["context_id"]

            async def call(name, arguments=None, request_id=None, *, client=owner, ctx=None):
                description = data(
                    await client.call_tool("describe_tool", {"tool_id": "freecad-headless/" + name})
                )
                payload = {
                    "tool_id": "freecad-headless/" + name,
                    "catalog_revision": description["catalog_revision"],
                    "arguments": arguments or {},
                    "context_id": ctx or context,
                }
                if request_id:
                    payload["request_id"] = request_id
                return await client.call_tool(
                    "call_write_tool" if request_id else "call_read_tool", payload
                )

            created = data(await call("new_document", {"name": "BrokerDemo"}, "broker-create"))
            assert (await call("new_document", {"name": "Duplicate"}, "broker-create")).is_error
            assert (await call("list_documents", client=other)).is_error
            edited = data(
                await call(
                    "apply_operations",
                    {
                        "document": "BrokerDemo",
                        "expected_revision": created["revision"],
                        "operations": [
                            {
                                "op": "create_box",
                                "name": "Block",
                                "length": 2,
                                "width": 3,
                                "height": 4,
                            }
                        ],
                    },
                    "broker-box",
                )
            )
            inspected = data(await call("inspect_document", {"document": "BrokerDemo"}))
            assert inspected["objects"][0]["shape"]["volume_mm3"] == pytest.approx(24)
            assert len(data(await call("list_documents"))) == 1
            changed = data(
                await call(
                    "apply_operations",
                    {
                        "document": "BrokerDemo",
                        "expected_revision": edited["document"]["revision"],
                        "operations": [
                            {
                                "op": "create_box",
                                "name": "Extra",
                                "length": 1,
                                "width": 1,
                                "height": 1,
                            }
                        ],
                    },
                    "broker-extra",
                )
            )
            assert (
                await call(
                    "apply_operations",
                    {
                        "document": "BrokerDemo",
                        "expected_revision": created["revision"],
                        "operations": [
                            {
                                "op": "create_box",
                                "name": "Stale",
                                "length": 1,
                                "width": 1,
                                "height": 1,
                            }
                        ],
                    },
                    "broker-stale",
                )
            ).is_error
            data(
                await call(
                    "undo_document",
                    {
                        "document": "BrokerDemo",
                        "expected_revision": changed["document"]["revision"],
                    },
                    "broker-undo",
                )
            )
            after = data(await call("inspect_document", {"document": "BrokerDemo"}))
            assert [o["name"] for o in after["objects"]] == ["Block"]
            data(
                await owner.call_tool(
                    "refresh_capabilities",
                    {"service_id": "freecad-headless", "context_id": context},
                )
            )
            assert (
                data(await call("inspect_document", {"document": "BrokerDemo"}))["revision"]
                == after["revision"]
            )
            data(
                await call(
                    "save_document",
                    {"document": "BrokerDemo", "path": "BrokerDemo.FCStd"},
                    "broker-save",
                )
            )
            data(
                await owner.call_tool(
                    "release_service", {"service_id": "freecad-headless", "context_id": context}
                )
            )
            context = data(
                await owner.call_tool("acquire_service", {"service_id": "freecad-headless"})
            )["context_id"]
            assert data(await call("list_documents")) == []
            data(await call("open_document", {"path": "BrokerDemo.FCStd"}, "broker-reopen"))
            reopened = data(await call("inspect_document", {"document": "BrokerDemo"}))
            assert reopened["objects"][0]["shape"]["valid"]
            assert reopened["objects"][0]["shape"]["volume_mm3"] == pytest.approx(24)
            data(
                await owner.call_tool(
                    "release_service", {"service_id": "freecad-headless", "context_id": context}
                )
            )

    asyncio.run(run())
