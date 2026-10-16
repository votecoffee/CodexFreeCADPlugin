"""Convert MCP tool contracts for an application-managed Responses API tool loop."""

import json


def function_tools(tools):
    # This example adapter transports text results. Use MCP directly for viewport images.
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
            "strict": False,
        }
        for tool in tools
        if tool.name != "capture_view"
    ]


def function_output(call_id, result):
    content = result.structured_content
    if content is None:
        content = [item.text for item in result.content if item.type == "text"]
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps({"is_error": result.is_error, "result": content}),
    }
