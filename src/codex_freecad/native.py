"""Standalone native profile with reviewed targets and retained uncertainty fences."""

import argparse
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path

from . import __package_version__, __version__
from .native_session import NativeClient


def verify_file(path, expected):
    with Path(path).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("Reviewed native executable/bridge binding changed")


@contextmanager
def native_session(client, state, registry):
    from universal_tools.management import ComponentVersion, ManagedService, ManagedStatus
    from universal_tools.resources import durable_json

    from .offline_session import root_lifetime
    from .process_lifetime import ProcessSlots
    from .resource_ownership import resource_session

    path = None
    try:
        with (
            root_lifetime(state, process_limit=4),
            # Keep the profile's lifetime bound explicit as well as the early
            # bootstrap's shared `frontends` lease. History is a separate bound.
            ProcessSlots(Path(state) / "native-frontends", limit=4),
            resource_session(registry, state=state) as owner,
        ):
            folder = Path(state) / "native-sessions"
            folder.mkdir(parents=True, exist_ok=True)
            record = {
                "profile": "direct-standalone-native",
                "version": __version__,
                "owner": owner.identity.model_dump(mode="json"),
                "owner_id": owner.owner_id,
                "mode": client.mode,
                "receipt_generation": client.generation,
                "state": "active",
            }
            # Metadata frontends can coexist; keep the history bound atomic.
            with ProcessSlots(Path(state) / "history-admission", limit=1):
                if len(list(folder.glob("*.json"))) >= 256:
                    raise RuntimeError("Native root history full; preserve the original evidence")
                path = folder / (owner.owner_id + ".json")
                durable_json(path, record)

            def status():
                from .stable_launcher import deployment_info

                deployment = deployment_info()
                update_pending = bool(
                    deployment["selected_package_version"]
                    and (
                        deployment["selected_package_version"] != __package_version__
                        or deployment.get("selected_snapshot") != deployment.get("running_snapshot")
                    )
                )
                return ManagedStatus(
                    state="degraded"
                    if client.uncertain
                    else "busy"
                    if client.lock.locked()
                    else "running",
                    message=f"FreeCAD {__version__}; {client.mode} MCP frontend; native lease held={client.native_admitted}; backend validated={client.validated}. Metadata is not native health.",
                    active_operations=int(client.lock.locked()),
                    restart_allowed=False,
                    restart_reason="Native documents/receipts require inspection; close the owning client",
                    versions={
                        "app": ComponentVersion(
                            installed=deployment["selected_package_version"] or "not-reporting",
                            running=__package_version__,
                            update_pending=update_pending,
                        )
                    },
                )

            with ManagedService(
                "freecad-mcp-server",
                "FreeCADMCPServer (native)",
                status,
                plugin_id="freecad-modeling@freecad-development",
                registry=registry,
            ):
                try:
                    yield
                finally:
                    client.close()
    except BaseException:
        if path is not None:
            durable_json(path, {**record, "state": "uncertain"})
        raise
    else:
        durable_json(path, {**record, "state": "closed"})


def run_native(server, client, state, registry, *, exit_process):
    from .process_lifetime import run_stdio

    result = []
    try:
        with native_session(client, state, registry):
            run_stdio(server, exit_process=result.append, close_resources=False)
    except BaseException:
        result[:] = [1]
        raise
    finally:
        exit_process(result[0] if result else 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--mode", choices=["headless", "live"], required=True)
    parser.add_argument("--native-target", type=Path, required=True)
    parser.add_argument("--expected-target-sha256", required=True)
    args = parser.parse_args()
    from .client import HeadlessClient, LiveClient
    from .offline_interpreter import inherited_stdio, require_windowless_root
    from .server import READ, create_server

    require_windowless_root()
    inherited_stdio()
    target = args.native_target.resolve(strict=True)
    verify_file(target, args.expected_target_sha256)
    if args.mode == "headless":
        backend = HeadlessClient(
            args.workspace,
            str(target),
            extension_dirs=[],
            executable_sha256=args.expected_target_sha256,
        )
        binding_check = None
    else:
        backend = LiveClient(target)

        def binding_check():
            verify_file(target, args.expected_target_sha256)

    client = NativeClient(
        backend, args.workspace, args.state, mode=args.mode, binding_check=binding_check
    )
    server = create_server(client)

    @server.tool(annotations=READ)
    def review_native_target(path: str) -> dict:
        """Review exact workspace source/output bytes before native open/save/export; no native open."""
        from mcp.server.mcpserver.exceptions import ToolError

        from .native_session import NativePolicyError

        try:
            return client.review_target(path)
        except NativePolicyError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=READ)
    def get_native_workflow() -> dict:
        """Read the fixed native profile guide and its SHA-256 before modeling."""
        raw = Path(__file__).with_name("guidance").joinpath("native.md").read_bytes()
        from .stable_launcher import deployment_info

        return {
            "profile": "direct-standalone-native",
            "mode": args.mode,
            "text": raw.decode("utf-8"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "deployment": {**deployment_info(), "running_package_version": __package_version__},
        }

    run_native(server, client, args.state, args.registry, exit_process=os._exit)


if __name__ == "__main__":
    main()
