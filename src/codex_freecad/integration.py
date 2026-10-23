"""Plan or install FreeCAD's standalone Codex plugin."""

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path


def read_config(codex_home):
    path = codex_home / "config.toml"
    try:
        # Universal-newline reads can hide malformed CRCRLF from this preflight
        # even though the Codex CLI will reject the original bytes.
        config = tomllib.loads(path.read_bytes().decode("utf-8-sig")) if path.exists() else {}
        for section in ("plugins", "mcp_servers"):
            entries = config.get(section, {})
            if not isinstance(entries, dict) or any(
                not isinstance(item, dict) for item in entries.values()
            ):
                raise ValueError("Invalid Codex configuration section: " + section)
        return config
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot read Codex configuration; repair it before installation") from exc


def connection_plan(output, *, integration="standalone", codex_home=None):
    if integration not in {"standalone", "none"}:
        raise ValueError("Choose standalone or none for the Codex integration")
    if integration == "none":
        return {"integration": "none", "commands": []}
    output = Path(output).expanduser().resolve()
    codex_home = (
        Path(codex_home or os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        .expanduser()
        .resolve()
    )
    config = read_config(codex_home)
    if any(name in config.get("mcp_servers", {}) for name in ("freecad-live", "freecad-headless")):
        raise ValueError(
            "Direct FreeCAD MCP entries already exist; use that connection or remove them before plugin installation"
        )
    plugin = output / "plugin" / ".codex-plugin" / "plugin.json"
    if not plugin.is_file():
        raise ValueError("Standalone plugin is missing; run setup first")
    return {
        "integration": "standalone",
        "codex_home": str(codex_home),
        "commands": [
            ["codex", "plugin", "marketplace", "add", str(output)],
            ["codex", "plugin", "add", "freecad-modeling@freecad-development"],
        ],
        "next": "Start a new Codex chat",
    }


def execute_plan(plan, *, run=subprocess.run):
    if plan["integration"] == "none":
        return
    if plan["integration"] != "standalone":
        raise ValueError("Only standalone plugin installation is supported")
    environment = dict(os.environ, CODEX_HOME=plan["codex_home"])
    for command in plan["commands"]:
        # argv arrays and no shell preserve paths containing spaces and metacharacters.
        run(command, check=True, env=environment, stdout=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local"))
    parser.add_argument("--integration", choices=["standalone", "none"], default="standalone")
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="Execute the plan; otherwise preview only"
    )
    args = parser.parse_args()
    try:
        plan = connection_plan(
            args.output, integration=args.integration, codex_home=args.codex_home
        )
        if args.apply:
            execute_plan(plan)
        print(json.dumps(plan, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, "FreeCAD Codex integration: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
