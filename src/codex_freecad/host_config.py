"""Application-owned backend definitions for the experimental FreeCAD host."""

import hashlib
import os

PROTOCOL_MODES = ("legacy", "auto", "2026-07-28")

WRITE_TOOLS = [
    "reload_extensions",
    "new_document",
    "open_document",
    "import_model",
    "apply_operations",
    "undo_document",
    "save_document",
    "export_model",
    "set_view",
    "capture_view",
]


def backend_services(
    servers, workspace, extension_dirs=(), *, protocol_mode="legacy", modern_discovery=False
):
    if modern_discovery and protocol_mode == "legacy":
        raise ValueError("Modern discovery requires explicit auto/modern protocol")
    fingerprint = hashlib.sha256(os.path.normcase(str(workspace)).encode()).hexdigest()[:16]
    result = {}
    for name, server in servers.items():
        args = list(server["args"])
        if name == "freecad-live":
            for directory in extension_dirs:
                args += ["--extensions", directory]
        result[name] = {
            "schema_version": 1,
            "id": name,
            "display_name": "FreeCADMCPServer (" + name.removeprefix("freecad-") + ")",
            "description": "Native FreeCAD modeling with persistent documents and Undo.",
            "transport": {
                "type": "stdio",
                "command": server["command"],
                "args": args,
                "cwd": None,
                "env_vars": [],
            },
            "enabled": True,
            "allow_writes": True,
            "allowed_write_tools": WRITE_TOOLS.copy(),
            "session_mode": "exclusive",
            "resource_id": name + "-" + fingerprint,
            "timeout_seconds": 150.0,
            "max_argument_bytes": 8 * 1024 * 1024,
            "max_argument_depth": 64,
            "max_argument_nodes": 100_000,
            "capability_catalog": {
                "schema_version": 1,
                "tool": "list_host_capabilities",
                "arguments": {},
            },
        }
        if protocol_mode != "legacy":
            result[name]["protocol_mode"] = protocol_mode
        if modern_discovery:
            result[name].update(watch_catalog=True, discovery_cache_ttl_seconds=2)
    return result
