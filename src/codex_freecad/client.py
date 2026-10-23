"""Local application API and transports; no OpenAI account is needed to use these."""

import atexit
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .engine import CadError

PREFIX = "@@CODEX_FREECAD@@"


def find_freecad_cmd(explicit=None):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise CadError("FreeCADCmd executable does not exist: " + str(path))
        return str(path)
    configured = os.environ.get("FREECAD_CMD")
    if configured:
        return find_freecad_cmd(configured)
    for name in ("FreeCADCmd", "freecadcmd", "FreeCADCmd.exe"):
        found = shutil.which(name)
        if found:
            return found
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    for folder in sorted(program_files.glob("FreeCAD*"), reverse=True):
        candidate = folder / "bin" / "FreeCADCmd.exe"
        if candidate.is_file():
            return str(candidate)
    raise CadError("FreeCADCmd not found. Set FREECAD_CMD or pass --freecad-cmd")


class HeadlessClient:
    def __init__(
        self,
        workspace,
        freecad_cmd=None,
        timeout=120,
        extension_dirs=None,
        resource_registry=None,
        executable_sha256=None,
    ):
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.freecad_cmd = freecad_cmd
        self.executable_sha256 = executable_sha256
        self.timeout = timeout
        self.extension_dirs = extension_dirs
        self.process = None
        self.lock = threading.Lock()
        self.responses = queue.Queue()
        self.diagnostics = []
        self.failed = False
        self.readers = []
        self.last_resource = None
        self.resource_registry = resource_registry
        self.resource_owner = None
        self.owns_resource_owner = False
        atexit.register(self.close)

    def _read(self, stream, replies, response_queue):
        for line in iter(stream.readline, ""):
            if replies and PREFIX in line:
                try:
                    response_queue.put(json.loads(line.split(PREFIX, 1)[1]))
                    continue
                except ValueError:
                    pass
            self.diagnostics.append(line.rstrip()[-1000:])
            self.diagnostics[:] = self.diagnostics[-30:]
        if replies:
            response_queue.put({"error": {"message": "FreeCAD worker exited"}})

    def _receive(self):
        try:
            response = self.responses.get(timeout=self.timeout)
        except queue.Empty:
            self.failed = True
            self.close()
            raise CadError(
                "FreeCAD timed out. Outcome is unknown; this session is disabled. Restart the MCP server."
            ) from None
        if "error" in response:
            raise CadError(response["error"]["message"])
        return response

    def _start(self):
        if self.failed:
            raise CadError("Worker session is disabled after a timeout; restart the MCP server")
        if self.process is not None:
            if self.process.poll() is not None:
                raise CadError("FreeCAD worker exited; restart the MCP server")
            return
        executable = find_freecad_cmd(self.freecad_cmd)
        if self.executable_sha256 is not None:
            import hashlib

            with Path(executable).open("rb") as stream:
                observed = hashlib.file_digest(stream, "sha256").hexdigest()
            if observed != self.executable_sha256:
                raise CadError("FreeCADCmd executable changed; review the native binding again")
        # A failed initial startup may be retried after its extension is repaired.
        # Retired reader threads must never publish their EOF into the new worker's queue.
        self.responses = queue.Queue()
        runtime = self.workspace / ".runtime" / uuid.uuid4().hex
        runtime.mkdir(parents=True)
        env = dict(
            os.environ, CODEX_FREECAD_WORKSPACE=str(self.workspace), PYTHONIOENCODING="utf-8"
        )
        if self.extension_dirs is not None:
            env["CODEX_FREECAD_EXTENSION_PATHS"] = json.dumps(
                [str(Path(p).expanduser().resolve()) for p in self.extension_dirs]
            )
        from .owned_process import spawn_owned
        from .resource_ownership import api_owner

        if self.resource_owner is None:
            self.resource_owner, self.owns_resource_owner = api_owner(self.resource_registry)

        self.process = spawn_owned(
            [
                executable,
                "-u",
                str(runtime / "user.cfg"),
                "-s",
                str(runtime / "system.cfg"),
                str(Path(__file__).with_name("worker.py")),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(self.workspace),
            env=env,
            resource_owner=self.resource_owner,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            for stream, replies in ((self.process.stdout, True), (self.process.stderr, False)):
                reader = threading.Thread(
                    target=self._read, args=(stream, replies, self.responses), daemon=True
                )
                self.readers.append((reader, stream))
                reader.start()
            if not self._receive().get("ready"):
                raise CadError("Unexpected FreeCAD startup response")
        except BaseException:
            self.close()
            raise

    def call(self, method, **params):
        with self.lock:
            self._start()
            request_id = uuid.uuid4().hex
            try:
                self.process.stdin.write(
                    json.dumps({"id": request_id, "method": method, "params": params}) + "\n"
                )
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.failed = True
                raise CadError(
                    "FreeCAD worker reply is unknown; inspect before another write"
                ) from None
            response = self._receive()
            if response.get("id") != request_id:
                self.failed = True
                self.close()
                raise CadError("FreeCAD response did not match the request; restart the MCP server")
            return response["result"]

    def close(self):
        process = self.process
        if process is not None:
            try:
                if process.poll() is None:
                    try:
                        process.stdin.write('{"method":"shutdown"}\n')
                        process.stdin.flush()
                        process.stdin.close()
                        process.wait(timeout=3)
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
            finally:
                process.close_owned_tree()
                deadline = time.monotonic() + 2
                for reader, _ in self.readers:
                    if getattr(reader, "ident", "stub") is None:
                        continue
                    reader.join(timeout=max(0, deadline - time.monotonic()))
                alive = {stream for reader, stream in self.readers if reader.is_alive()}
                self.last_resource = {
                    **process.identity,
                    "reader_cleanup": "pending" if alive else "closed",
                }
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream in alive:
                        continue  # TextIO.close can block behind a stuck readline lock.
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
                if alive:
                    self.failed = True  # Retain handles/evidence; never spawn another worker here.
                else:
                    self.process, self.readers = None, []
        if self.owns_resource_owner:
            self.resource_owner.close()

    def resource_status(self):
        result = (
            dict(self.process.identity)
            if self.process is not None
            else self.last_resource
            or {
                "ownership": "exclusive-launched",
                "state": "not-running",
                "native_dirty_state": "not-inspected",
            }
        )
        if self.process is not None and self.last_resource is not None:
            if self.last_resource.get("resource_id") == result.get("resource_id"):
                result.update(reader_cleanup=self.last_resource.get("reader_cleanup"))
        return {**result, "session_disabled": self.failed}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class LiveClient:
    def __init__(self, state_file, timeout=120, resource_registry=None, *, managed=True):
        self.state_file = Path(state_file).expanduser().resolve()
        self.timeout = timeout
        # Never send the local bearer token through environment HTTP proxies.
        self.opener = build_opener(ProxyHandler({}))
        self.attachment = None
        self.managed = managed
        self.resource_registry = resource_registry
        self.resource_owner = None
        self.owns_resource_owner = False

    def call(self, method, **params):
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise CadError(
                "Live bridge is not running. Run the generated StartBridge.FCMacro in FreeCAD."
            ) from None
        port = state["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise CadError("Invalid live bridge state")
        if self.managed:
            from .resource_ownership import Attachment, api_owner

            pid = state.get("pid")
            if type(pid) is not int or pid <= 0:
                raise CadError(
                    "Live bridge process identity is missing; inspect its intended bridge"
                )
            if self.attachment is None:
                if self.resource_owner is None:
                    self.resource_owner, self.owns_resource_owner = api_owner(
                        self.resource_registry
                    )
                self.attachment = Attachment(pid, self.resource_owner)
            self.attachment.verify(pid)
        body = json.dumps({"method": method, "params": params}).encode("utf-8")
        request = Request(
            "http://127.0.0.1:%d/call" % port,
            data=body,
            headers={
                "Authorization": "Bearer " + state["token"],
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout + 5) as response:
                payload = json.load(response)
        except HTTPError as exc:
            try:
                message = json.load(exc).get("error", "Bridge request failed")
            except ValueError:
                message = "Bridge HTTP error: " + str(exc.code)
            raise CadError(str(message)) from None
        except (URLError, TimeoutError, OSError):
            if self.attachment is not None:
                self.attachment.uncertain()
            raise CadError(
                "Live bridge unavailable or timed out. Inspect the model before retrying a write."
            ) from None
        if "error" in payload:
            raise CadError(payload["error"])
        return payload["result"]

    def close(self):
        if self.attachment is not None:
            self.attachment.close()
            self.attachment = None
        if self.owns_resource_owner:
            self.resource_owner.close()

    def resource_status(self):
        return {
            "ownership": "attached-user-owned",
            "cleanup": "detach-only",
            "terminate_allowed": False,
            "native_dirty_state": "not-inspected",
            "ledger_resource_id": self.attachment.record.resource_id if self.attachment else None,
        }
