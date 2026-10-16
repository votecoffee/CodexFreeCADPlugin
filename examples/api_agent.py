"""Optional OpenAI Responses API example. Requires OPENAI_API_KEY; makes paid API calls.

python examples/api_agent.py --model YOUR_MODEL --prompt "Create a 40 mm cube and save Cube.FCStd"
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from mcp import Client

from codex_freecad.client import HeadlessClient, LiveClient
from codex_freecad.responses_bridge import function_output, function_tools
from codex_freecad.server import create_server


async def run(args):
    from openai import AsyncOpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY locally before running this example")
    backend = (
        HeadlessClient(args.workspace)
        if args.mode == "headless"
        else LiveClient(args.workspace / ".codex-freecad-live.json")
    )
    async with AsyncOpenAI() as api, Client(create_server(backend)) as cad:
        tools = function_tools((await cad.list_tools()).tools)
        allowed = {tool["name"] for tool in tools}
        history = [{"role": "user", "content": args.prompt}]
        for _ in range(args.max_rounds):
            response = await api.responses.create(
                model=args.model,
                input=history,
                tools=tools,
                parallel_tool_calls=False,
                instructions="Use the FreeCAD tools to fulfill the user's CAD request. Inspect "
                "before editing and use the inspected revision for edits. Lengths are mm and "
                "rotations degrees. Group dependent edits into one transaction. Verify geometry "
                "and save to the user's explicit workspace path. Never retry a timed-out write "
                "without inspecting the model. Report tool errors and incomplete work honestly.",
            )
            history.extend(response.output)
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                print(response.output_text)
                return
            for call in calls:
                if call.name not in allowed:
                    raise RuntimeError("Model requested an unknown function")
                result = await cad.call_tool(call.name, json.loads(call.arguments))
                history.append(function_output(call.call_id, result))
        raise RuntimeError("Tool-loop round limit reached; inspect and save any unsaved work")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--mode", choices=["live", "headless"], default="headless")
    parser.add_argument("--workspace", type=Path, default=Path("models"))
    parser.add_argument("--max-rounds", type=int, default=20)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
