import asyncio
import json

from mcp import Client

from codex_freecad.responses_bridge import function_output, function_tools
from codex_freecad.server import create_server


class FixtureBackend:
    def call(self, method, **params):
        return {"method": method, "params": params}

    def close(self):
        pass


def test_responses_adapter_preserves_schemas_and_tool_results_without_paid_api_calls():
    async def run():
        async with Client(create_server(FixtureBackend())) as cad:
            tools = function_tools((await cad.list_tools()).tools)
            assert len(tools) == 16
            edit = next(t for t in tools if t["name"] == "apply_operations")
            assert edit["parameters"]["properties"]["operations"]["type"] == "array"
            result = await cad.call_tool("inspect_document", {"document": "Plate"})
            output = function_output("test_call", result)
            assert output["type"] == "function_call_output"
            assert output["call_id"] == "test_call"
            assert not json.loads(output["output"])["is_error"]

    asyncio.run(run())
