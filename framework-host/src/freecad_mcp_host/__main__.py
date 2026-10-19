"""Start an app-owned framework host or connect a standalone stdio frontend to it."""

import argparse
import asyncio
import json
from importlib.metadata import version
from pathlib import Path

from universal_tools.cli import initialize, stop
from universal_tools.framework import load_application, serve_application
from universal_tools.models import BrokerError, atomic_json, load_settings
from universal_tools.surface import RemoteBackend, create_surface

from . import APPLICATION_ID, FRAMEWORK_VERSION


def check_runtime():
    if version("universal-codex-tools") != FRAMEWORK_VERSION:
        raise BrokerError("Install the exact pinned FreeCAD host framework version")


def publication(path):
    definition = load_application(path)
    if definition.id != APPLICATION_ID:
        raise BrokerError("Publication belongs to another application")
    for backend in definition.backends:
        backend.verify()
    return definition


def require_state(state, path):
    marker = state / "freecad-host.json"
    if not marker.is_file():
        raise BrokerError("Initialize a dedicated FreeCAD framework state first")
    expected = {"application_id": APPLICATION_ID, "publication": str(path)}
    if json.loads(marker.read_bytes()) != expected:
        raise BrokerError("State belongs to another application/publication")
    if any((state / "services").glob("*.json")):
        raise BrokerError("FreeCAD framework state cannot contain broker registrations")


def initialize_app(state, path, port):
    publication(path)
    marker = state / "freecad-host.json"
    if marker.exists():
        require_state(state, path)
    elif (state / "settings.json").exists() or any((state / "services").glob("*.json")):
        raise BrokerError("Use fresh dedicated state; existing broker/app state was preserved")
    initialize(state, port)
    atomic_json(marker, {"application_id": APPLICATION_ID, "publication": str(path)})


async def status(state):
    async with RemoteBackend(load_settings(state)) as backend:
        result = await backend.invoke("broker_status", {})
        if result.isError:
            raise BrokerError("FreeCAD host is unavailable; start its app-owned serve command")
        return result.structuredContent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("command", choices=["init", "serve", "proxy", "status", "stop", "validate"])
    parser.add_argument("--port", type=int, default=8891)
    args = parser.parse_args()
    state, path = args.state.expanduser().resolve(), args.publication.expanduser().resolve()
    try:
        check_runtime()
        if args.command in {"status", "stop"}:
            require_state(state, path)
            print(
                json.dumps(asyncio.run(status(state)) if args.command == "status" else stop(state))
            )
            return
        definition = publication(path)
        if args.command == "validate":
            print(json.dumps({"application_id": definition.id, "framework": FRAMEWORK_VERSION}))
        elif args.command == "init":
            initialize_app(state, path, args.port)
            print(json.dumps({"application_id": definition.id, "initialized": True}))
        else:
            require_state(state, path)
            if args.command == "serve":
                serve_application(state, path)
            elif args.command == "proxy":
                # The app host must already be running. Never auto-start a universal daemon.
                create_surface(
                    RemoteBackend(load_settings(state)),
                    name=definition.display_name,
                    instructions=definition.instructions,
                ).run(transport="stdio")
    except (BrokerError, OSError, ValueError) as exc:
        parser.exit(1, "FreeCAD framework host: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
