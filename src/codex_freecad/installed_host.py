"""Read the explicit local framework selection without importing any host dependencies."""

import argparse
import json
from pathlib import Path


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(selected_host(args.output)))
    except ValueError as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
