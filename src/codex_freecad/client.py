"""Local application API and transports; no OpenAI account is needed to use these."""

import atexit
import json
import os
import queue
import shutil
import subprocess
import threading
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
    def __init__(self, workspace, freecad_cmd=None, timeout=120, extension_dirs=None):
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.freecad_cmd = freecad_cmd
        self.timeout = timeout
        self.extension_dirs = extension_dirs
        self.process = None
        self.lock = threading.Lock()
        self.responses = queue.Queue()
        self.diagnostics = []
        self.failed = False
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
        self.process = subprocess.Popen(
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
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for stream, replies in ((self.process.stdout, True), (self.process.stderr, False)):
            threading.Thread(
                target=self._read, args=(stream, replies, self.responses), daemon=True
            ).start()
        try:
            if not self._receive().get("ready"):
                raise CadError("Unexpected FreeCAD startup response")
        except Exception:
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
                raise CadError("FreeCAD worker is unavailable") from None
            response = self._receive()
            if response.get("id") != request_id:
                self.failed = True
                self.close()
                raise CadError("FreeCAD response did not match the request; restart the MCP server")
            return response["result"]

    def close(self):
        process = self.process
        if process is not None:
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
            self.process = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class LiveClient:
    def __init__(self, state_file, timeout=120):
        self.state_file = Path(state_file).expanduser().resolve()
        self.timeout = timeout
        # Never send the local bearer token through environment HTTP proxies.
        self.opener = build_opener(ProxyHandler({}))

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
            raise CadError(
                "Live bridge unavailable or timed out. Inspect the model before retrying a write."
            ) from None
        if "error" in payload:
            raise CadError(payload["error"])
        return payload["result"]

    def close(self):
        pass
