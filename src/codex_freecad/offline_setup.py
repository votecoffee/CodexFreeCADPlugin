"""Prepare a separate immutable offline plugin candidate; never install or start it."""

import argparse
import hashlib
import json
from importlib.metadata import distributions
from pathlib import Path

from . import __package_version__, __version__
from .framework_setup import atomic_json
from .offline_interpreter import pe_identity, windowless_interpreter


def inventory(root):
    result, total = {}, 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or getattr(path.stat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("Offline runtime cannot contain links or junctions")
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise ValueError("Offline runtime must contain wheel sources without bytecode caches")
        if not path.is_file():
            continue
        total += path.stat().st_size
        if len(result) >= 20000 or total > 256 * 1024 * 1024:
            raise ValueError("Offline runtime exceeds its file/byte budget")
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def generate(workspace, output, runtime, *, python=None, state=None, registry=None):
    workspace, runtime = Path(workspace).resolve(strict=True), Path(runtime).resolve(strict=True)
    output = Path(output).resolve()
    state = Path(state or output / "state").absolute()
    registry = Path(registry or output / "registry").absolute()
    if not workspace.is_dir() or not runtime.is_dir() or output.exists():
        raise ValueError("Use existing workspace/runtime directories and a fresh candidate output")
    interpreter = windowless_interpreter(python)
    versions = {
        d.metadata["Name"].lower().replace("_", "-"): d.version
        for d in distributions(path=[str(runtime)])
    }
    expected = {
        "codex-freecad": __package_version__,
        "mcp": "2.3.0",
        "universal-codex-tools": "0.20.0",
    }
    if any(versions.get(name) != value for name, value in expected.items()):
        raise ValueError("Offline runtime must contain the checkpoint and exact reviewed pins")
    if output.is_relative_to(runtime):
        raise ValueError("Keep candidate state/configuration outside its immutable runtime")
    if not (runtime / "codex_freecad/offline.py").is_file() or json.loads(
        (runtime / "codex_freecad/release.json").read_bytes()
    ) != json.loads(Path(__file__).with_name("release.json").read_bytes()):
        raise ValueError("Offline runtime source checkpoint differs from the generator")
    files = inventory(runtime)
    if (
        not {
            "codex_freecad/" + name
            for name in (
                "__init__.py",
                "release.json",
                "process_lifetime.py",
                "offline_session.py",
                "offline_interpreter.py",
            )
        }
        <= files.keys()
    ):
        raise ValueError("Offline runtime is missing its standard-library bootstrap guard")
    manifest = json.dumps({"runtime": str(runtime), "files": files}, sort_keys=True).encode()
    if len(manifest) > 8 * 1024 * 1024:
        raise ValueError("Offline closure manifest exceeds its byte budget")
    manifest_hash = hashlib.sha256(manifest).hexdigest()
    output.mkdir(parents=True)
    (output / "closure.json").write_bytes(manifest)
    launcher = (
        '"""Generated immutable offline entry; use paired real pythonw.exe -I -S -B."""\n'
        "import ctypes,hashlib,io,json,msvcrt,os,struct,sys,threading,traceback\nfrom contextlib import contextmanager\nfrom pathlib import Path\n"
        "root=Path(__file__).resolve().parent\n"
        "with (root/'closure.json').open('rb') as stream: raw=stream.read(8*1024*1024+1)\n"
        f"if hashlib.sha256(raw).hexdigest() != {manifest_hash!r}:\n"
        "    raise RuntimeError('Offline closure manifest changed')\n"
        "closure=json.loads(raw); runtime=Path(closure['runtime']); actual={}\n"
        "if runtime.is_symlink() or getattr(runtime.stat(),'st_file_attributes',0)&0x400:\n"
        "    raise RuntimeError('Offline runtime root link/junction refused')\n"
        "if (runtime/'codex_freecad/__pycache__').exists() or list((runtime/'codex_freecad').glob('*.py[co]')):\n"
        "    raise RuntimeError('Offline bootstrap bytecode cache refused')\n"
        "for name in ('__init__.py','release.json','process_lifetime.py','offline_session.py','offline_interpreter.py'):\n"
        "    key='codex_freecad/'+name; p=runtime/key\n"
        "    if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=closure['files'][key]:\n"
        "        raise RuntimeError('Offline bootstrap code changed')\n"
        "sys.path.insert(0,str(runtime))\n"
        "from codex_freecad.offline_interpreter import require_windowless_root,inherited_stdio\n"
        "require_windowless_root(); inherited_stdio()\n"
        "from codex_freecad.offline_session import root_lifetime\n"
        f"with root_lifetime({str(state)!r}):\n"
        "    total=0\n"
        "    for p in runtime.rglob('*'):\n"
        "        if p.is_symlink() or getattr(p.stat(),'st_file_attributes',0)&0x400:\n"
        "            raise RuntimeError('Offline runtime link/junction refused')\n"
        "        if '__pycache__' in p.parts or p.suffix in ('.pyc','.pyo'):\n"
        "            raise RuntimeError('Offline runtime bytecode cache refused')\n"
        "        if p.is_file():\n"
        "            total+=p.stat().st_size\n"
        "            if len(actual)>=20000 or total>256*1024*1024: raise RuntimeError('Offline runtime budget exceeded')\n"
        "            with p.open('rb') as stream: actual[p.relative_to(runtime).as_posix()]=hashlib.file_digest(stream,'sha256').hexdigest()\n"
        "    if actual != closure['files']:\n"
        "        raise RuntimeError('Offline runtime bytes/file set changed')\n"
        "    sys.path[:0]=[str(runtime/'win32'),str(runtime/'win32/lib'),str(runtime/'Pythonwin')]\n"
        "    if sys.platform=='win32':\n"
        "        import pywin32_bootstrap\n"
        "    from codex_freecad.offline import main\n    main()\n"
    )
    before_guard, guarded = launcher.split("with root_lifetime(", 1)
    guarded = "with root_lifetime(" + guarded
    launcher = (
        before_guard
        + "result=0\ntry:\n"
        + "".join("    " + line for line in guarded.splitlines(keepends=True))
        + "except SystemExit as exc:\n"
        "    result=exc.code if isinstance(exc.code,int) else 1\n"
        "except BaseException:\n"
        "    result=1; traceback.print_exc(file=sys.stderr)\n"
        "finally:\n"
        "    for stream in (sys.stdout,sys.stderr):\n"
        "        try: stream.flush()\n"
        "        except BaseException: pass\n"
        "    os._exit(result)\n"
    )
    (output / "offline-launch.py").write_bytes(launcher.encode())
    plugin = output / "plugin"
    atomic_json(
        plugin / ".codex-plugin/plugin.json",
        {
            "name": "freecad-modeling",
            "version": __package_version__,
            "description": f"FreeCAD {__version__}: bounded read-only offline FCStd inspection",
            "mcpServers": "./.mcp.json",
            "skills": "./skills/",
            "requires_local_executor": True,
            "interface": {
                "displayName": "FreeCADMCPServer (offline)",
                "shortDescription": "Read-only FCStd package inspection",
            },
        },
    )
    atomic_json(
        plugin / ".mcp.json",
        {
            "mcpServers": {
                "freecad": {
                    "command": str(interpreter),
                    "args": [
                        "-I",
                        "-S",
                        "-B",
                        str(output / "offline-launch.py"),
                        "--workspace",
                        str(workspace),
                        "--state",
                        str(state),
                        "--registry",
                        str(registry),
                    ],
                }
            }
        },
    )
    atomic_json(
        plugin / "release.json", json.loads(Path(__file__).with_name("release.json").read_bytes())
    )
    skill = plugin / "skills/freecad-offline/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(Path(__file__).with_name("standalone_offline_skill.md").read_bytes())
    atomic_json(
        output / ".agents/plugins/marketplace.json",
        {
            "name": "freecad-development",
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
    result = {
        "profile": "direct-standalone-offline",
        "version": __version__,
        "package_version": __package_version__,
        "plugin": str(plugin),
        "runtime": str(runtime),
        "python": str(interpreter),
        "python_sha256": hashlib.sha256(interpreter.read_bytes()).hexdigest(),
        "python_image": pe_identity(interpreter),
        "python_kind": "paired-real-windowless-base-interpreter",
        "closure_sha256": manifest_hash,
        "launcher_sha256": hashlib.sha256(launcher.encode()).hexdigest(),
        "native_execution": False,
        "installed": False,
        "started": False,
    }
    atomic_json(output / "candidate.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.workspace, args.output, args.runtime), indent=2))


if __name__ == "__main__":
    main()
