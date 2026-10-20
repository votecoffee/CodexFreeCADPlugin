"""Disposable provider below the original MCP handlers. Never imports a native CAD API."""

import base64
import copy
import json
import os
from pathlib import Path

GENERATION = 1
PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lS8AAAAASUVORK5CYII="
    )
).decode()


class FixtureClient:
    def __init__(self, workspace, *args, **kwargs):
        self.workspace = Path(workspace)
        if self.workspace.suffix == ".json":
            self.workspace = self.workspace.parent
        self.documents = {}
        self.history = {}
        self.revision = 0

    def close(self):
        pass

    def effect(self, method):
        self.workspace.mkdir(parents=True, exist_ok=True)
        with (self.workspace / "effects.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"method": method, "pid": os.getpid()}) + "\n")

    def call(self, method, **params):
        from codex_freecad.engine import CadError

        self.workspace.mkdir(parents=True, exist_ok=True)
        with (self.workspace / "calls.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"method": method, "pid": os.getpid()}) + "\n")

        if method == "status":
            return {"pid": os.getpid(), "generation": GENERATION, "fixture": True}
        if method == "list_documents":
            return [copy.deepcopy(self.documents[n]) for n in sorted(self.documents)]
        if method == "new_document":
            name = params["name"]
            if name in self.documents:
                raise CadError("Document already exists")
            self.documents[name] = {"name": name, "revision": "0", "objects": []}
            self.history[name] = []
            self.effect(method)
            return copy.deepcopy(self.documents[name])
        name = params.get("document")
        if name not in self.documents:
            raise CadError("Explicit fixture document does not exist")
        doc = self.documents[name]
        if method == "inspect_document":
            return copy.deepcopy(doc)
        if method == "capture_view":
            self.effect(method)
            return {"data": PNG, "mime_type": "image/png", "path": "fixture.png"}
        expected = params.get("expected_revision")
        if expected is not None and expected != doc["revision"]:
            raise CadError("Document revision changed")
        if method == "apply_operations":
            self.history[name].append(copy.deepcopy(doc))
            for operation in params["operations"]:
                if operation["op"] != "create_box":
                    raise CadError("Disposable fixture supports only create_box")
                doc["objects"].append(
                    {
                        "name": operation["name"],
                        "dimensions": {
                            key: operation[key] for key in ("length", "width", "height")
                        },
                    }
                )
            self.revision += 1
            doc["revision"] = str(self.revision)
            self.effect(method)
            if name == "LostReply":
                os._exit(9)  # Independent durable effect; no reply and no automatic retry.
            return {"results": [], "document": copy.deepcopy(doc), "warnings": []}
        if method == "undo_document":
            previous = self.history[name].pop()
            self.revision += 1
            previous["revision"] = str(self.revision)
            self.documents[name] = previous
            self.effect(method)
            return copy.deepcopy(previous)
        raise CadError("Unsupported disposable provider call")
