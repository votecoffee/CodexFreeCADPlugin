"""In-process SDK handler/serialization checks; no serving connection or native backend."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from mcp.types import CallToolRequestParams

from codex_freecad.engine import CadError
from codex_freecad.native_session import NativeCapacityError
from codex_freecad.server import create_server


def response(client, name, arguments):
    server = create_server(client)
    result = asyncio.run(
        server._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments))
    )
    return json.loads(result.model_dump_json(by_alias=True))


def test_known_capacity_refusal_survives_sdk_handler_and_serialization():
    calls = []
    reason = "FreeCAD native capacity is busy in another connection"

    def reject(method, **params):
        calls.append(method)
        raise NativeCapacityError(reason)

    wire = response(
        SimpleNamespace(call=reject, close=lambda: None), "new_document", {"name": "Refused"}
    )
    assert wire["isError"] is True and reason in wire["content"][0]["text"]
    assert calls == ["new_document"]


@pytest.mark.parametrize("exception", [OSError, CadError])
def test_other_backend_failures_keep_sdk_redaction(exception):
    def crash(*args, **params):
        raise exception("private diagnostic detail")

    wire = response(SimpleNamespace(call=crash, close=lambda: None), "freecad_status", {})
    assert wire["isError"] is True
    assert "Error executing tool freecad_status" in wire["content"][0]["text"]
    assert "private diagnostic detail" not in json.dumps(wire)


def test_successful_status_conversion_is_unchanged():
    wire = response(
        SimpleNamespace(call=lambda *a, **k: {"mode": "headless"}, close=lambda: None),
        "freecad_status",
        {},
    )
    assert not wire["isError"]
    assert json.loads(wire["content"][0]["text"]) == {"mode": "headless"}
