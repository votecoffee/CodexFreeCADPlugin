"""Direct standalone offline MCP profile. No native or outgoing MCP transport."""

import argparse
import hashlib
import os
from pathlib import Path
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __package_version__, __version__
from .offline_files import bundled_capabilities, inspect_fcstd
from .offline_interpreter import inherited_stdio, require_windowless_root
from .offline_session import Admission, offline_session, run_offline

PROFILE = "direct-standalone-offline"
TOOLS = (
    "freecad_offline_status",
    "get_offline_workflow",
    "list_bundled_capabilities",
    "inspect_fcstd_package",
)
READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def create_offline_server(workspace, admission):
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Configure an existing offline workspace directory")
    server = MCPServer(
        "FreeCAD offline",
        version=__version__,
        instructions="Read-only FCStd ZIP/XML inspection and bundled schema references. No native "
        "FreeCAD, geometry evaluation, model edits, external extensions, bridge, shared host, "
        "SCM or controller routes exist in this profile. Read get_offline_workflow first.",
    )

    @server.tool(annotations=READ)
    def freecad_offline_status() -> dict:
        """Read this fixed offline profile's version and refused routes; no app discovery."""
        with admission.operation():
            return {
                "profile": PROFILE,
                "app_version": __version__,
                "app_package_version": __package_version__,
                "tools": list(TOOLS),
                "native_execution": False,
                "child_processes": [],
                "refused_routes": [
                    "native",
                    "live-bridge",
                    "shared-host",
                    "external-extension",
                    "controller",
                    "SCM",
                    "shell",
                    "outgoing-MCP",
                ],
            }

    @server.tool(annotations=READ)
    def get_offline_workflow() -> dict:
        """Read bounded bundled offline guidance and its SHA-256."""
        with admission.operation():
            raw = Path(__file__).with_name("guidance").joinpath("offline.md").read_bytes()
            if len(raw) > 32768:
                raise ValueError("Offline guide exceeds its budget")
            return {
                "profile": PROFILE,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "text": raw.decode("utf-8"),
            }

    @server.tool(annotations=READ)
    def list_bundled_capabilities() -> dict:
        """Read bundled native capability schemas as references; handlers cannot be invoked."""
        with admission.operation():
            return bundled_capabilities()

    @server.tool(annotations=READ)
    def inspect_fcstd_package(
        path: Annotated[str, Field(min_length=1, max_length=1024)],
        expected_sha256: Annotated[str | None, Field(pattern=r"^[0-9a-f]{64}$")] = None,
    ) -> dict:
        """Inspect FCStd bytes within the configured workspace without opening a native document.

        Streams bounded ZIP payloads for CRC/SHA checks and reads Document.xml object names/types.
        No geometry, expressions, macros or saved Python proxies are evaluated. No files are written.
        """
        with admission.operation():
            return inspect_fcstd(workspace, path, expected_sha256)

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Offline lifetime containment currently requires Windows")
    try:
        require_windowless_root()
        inherited_stdio()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    admission = Admission()
    server = create_offline_server(args.workspace, admission)
    run_offline(
        server, offline_session(args.state, args.registry, admission), exit_process=os._exit
    )


if __name__ == "__main__":
    main()
