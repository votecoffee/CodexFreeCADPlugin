"""Stable registry loading trusted installed Python extensions into fresh namespaces.

Code paths come from startup configuration, never a model or tool argument.
Source snapshots bypass .pyc caches, including relative helper imports.
"""

import copy
import hashlib
import importlib.abc
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path

from .engine import CadError
from .extension_schema import bounded_json, check_schema, validate

API_VERSION = 1
_registry = None


class Snapshot(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, folder, files):
        self.folder = folder
        self.prefix = "_codex_cad_extension_" + uuid.uuid4().hex
        self.sources = {}
        for name, content in files.items():
            if not name.endswith(".py"):
                continue
            package = name.endswith("__init__.py")
            suffix = name[:-12].rstrip("/") if package else name[:-3]
            fullname = self.prefix + ("." + suffix.replace("/", ".") if suffix else "")
            filename = str(folder / name)
            # Validate every helper before publication, including modules imported
            # only when a capability is first invoked. Compilation has no side effects.
            self.sources[fullname] = (compile(content, filename, "exec"), filename, package)
        sys.meta_path.insert(0, self)

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.sources:
            return importlib.util.spec_from_loader(
                fullname, self, is_package=self.sources[fullname][2]
            )
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        code, filename, package = self.sources[module.__name__]
        module.__file__ = filename
        if package:
            module.__path__ = []  # Relative imports resolve through this snapshot only.
        exec(code, module.__dict__)

    def load(self):
        import importlib

        return importlib.import_module(self.prefix)

    def close(self):
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        for name in list(sys.modules):
            if name == self.prefix or name.startswith(self.prefix + "."):
                del sys.modules[name]


class Generation:
    def __init__(self, revision, extensions):
        self.revision, self.extensions = revision, extensions
        self.snapshots = []
        self.modules, self.capabilities = {}, {}

    def close(self):
        for snapshot in self.snapshots:
            snapshot.close()


class Registry:
    def __init__(self, directories=(), builtin=None):
        self.directories = tuple(Path(p).expanduser().resolve() for p in directories)
        self.builtin = Path(builtin) if builtin else Path(__file__).with_name("extensions")
        self.active = None
        self.active = self.prepare()

    def scan(self):
        extensions = {}
        for root in (self.builtin, *self.directories):
            if not root.is_dir():
                raise CadError("Extension directory does not exist: " + str(root))
            for folder in sorted(root.iterdir()):
                if not folder.is_dir() or folder.name.startswith((".", "_")):
                    continue
                if not folder.resolve().is_relative_to(root.resolve()):
                    raise CadError("Extension package escapes its configured directory")
                manifest_path = folder / "manifest.json"
                if not manifest_path.is_file():
                    continue
                files = {}
                for path in sorted(folder.rglob("*")):
                    if (
                        not path.is_file()
                        or "__pycache__" in path.parts
                        or path.suffix not in {".py", ".json"}
                    ):
                        continue
                    if not path.resolve().is_relative_to(folder.resolve()):
                        raise CadError("Extension file escapes its package")
                    data = path.read_bytes()
                    if len(data) > 262144 or len(files) >= 128:
                        raise CadError("Extension package exceeds the file size/count limits")
                    files[path.relative_to(folder).as_posix()] = data
                if sum(map(len, files.values())) > 4 * 1024 * 1024 or "__init__.py" not in files:
                    raise CadError("Extension needs __init__.py and at most 4 MiB of source")
                try:
                    manifest = json.loads(files["manifest.json"])
                except (ValueError, KeyError, UnicodeError) as exc:
                    raise CadError("Invalid extension manifest: " + str(folder)) from exc
                self.check_manifest(manifest)
                name = manifest["id"]
                if name in extensions:
                    raise CadError("Duplicate extension id: " + name)
                digest = hashlib.sha256()
                for filename, data in sorted(files.items()):
                    digest.update(filename.encode() + b"\0" + data + b"\0")
                extensions[name] = {
                    "manifest": manifest,
                    "folder": folder,
                    "files": files,
                    "sha256": digest.hexdigest(),
                }
                if len(extensions) > 32:
                    raise CadError("At most 32 installed extensions are supported")
        return extensions

    @staticmethod
    def check_manifest(manifest):
        bounded_json(manifest)
        if not isinstance(manifest, dict) or set(manifest) != {
            "id",
            "version",
            "api_version",
            "description",
            "capabilities",
            "ui",
        }:
            raise CadError("Extension manifest fields must match extension API v1")
        if not isinstance(manifest["id"], str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,39}", manifest["id"]
        ):
            raise CadError("Invalid extension id")
        if not isinstance(manifest["version"], str) or not re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", manifest["version"]
        ):
            raise CadError("Extension version must use semantic version syntax")
        if type(manifest["api_version"]) is not int or manifest["api_version"] != API_VERSION:
            raise CadError("Unsupported extension API version")
        if not isinstance(manifest["description"], str) or type(manifest["ui"]) is not bool:
            raise CadError("Invalid extension description/UI declaration")
        if manifest["ui"] and manifest["id"] != "cad_panel":
            raise CadError("Only the installed cad_panel extension provides the dock lifecycle")
        capabilities = manifest["capabilities"]
        if not isinstance(capabilities, dict) or len(capabilities) > 100:
            raise CadError("An extension supports at most 100 named capabilities")
        for name, item in capabilities.items():
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", name)
                or not isinstance(item, dict)
                or set(item) != {"kind", "description", "handler", "parameters"}
            ):
                raise CadError("Invalid capability declaration")
            if (
                not isinstance(item["kind"], str)
                or item["kind"] not in {"query", "edit"}
                or not isinstance(item["description"], str)
            ):
                raise CadError("Capability kind must be query or edit")
            if not isinstance(item["handler"], str) or not re.fullmatch(
                r"[a-z][a-z0-9_]*", item["handler"]
            ):
                raise CadError("Capability handler must be a public function name")
            check_schema(item["parameters"])
            if item["parameters"]["type"] != "object":
                raise CadError("Capability parameters must be an object")

    def prepare(self):
        extensions = self.scan()
        revision = hashlib.sha256(
            json.dumps({k: v["sha256"] for k, v in extensions.items()}, sort_keys=True).encode()
        ).hexdigest()
        if self.active is not None and revision == self.active.revision:
            return None
        candidate = Generation(revision, extensions)
        try:
            for name, source in extensions.items():
                snapshot = Snapshot(source["folder"], source["files"])
                candidate.snapshots.append(snapshot)
                module = snapshot.load()
                candidate.modules[name] = module
                manifest = source["manifest"]
                if manifest["ui"] and any(
                    not callable(getattr(module, key, None))
                    for key in ("show", "shutdown", "capture_state", "restore_state")
                ):
                    raise CadError("CAD panel extension is missing lifecycle functions")
                for key, item in manifest["capabilities"].items():
                    handler = getattr(module, item["handler"], None)
                    if not callable(handler):
                        raise CadError("Missing capability handler: " + name + "." + key)
                    candidate.capabilities[name + "." + key] = {
                        **item,
                        "extension": name,
                        "version": manifest["version"],
                        "function": handler,
                    }
                    if len(candidate.capabilities) > 256:
                        raise CadError("At most 256 installed capabilities are supported")
            latest = self.scan()
            if {k: v["sha256"] for k, v in latest.items()} != {
                k: v["sha256"] for k, v in extensions.items()
            }:
                raise CadError(
                    "Extension files changed while loading; finish installing before reloading"
                )
            return candidate
        except Exception as exc:
            candidate.close()
            raise CadError(
                "Extension reload rejected; previous generation retained: " + str(exc)
            ) from exc

    def catalog(self):
        return {
            "extension_api_version": API_VERSION,
            "catalog_revision": self.active.revision,
            "extensions": [
                {
                    "id": name,
                    "version": item["manifest"]["version"],
                    "description": item["manifest"]["description"],
                    "sha256": item["sha256"],
                    "ui": item["manifest"]["ui"],
                }
                for name, item in self.active.extensions.items()
            ],
            "capabilities": [
                {
                    "name": name,
                    "kind": item["kind"],
                    "description": item["description"],
                    "extension_version": item["version"],
                }
                for name, item in self.active.capabilities.items()
            ],
        }

    def capability(self, name, revision=None, kind=None):
        if revision is not None and revision != self.active.revision:
            raise CadError("Extension catalog changed; describe the capability again")
        item = self.active.capabilities.get(name)
        if item is None:
            raise CadError("Unknown installed capability: " + str(name))
        if kind is not None and item["kind"] != kind:
            raise CadError("Capability requires the " + item["kind"] + " entry point")
        return item

    def describe(self, name):
        item = self.capability(name)
        return {
            "name": name,
            "catalog_revision": self.active.revision,
            **copy.deepcopy({k: v for k, v in item.items() if k != "function"}),
        }

    def invoke(self, engine, doc, name, arguments, kind, revision=None):
        item = self.capability(name, revision, kind)
        arguments = validate(item["parameters"], bounded_json(arguments))
        result = bounded_json(item["function"](engine, doc, arguments), maximum=1024 * 1024)
        return {
            "capability": name,
            "catalog_revision": self.active.revision,
            "extension_version": item["version"],
            "result": result,
        }


def peek_registry():
    return _registry


def close_registry():
    """Initial/core upgrade only; ordinary feature updates use Engine.reload_extensions."""
    global _registry
    if _registry is not None:
        _registry.active.close()
        _registry = None


def get_registry(directories=None):
    global _registry
    if directories is None and _registry is None:
        try:
            directories = json.loads(os.environ.get("CODEX_FREECAD_EXTENSION_PATHS", "[]"))
        except ValueError as exc:
            raise CadError(
                "CODEX_FREECAD_EXTENSION_PATHS must be a JSON list of directories"
            ) from exc
    if directories is not None and (
        not isinstance(directories, (tuple, list))
        or any(not isinstance(p, (str, Path)) for p in directories)
    ):
        raise CadError("Extension startup paths must be a list of directories")
    if _registry is None:
        _registry = Registry(directories or ())
    elif (
        directories is not None
        and tuple(Path(p).expanduser().resolve() for p in directories) != _registry.directories
    ):
        raise CadError(
            "Extension directories changed; restart the native backend to apply startup configuration"
        )
    return _registry
