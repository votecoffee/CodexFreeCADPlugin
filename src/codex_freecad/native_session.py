"""Bounded native dispatch, inspected targets and durable non-replayable receipts."""

import hashlib
import json
import threading
import uuid
from pathlib import Path

from . import __package_version__
from .engine import CadError, Workspace

READS = frozenset(
    {
        "status",
        "list_documents",
        "inspect_document",
        "inspect_object",
        "inspect_assembly",
        "inspect_sketch",
        "inspect_topology",
        "measure_distance",
        "check_interference",
        "sample_motion",
        "get_selection",
        "capture_view",
        "list_capabilities",
        "describe_capability",
        "run_query",
    }
)
WRITES = frozenset(
    {
        "new_document",
        "open_document",
        "import_model",
        "apply_operations",
        "undo_document",
        "save_document",
        "export_model",
        "set_view",
        "reload_extensions",
    }
)
SUFFIXES = {".fcstd", ".step", ".stp", ".stl", ".brep"}


def digest(path):
    if not path.exists():
        return "absent"
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class NativeClient:
    def __init__(self, client, workspace, state, *, mode, binding_check=None):
        self.client, self.mode = client, mode
        self.workspace = Workspace(workspace)
        self.state = Path(state)
        self.lock = threading.Lock()
        self.closed = False
        self.uncertain = False
        self.validated = False
        self.binding_check = binding_check
        self.targets, self.revisions = {}, {}
        # Every connection has its own receipt generation; old uncertainty remains.
        self.generation = uuid.uuid4().hex
        self.journal = self.state / "native-receipts" / self.generation

    def review_target(self, path):
        if not self.lock.acquire(blocking=False):
            raise CadError("Native request capacity reached")
        try:
            if self.closed:
                raise CadError("Native session is closed")
            target = self.workspace.path(path, SUFFIXES)
            observed = digest(target)
            self.targets[str(target)] = observed
            return {"path": str(target), "sha256": observed, "native_opened": False}
        finally:
            self.lock.release()

    def _guards(self, method, params):
        if method in {"apply_operations", "import_model", "undo_document"}:
            if not params.get("expected_revision"):
                raise CadError("Inspect the document and pass expected_revision before editing")
        if method in {"open_document", "save_document", "export_model"}:
            target = self.workspace.path(params["path"], SUFFIXES)
            expected = self.targets.get(str(target))
            if expected is None or digest(target) != expected:
                raise CadError(
                    "Review this exact native target before opening, saving or exporting"
                )
            if method == "open_document":
                if expected == "absent":
                    raise CadError("FCStd source does not exist")
                params["expected_sha256"] = expected
            else:
                document = params["document"]
                revision = self.revisions.get(document)
                current = self.client.call("inspect_document", document=document)
                if not revision or revision != current["revision"]:
                    raise CadError("Inspect the current document before saving or exporting")
                params["expected_target_sha256"] = expected

    def call(self, method, **params):
        if method not in READS | WRITES:
            raise CadError("Unsupported native dispatch method")
        if not self.lock.acquire(blocking=False):
            raise CadError("Native request capacity reached; wait for the active request")
        receipt = None
        try:
            if self.closed or (self.uncertain and method in WRITES):
                raise CadError("Native session closed or uncertain; preserve receipts and inspect")
            if self.binding_check is not None:
                self.binding_check()
            if method in WRITES:
                for previous in (self.state / "native-receipts").glob("*/*.json"):
                    if json.loads(previous.read_bytes())["state"] in {"dispatched", "uncertain"}:
                        raise CadError(
                            "Unresolved native receipt; inspect original work without replay"
                        )
            if not self.validated:
                status = self.client.call("status")
                if (
                    status.get("plugin_package_version") != __package_version__
                    or status.get("mode") != self.mode
                ):
                    raise CadError("Native backend differs from this reviewed package/mode")
                self.validated = True
            self._guards(method, params)
            if method in WRITES:
                from universal_tools.resources import durable_json

                self.journal.mkdir(parents=True, exist_ok=True)
                if len(list((self.state / "native-receipts").glob("*/*.json"))) >= 256:
                    raise CadError("Native receipt history full; preserve it before a new session")
                raw = json.dumps(params, sort_keys=True, ensure_ascii=True).encode()
                receipt = {
                    "request_id": uuid.uuid4().hex,
                    "method": method,
                    "arguments_sha256": hashlib.sha256(raw).hexdigest(),
                    "state": "dispatched",
                    "replay_allowed": False,
                    "target": params.get("path"),
                    "expected_revision": params.get("expected_revision"),
                    "expected_target_sha256": params.get(
                        "expected_target_sha256", params.get("expected_sha256")
                    ),
                }
                path = self.journal / (receipt["request_id"] + ".json")
                durable_json(path, receipt)
            result = self.client.call(method, **params)
            inspected = result.get("document") if isinstance(result, dict) else None
            if isinstance(inspected, dict) and inspected.get("revision"):
                self.revisions[inspected["name"]] = inspected["revision"]
            if isinstance(result, dict) and result.get("revision"):
                document = result.get("name") or params.get("document")
                if document:
                    self.revisions[document] = result["revision"]
            if receipt is not None:
                receipt = {**receipt, "state": "reply-received"}
                durable_json(path, receipt)
                if method in {"save_document", "export_model"}:
                    target = self.workspace.path(params["path"], SUFFIXES)
                    self.targets[str(target)] = digest(target)
                if isinstance(result, dict):
                    result = {**result, "native_receipt": receipt}
            return result
        except BaseException:
            if receipt is not None:
                self.uncertain = True
                # Even a failed persistence after a native reply is uncertain.
                # A retained dispatched record also blocks inference of success.
                durable_json(path, {**receipt, "state": "uncertain"})
            raise
        finally:
            self.lock.release()

    def close(self):
        # SDK closes its lifespan after in-flight calls. Refuse a racing teardown
        # rather than acknowledge cancellation or drop a native operation.
        if not self.lock.acquire(blocking=False):
            raise CadError("Native operation still active; teardown is not acknowledged")
        try:
            if not self.closed:
                self.client.close()
                self.closed = True
        finally:
            self.lock.release()

    def resource_status(self):
        return {
            **self.client.resource_status(),
            "receipt_generation": self.generation,
            "uncertain": self.uncertain,
            "admission": "one active request; no waiting queue",
        }
