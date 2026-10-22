"""Start an app-owned framework host or connect a standalone stdio frontend to it."""

import argparse
import asyncio
import json
import shutil
import socket
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

from universal_tools.cli import initialize, probe, process_options, stop
from universal_tools.daemon import InstanceLock
from universal_tools.framework import load_application
from universal_tools.models import BrokerError, atomic_json, load_settings
from universal_tools.surface import RemoteBackend, create_surface

from . import APPLICATION_ID, FRAMEWORK_VERSION
from .application import serve
from .maintenance import journal_status, require_idle


def check_runtime():
    if version("mcp") != "2.3.0":
        raise BrokerError(
            "FreeCAD requires MCP 2.3.0; update the framework package without downgrading"
        )
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
        payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        if payload.get("isError"):
            raise BrokerError("FreeCAD host is unavailable; start its app-owned serve command")
        value = payload.get("structuredContent") or json.loads(payload["content"][0]["text"])
        if value.get("application_id") != APPLICATION_ID:
            raise BrokerError("Configured endpoint is not the FreeCAD application host")
        return value


def wait_stopped(state, *, deadline=None, allow_running=False):
    """Port closure precedes framework cleanup; wait for the OS-owned state lock too."""
    deadline = deadline or time.monotonic() + 35
    while True:
        try:
            with InstanceLock(state / "broker.lock"):
                return False
        except BrokerError:
            if allow_running and probe(load_settings(state)):
                return True
            if time.monotonic() >= deadline:
                raise BrokerError(
                    "FreeCAD host still owns its state; no replacement was started"
                ) from None
            time.sleep(0.1)


def spawn_serve(state, path, management_registry=None):
    command = [
        sys.executable,
        "-m",
        "freecad_mcp_host",
        "--state",
        str(state),
        "--publication",
        str(path),
        "serve",
    ]
    if management_registry is not None:
        command += ["--management-registry", str(management_registry)]
    with (state / "freecad-host.log").open("ab") as log:
        return subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **process_options()
        )


def activate(
    state,
    path,
    *,
    previous_python,
    workspace,
    backup,
    port=8891,
    freecad_cmd=None,
    extension_dirs=(),
    protocol_mode="legacy",
    management_registry=None,
    source_package=None,
    modern_discovery=False,
):
    """Local idle-host maintenance. Fence proxy auto-start across the complete handoff."""
    from codex_freecad.framework_setup import publish

    require_state(state, path)
    publication(path)
    if not Path(previous_python).is_file() or not Path(backup).resolve().is_relative_to(
        path.parent / "backups"
    ):
        raise BrokerError(
            "Activation requires the prior interpreter and an app-owned backup directory"
        )
    lock = InstanceLock(state / "freecad-startup.lock")
    deadline = time.monotonic() + 35
    while True:
        try:
            lock.__enter__()
            break
        except BrokerError:
            if time.monotonic() >= deadline:
                raise BrokerError(
                    "Another client still owns startup; activation did not begin"
                ) from None
            time.sleep(0.1)
    try:
        require_idle(state)
        subprocess.run(
            [
                str(previous_python),
                "-m",
                "freecad_mcp_host",
                "--state",
                str(state),
                "--publication",
                str(path),
                "stop",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            **process_options(),
        )
        wait_stopped(state)
        require_idle(state)
        Path(backup).mkdir(parents=True, exist_ok=True)
        for name in ("ownership.sqlite3", "writes.sqlite3"):
            shutil.copy2(state / name, Path(backup) / name)
        result = publish(
            workspace,
            path.parent,
            sys.executable,
            backend_python=sys.executable,
            freecad_cmd=freecad_cmd,
            extension_dirs=extension_dirs,
            protocol_mode=protocol_mode,
            installed=True,
            source_package=source_package,
            modern_discovery=modern_discovery,
        )
        initialize_app(state, path, port)
        child = spawn_serve(state, path, management_registry)
        deadline = time.monotonic() + 35
        settings = load_settings(state)
        while time.monotonic() < deadline:
            if probe(settings):
                return {
                    "startup_fence": True,
                    "publication": result["publication"],
                    "doctor": doctor(state, path),
                }
            if child.poll() is not None:
                raise BrokerError(
                    "Replacement startup failed; preserved runtimes and journals need inspection"
                )
            time.sleep(0.1)
        raise BrokerError("Replacement startup timed out; no runtime selection was acknowledged")
    finally:
        lock.__exit__()


def start(state, path, *, timeout=35, management_registry=None):
    """Start only this app's server, preserving its ownership and recovery journals."""
    require_state(state, path)
    settings = load_settings(state)
    deadline = time.monotonic() + timeout
    lock = InstanceLock(state / "freecad-startup.lock")
    while True:
        try:
            lock.__enter__()
            break
        except BrokerError:
            if time.monotonic() >= deadline:
                raise BrokerError("Another client is still starting the FreeCAD host") from None
            time.sleep(0.1)
    try:
        if probe(settings):
            return asyncio.run(status(state))
        if wait_stopped(state, deadline=deadline, allow_running=True):
            return asyncio.run(status(state))
        publication(path)
        with socket.socket() as sock:
            try:
                sock.bind((settings.host, settings.port))
            except OSError:
                raise BrokerError(
                    "FreeCAD host port is occupied; existing process preserved"
                ) from None
        child = spawn_serve(state, path, management_registry)
        while time.monotonic() < deadline:
            if probe(settings):
                return asyncio.run(status(state))
            if child.poll() is not None:
                raise BrokerError("FreeCAD host startup failed; inspect freecad-host.log")
            time.sleep(0.1)
        raise BrokerError("FreeCAD host startup timed out; inspect freecad-host.log")
    finally:
        lock.__exit__()


def doctor(state, path):
    from codex_freecad.runtime_features import feature_report

    desired = publication(path)
    require_state(state, path)
    value = asyncio.run(status(state))
    active = json.loads((state / "framework/active.json").read_bytes())
    release = active["release_id"]
    if (
        not isinstance(release, str)
        or len(release) != 64
        or any(c not in "0123456789abcdef" for c in release)
    ):
        raise BrokerError("Invalid active application release")
    selected = load_application(state / "framework/releases" / release / "definition.json")
    desired = desired.model_copy(
        update={"backends": sorted(desired.backends, key=lambda row: row.service.id)}
    )
    if selected != desired:
        raise BrokerError("Live backend publication differs from the requested installation")
    if (
        value.get("version") != FRAMEWORK_VERSION
        or {row["service_id"] for row in value["services"]}
        != {row.service.id for row in desired.backends}
        or any(service.get("status") != "available" for service in value["services"])
    ):
        raise BrokerError(
            "Live host version or backend availability differs from this installation"
        )
    return {
        "passed": True,
        "application_id": APPLICATION_ID,
        "framework": version("universal-codex-tools"),
        "mcp": version("mcp"),
        "app_host": version("freecad-mcp-host"),
        "feature_report": feature_report(
            protocol_mode=desired.backends[0].service.protocol_mode,
            watch_catalog=desired.backends[0].service.watch_catalog,
            discovery_cache_ttl_seconds=desired.backends[0].service.discovery_cache_ttl_seconds,
        ),
        "journals": journal_status(state),
        "resource_ownership": value.get("resource_ownership", {"state": "unassessed"}),
        "services": [
            {"id": row["service_id"], "tools": row["tool_count"]} for row in value["services"]
        ],
    }


def main():
    from codex_freecad.process_lifetime import ProcessSlots, process_lifetime, run_stdio

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument(
        "command",
        choices=[
            "init",
            "serve",
            "start",
            "connect",
            "proxy",
            "status",
            "stop",
            "validate",
            "doctor",
            "check-idle",
            "wait-stopped",
            "activate",
        ],
    )
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument("--modern-discovery", action="store_true")
    parser.add_argument("--previous-python", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--freecad-cmd", type=Path)
    parser.add_argument("--extensions", type=Path, action="append", default=[])
    parser.add_argument(
        "--protocol-mode", choices=["legacy", "auto", "2026-07-28"], default="legacy"
    )
    parser.add_argument(
        "--management-registry", type=Path, help="Explicit private registry for isolated testing"
    )
    args = parser.parse_args()
    state, path = args.state.expanduser().resolve(), args.publication.expanduser().resolve()
    try:
        check_runtime()
        if args.command == "activate":
            if not args.previous_python or not args.workspace or not args.backup:
                raise BrokerError("activate requires --previous-python, --workspace and --backup")
            print(
                json.dumps(
                    activate(
                        state,
                        path,
                        previous_python=args.previous_python,
                        workspace=args.workspace,
                        backup=args.backup,
                        port=args.port,
                        freecad_cmd=args.freecad_cmd,
                        extension_dirs=args.extensions,
                        protocol_mode=args.protocol_mode,
                        management_registry=args.management_registry,
                        modern_discovery=args.modern_discovery,
                    )
                )
            )
            return
        if args.command == "wait-stopped":
            require_state(state, path)
            wait_stopped(state)
            print(json.dumps({"stopped": True, "state_lock_released": True}))
            return
        if args.command in {"doctor", "check-idle"}:
            require_state(state, path)
            result = doctor(state, path) if args.command == "doctor" else require_idle(state)
            print(json.dumps(result))
            return
        if args.command in {"status", "stop"}:
            require_state(state, path)
            print(
                json.dumps(asyncio.run(status(state)) if args.command == "status" else stop(state))
            )
            return
        if args.command == "start":
            value = start(state, path, management_registry=args.management_registry)
            print(json.dumps(value))
            return
        if args.command == "connect":
            require_state(state, path)
            if probe(load_settings(state)) is None:
                raise BrokerError(
                    "FreeCAD host is stopped; an administrator must start it explicitly"
                )
            asyncio.run(status(state))  # Verify identity without starting any replacement.
            definition = publication(path)
            with ProcessSlots(state / "frontends"), process_lifetime(stdio=True, limit=8):
                run_stdio(
                    create_surface(
                        RemoteBackend(load_settings(state)),
                        name=definition.display_name,
                        instructions=definition.instructions,
                    )
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
                with process_lifetime():
                    serve(state, path, registry=args.management_registry)
            elif args.command == "proxy":
                # The app host must already be running. Never auto-start a universal daemon.
                with ProcessSlots(state / "frontends"), process_lifetime(stdio=True, limit=8):
                    run_stdio(
                        create_surface(
                            RemoteBackend(load_settings(state)),
                            name=definition.display_name,
                            instructions=definition.instructions,
                        )
                    )
    except (BrokerError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, "FreeCAD framework host: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
