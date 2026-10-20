"""Publish an experimental app-owned framework candidate without changing installed routes."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .host_config import PROTOCOL_MODES, backend_services

INSTRUCTIONS = (
    "FreeCADMCPServer experimental app-owned host. Search and describe current FreeCAD tools. "
    "Acquire freecad-live or freecad-headless and retain that context. Read get_workflow overview. "
    "Inspect explicit documents before editing and preserve document/catalog revisions. Writes "
    "require unique request IDs. Do not replay an uncertain write or switch routes to bypass it. "
    "Save before releasing headless contexts. Use this application's own standalone connection."
)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, pending = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


def source_files(source, prefix):
    source = Path(source).resolve()
    result = {}
    for path in sorted(source.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError("Publication source cannot contain symlinks")
        if path.is_file():
            if not path.resolve().is_relative_to(source):
                raise ValueError("Publication source escapes its package")
            result[prefix + path.relative_to(source).as_posix()] = path.read_bytes()
    return result


def publish(
    workspace,
    output,
    host_python,
    *,
    backend_python=None,
    freecad_cmd=None,
    extension_dirs=(),
    source_package=None,
    protocol_mode="legacy",
):
    """Local admin publication only. This function never starts a host/native app or installs a plugin."""
    if protocol_mode not in PROTOCOL_MODES:
        raise ValueError("Unsupported backend protocol mode")
    workspace, output = Path(workspace).expanduser().resolve(), Path(output).expanduser().resolve()
    host_python = Path(host_python).expanduser().resolve()
    backend_python = Path(backend_python or sys.executable).expanduser().resolve()
    if not host_python.is_file() or not backend_python.is_file():
        raise ValueError("Host and backend Python executables must exist")
    source = Path(source_package or Path(__file__).parent).resolve()
    if not (source / "server.py").is_file() or not (source / "__init__.py").is_file():
        raise ValueError("Publish a complete codex_freecad source package")
    files = source_files(source, "package/codex_freecad/")
    for index, directory in enumerate(extension_dirs):
        directory = Path(directory).expanduser().resolve()
        if not directory.is_dir():
            raise ValueError("Installed extension root is missing")
        files.update(source_files(directory, f"extensions/{index}/"))
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    closure = json.dumps({"schema_version": 1, "files": hashes}, sort_keys=True).encode()
    closure_hash = hashlib.sha256(closure).hexdigest()
    launcher = (
        '"""Immutable FreeCAD backend entry; verify the packaged code/resources before import."""\n'
        "import hashlib, json, sys\nfrom pathlib import Path\n"
        "root = Path(__file__).resolve().parent\n"
        "raw = (root / 'closure.json').read_bytes()\n"
        f"if hashlib.sha256(raw).hexdigest() != {closure_hash!r}:\n"
        "    raise RuntimeError('Backend closure manifest changed')\n"
        "files = json.loads(raw)['files']\n"
        "actual = set()\n"
        "for path in root.rglob('*'):\n"
        "    if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):\n"
        "        continue\n"
        "    if path.is_symlink():\n"
        "        raise RuntimeError('Backend closure contains a symlink')\n"
        "    if path.is_file():\n"
        "        actual.add(path.relative_to(root).as_posix())\n"
        "if actual != set(files) | {'launcher.py', 'closure.json'}:\n"
        "    raise RuntimeError('Backend closure file set changed')\n"
        "for name, digest in files.items():\n"
        "    if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:\n"
        "        raise RuntimeError('Backend closure file changed: ' + name)\n"
        "sys.path.insert(0, str(root / 'package'))\n"
        "from codex_freecad.server import main\nmain()\n"
    ).encode()
    content_revision = hashlib.sha256(closure + launcher).hexdigest()
    deployment = output / "deployments" / content_revision
    complete = {**files, "closure.json": closure, "launcher.py": launcher}
    if deployment.exists():
        actual = source_files(deployment, "")
        if actual != complete:
            raise ValueError(
                "Existing immutable backend deployment changed; original was preserved"
            )
    else:
        stage = Path(tempfile.mkdtemp(prefix="stage-", dir=_deployment_parent(output)))
        try:
            for name, data in complete.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            stage.rename(deployment)
        except BaseException:
            # Preserve a failed stage for inspection; no publication selects it.
            raise
    servers = {}
    for mode in ("live", "headless"):
        args = [
            "-B",
            str(deployment / "launcher.py"),
            "--mode",
            mode,
            "--workspace",
            str(workspace),
            "--framework-backend",
        ]
        if mode == "headless" and freecad_cmd:
            path = Path(freecad_cmd).expanduser().resolve()
            if not path.is_file():
                raise ValueError("FreeCADCmd executable is missing")
            args += ["--freecad-cmd", str(path)]
        servers["freecad-" + mode] = {"command": str(backend_python), "args": args}
    extensions = [str(deployment / "extensions" / str(i)) for i, _ in enumerate(extension_dirs)]
    for name in servers:
        if name.endswith("headless"):
            for directory in extensions:
                servers[name]["args"] += ["--extensions", directory]
    services = backend_services(servers, workspace, extensions, protocol_mode=protocol_mode)
    backends = []
    for service in services.values():
        revision = hashlib.sha256(
            json.dumps({"content": content_revision, "service": service}, sort_keys=True).encode()
        ).hexdigest()
        backends.append(
            {
                "revision": revision,
                "service": service,
                "artifact": {
                    "path": str(deployment / "launcher.py"),
                    "sha256": hashlib.sha256(launcher).hexdigest(),
                },
            }
        )
    definition = {
        "schema_version": 1,
        "id": "freecad-mcp-server",
        "display_name": "FreeCADMCPServer",
        "instructions": INSTRUCTIONS,
        "backends": backends,
    }
    publication = output / "application.json"
    atomic_json(publication, definition)
    plugin = output / "plugin"
    atomic_json(
        plugin / ".codex-plugin/plugin.json",
        {
            "name": "freecad-modeling",
            "version": __version__,
            "description": "Experimental FreeCAD app-owned framework connection",
            "mcpServers": "./.mcp.json",
            "skills": "./skills/",
            "requires_local_executor": True,
            "interface": {
                "displayName": "FreeCADMCPServer",
                "shortDescription": "Stable app-owned FreeCAD host",
            },
        },
    )
    state = output / "state"
    command = ["-m", "freecad_mcp_host", "--state", str(state), "--publication", str(publication)]
    atomic_json(
        plugin / ".mcp.json",
        {
            "mcpServers": {
                "freecad": {
                    "command": str(host_python),
                    "args": [*command, "proxy"],
                }
            }
        },
    )
    skill = plugin / "skills/freecad-modeling/SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_bytes(files["package/codex_freecad/standalone_skill.md"])
    atomic_json(
        output / ".agents/plugins/marketplace.json",
        {
            "name": "freecad-framework-experimental",
            "interface": {"displayName": "FreeCAD framework candidate"},
            "plugins": [
                {
                    "name": "freecad-modeling",
                    "source": {"source": "local", "path": "./plugin"},
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    "category": "Productivity",
                }
            ],
        },
    )
    return {
        "publication": str(publication),
        "deployment": str(deployment),
        "state": str(state),
        "plugin": str(plugin),
        "framework": "0.15.0",
        "protocol_mode": protocol_mode,
        "content_revision": content_revision,
        "host_commands": {
            name: [str(host_python), *command, name] for name in ("init", "serve", "status", "stop")
        },
    }


def _deployment_parent(output):
    path = output / "deployments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".local/framework-candidate"))
    parser.add_argument("--host-python", type=Path, required=True)
    parser.add_argument("--backend-python", type=Path)
    parser.add_argument("--freecad-cmd", type=Path)
    parser.add_argument("--extensions", type=Path, action="append", default=[])
    parser.add_argument("--protocol-mode", choices=PROTOCOL_MODES, default="legacy")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                publish(
                    args.workspace,
                    args.output,
                    args.host_python,
                    backend_python=args.backend_python,
                    freecad_cmd=args.freecad_cmd,
                    extension_dirs=args.extensions,
                    protocol_mode=args.protocol_mode,
                ),
                indent=2,
            )
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, "FreeCAD framework publication: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
