"""Read the explicit local framework selection without importing any host dependencies."""

import argparse
import json
from pathlib import Path

from .host_config import PROTOCOL_MODES, backend_services


def selected_host(output):
    output = Path(output).expanduser().resolve()
    marker = output / "framework-installation.json"
    if not marker.exists():
        return None
    try:
        value = json.loads(marker.read_bytes())
        root = output / "framework"
        python = Path(value["python"]).resolve()
        if (
            value["schema_version"] != 1
            or value["application_id"] != "freecad-mcp-server"
            or Path(value["output"]).resolve() != root
            or not python.is_relative_to(root / "runtimes")
            or not python.is_file()
            or not (root / "application.json").is_file()
            or not (root / "plugin/.mcp.json").is_file()
        ):
            raise ValueError("Invalid installation binding")
        publication = root / "application.json"
        config = json.loads((root / "plugin/.mcp.json").read_bytes())
        expected = {
            "mcpServers": {
                "freecad": {
                    "command": str(python),
                    "args": [
                        "-m",
                        "freecad_mcp_host",
                        "--state",
                        str(root / "state"),
                        "--publication",
                        str(publication),
                        "connect",
                    ],
                }
            }
        }
        if config != expected or json.loads(publication.read_bytes())["id"] != "freecad-mcp-server":
            raise ValueError("Selected plugin/publication binding changed")
        return {**value, "output": str(root), "python": str(python)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            "Invalid selected FreeCAD framework installation; repair it before setup or launch"
        ) from exc


def upgrade_plan(output):
    selected = selected_host(output)
    if selected is None:
        raise ValueError("Upgrade requires an existing selected framework installation")
    try:
        definition = json.loads((Path(selected["output"]) / "application.json").read_bytes())
        backends = {row["service"]["id"]: row["service"] for row in definition["backends"]}
        if len(definition["backends"]) != 2 or set(backends) != {
            "freecad-live",
            "freecad-headless",
        }:
            raise ValueError("Unexpected backend selection")
        modes = {service.get("protocol_mode", "legacy") for service in backends.values()}
        if len(modes) != 1:
            raise ValueError("Mixed backend protocol choices")
        mode = modes.pop()
        if mode not in PROTOCOL_MODES:
            raise ValueError("Unsupported backend protocol choice")
        servers = {
            name: {"command": row["transport"]["command"], "args": row["transport"]["args"]}
            for name, row in backends.items()
        }
        modern_discovery = all(
            row.get("watch_catalog") is True and row.get("discovery_cache_ttl_seconds") == 2
            for row in backends.values()
        )
        expected = backend_services(
            servers,
            Path(selected["workspace"]).resolve(),
            protocol_mode=mode,
            modern_discovery=modern_discovery,
        )
        if backends != expected:
            raise ValueError("Custom backend policy/configuration requires a separate publication")
        args = backends["freecad-headless"]["transport"]["args"]
        extensions = [args[i + 1] for i, arg in enumerate(args) if arg == "--extensions"]
        executable = args[args.index("--freecad-cmd") + 1] if "--freecad-cmd" in args else None
        return {
            **selected,
            "protocol_mode": mode,
            "extension_dirs": extensions,
            "freecad_cmd": executable,
            "modern_discovery": modern_discovery,
        }
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise ValueError("Cannot preserve this publication automatically: " + str(exc)) from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upgrade-plan", action="store_true")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                upgrade_plan(args.output) if args.upgrade_plan else selected_host(args.output)
            )
        )
    except ValueError as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
