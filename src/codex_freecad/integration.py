"""Plan or install a standalone Codex plugin or Universal Tools service registrations."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

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


def broker_services(servers, workspace, extension_dirs=()):
    fingerprint = hashlib.sha256(os.path.normcase(str(workspace)).encode()).hexdigest()[:16]
    result = {}
    for name, server in servers.items():
        args = [*server["args"], "--broker-catalog"]
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
            "capability_catalog": {
                "schema_version": 1,
                "tool": "list_broker_capabilities",
                "arguments": {},
            },
        }
    return result


def read_config(codex_home):
    path = codex_home / "config.toml"
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        for section in ("plugins", "mcp_servers"):
            entries = config.get(section, {})
            if not isinstance(entries, dict) or any(
                not isinstance(item, dict) for item in entries.values()
            ):
                raise ValueError("Invalid Codex configuration section: " + section)
        return config
    except (OSError, ValueError) as exc:
        raise ValueError(
            "Cannot read Codex configuration; select an explicit integration after repair"
        ) from exc


def detect_broker(codex_home, config):
    """Only an explicitly enabled, cached universal-tools plugin counts as installed."""
    enabled = [
        key
        for key, settings in config.get("plugins", {}).items()
        if key.startswith("universal-tools@") and settings.get("enabled") is True
    ]
    if not enabled:
        return None
    runtimes = set()
    for key in enabled:
        marketplace = key.split("@", 1)[1]
        if not marketplace or Path(marketplace).name != marketplace or marketplace in {".", ".."}:
            raise ValueError("Invalid Universal Tools marketplace name")
        cache = codex_home / "plugins" / "cache" / marketplace / "universal-tools"
        for runtime_file in cache.glob("*/runtime.json"):
            manifest = runtime_file.parent / "plugin.json"
            if not manifest.exists():
                manifest = runtime_file.parent / ".codex-plugin" / "plugin.json"
            try:
                if json.loads(manifest.read_text(encoding="utf-8"))["name"] != "universal-tools":
                    continue
                runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
                python, state = Path(runtime["python"]), Path(runtime["state"])
                if not python.is_absolute() or not state.is_absolute():
                    raise ValueError("Broker runtime paths must be absolute")
                if not python.is_file() or not (state / "settings.json").is_file():
                    raise ValueError("Broker runtime or initialized state is missing")
                runtimes.add((str(python.resolve()), str(state.resolve())))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(
                    "Enabled Universal Tools plugin has invalid cached runtime configuration"
                ) from exc
    if len(runtimes) != 1:
        raise ValueError(
            "Enabled Universal Tools runtime is missing or ambiguous; supply broker paths explicitly"
        )
    python, state = runtimes.pop()
    return {"python": python, "state": state}


def connection_plan(
    output, *, integration="auto", codex_home=None, broker_python=None, broker_state=None
):
    if integration not in {"auto", "broker", "standalone", "none"}:
        raise ValueError("Unknown Codex integration")
    output = Path(output).expanduser().resolve()
    codex_home = (
        Path(codex_home or os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        .expanduser()
        .resolve()
    )
    if integration == "none":
        return {"integration": "none", "commands": []}
    config = read_config(codex_home)
    if bool(broker_python) != bool(broker_state):
        raise ValueError("Supply both broker-python and broker-state")
    broker = None
    if integration in {"auto", "broker"}:
        broker = (
            {
                "python": str(Path(broker_python).expanduser().resolve()),
                "state": str(Path(broker_state).expanduser().resolve()),
            }
            if broker_python
            else detect_broker(codex_home, config)
        )
    selected = "broker" if broker else "standalone"
    if integration == "broker" and broker is None:
        raise ValueError("No enabled Universal Tools plugin found; supply explicit broker paths")
    commands, manifests = [], []
    if selected == "broker":
        # Do not silently duplicate an existing direct route or remove user configuration.
        if any(
            config.get("mcp_servers", {}).get(name, {}).get("enabled", True)
            for name in ("freecad-live", "freecad-headless")
            if name in config.get("mcp_servers", {})
        ) or any(
            key.startswith("freecad-modeling@") and item.get("enabled") is True
            for key, item in config.get("plugins", {}).items()
        ):
            raise ValueError(
                "FreeCAD direct integration is enabled; disable it explicitly before broker migration"
            )
        runtime = Path(broker["python"])
        state = Path(broker["state"])
        if not runtime.is_file() or not (state / "settings.json").is_file():
            raise ValueError("Broker Python or initialized broker state is missing")
        for name in ("freecad-live", "freecad-headless"):
            manifest = output / "broker" / (name + ".service.json")
            manifests.append(str(manifest))
            expected = json.loads(manifest.read_text(encoding="utf-8"))
            destination = state / "services" / (name + ".json")
            if destination.exists():
                previous = json.loads(destination.read_text(encoding="utf-8"))
                # Broker registration normalizes default fields; compare generated fields only.
                if any(previous.get(key) != value for key, value in expected.items()):
                    raise ValueError(
                        "Existing broker registration differs; review and replace it with broker CLI: "
                        + name
                    )
                continue
            commands.append(
                [
                    str(runtime),
                    "-m",
                    "universal_tools",
                    "--state",
                    str(state),
                    "register",
                    str(manifest),
                ]
            )
    else:
        if any(
            name in config.get("mcp_servers", {}) for name in ("freecad-live", "freecad-headless")
        ):
            raise ValueError(
                "Direct FreeCAD MCP entries already exist; use that connection or remove them before plugin installation"
            )
        plugin = output / "plugin" / ".codex-plugin" / "plugin.json"
        if not plugin.is_file():
            raise ValueError("Standalone plugin is missing; run setup first")
        marketplace = output
        commands = [
            ["codex", "plugin", "marketplace", "add", str(marketplace)],
            ["codex", "plugin", "add", "freecad-modeling@freecad-development"],
        ]
    return {
        "integration": selected,
        "codex_home": str(codex_home),
        "broker": broker,
        "commands": commands,
        "service_manifests": manifests,
        "next": "refresh_services" if broker else "Start a new Codex chat",
    }


def execute_plan(plan, *, run=subprocess.run):
    if plan["integration"] == "none":
        return
    environment = dict(os.environ, CODEX_HOME=plan["codex_home"])
    if plan["integration"] == "broker":
        manifests = plan["service_manifests"]
        # Validate every pending manifest with the actual runtime before registering either.
        # A newer cached plugin can still point at an older installed broker package.
        probe = [
            plan["broker"]["python"],
            "-c",
            "import sys; from pathlib import Path; from universal_tools.models import load_manifest; "
            "[load_manifest(Path(p)) for p in sys.argv[1:]]",
            *manifests,
        ]
        try:
            run(probe, check=True, env=environment, capture_output=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                "Broker runtime cannot validate FreeCAD service manifests. Upgrade Universal Tools "
                "to 0.8 or later, or explicitly choose the standalone plugin. No services were registered."
            ) from exc
    for command in plan["commands"]:
        # argv arrays and no shell preserve paths containing spaces and metacharacters.
        run(command, check=True, env=environment, stdout=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local"))
    parser.add_argument(
        "--integration", choices=["auto", "broker", "standalone", "none"], default="auto"
    )
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--broker-python", type=Path)
    parser.add_argument("--broker-state", type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="Execute the plan; otherwise preview only"
    )
    args = parser.parse_args()
    try:
        plan = connection_plan(
            args.output,
            integration=args.integration,
            codex_home=args.codex_home,
            broker_python=args.broker_python,
            broker_state=args.broker_state,
        )
        if args.apply and plan["integration"] != "none":
            execute_plan(plan)
        print(json.dumps(plan, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, "FreeCAD Codex integration: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
