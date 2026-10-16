"""Authenticated loopback HTTP transport, dispatching all CAD work onto Qt's GUI thread."""

import hmac
import json
import os
import queue
import secrets
import threading
import time
from concurrent.futures import Future, TimeoutError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import Engine

_bridge = None
MAX_BODY = 1024 * 1024


class Bridge:
    def __init__(self, workspace, state_file, extension_dirs=None):
        from PySide import QtCore

        self.engine = Engine(workspace, gui=True, extension_dirs=extension_dirs)
        self.state_file = Path(state_file).resolve()
        self.token = secrets.token_urlsafe(32)
        self.jobs = queue.Queue(maxsize=64)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.server.daemon_threads = True
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.drain)
        self.timer.start(30)
        self.stopped = False

    def handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value):
                data = json.dumps(value, ensure_ascii=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self):
                self.connection.settimeout(5)
                if self.path != "/call":
                    return self.reply(404, {"error": "Unknown endpoint"})
                if self.headers.get("Origin") is not None:
                    return self.reply(403, {"error": "Browser origins are not allowed"})
                expected_host = "127.0.0.1:%d" % bridge.server.server_port
                if self.headers.get("Host") != expected_host:
                    return self.reply(403, {"error": "Invalid Host"})
                authorization = self.headers.get("Authorization", "")
                if not hmac.compare_digest(authorization, "Bearer " + bridge.token):
                    return self.reply(401, {"error": "Unauthorized"})
                if self.headers.get_content_type() != "application/json":
                    return self.reply(415, {"error": "Expected application/json"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= MAX_BODY:
                        return self.reply(413, {"error": "Request too large or empty"})
                    request = json.loads(self.rfile.read(size))
                    if (
                        not isinstance(request, dict)
                        or not isinstance(request.get("method"), str)
                        or not isinstance(request.get("params", {}), dict)
                    ):
                        raise ValueError("Expected method and params")
                except (ValueError, OSError) as exc:
                    return self.reply(400, {"error": str(exc)})
                future = Future()
                try:
                    bridge.jobs.put_nowait((time.monotonic() + 115, future, request))
                except queue.Full:
                    return self.reply(429, {"error": "FreeCAD request queue is full"})
                try:
                    result = future.result(timeout=120)
                    return self.reply(200, {"result": result})
                except TimeoutError:
                    cancelled = future.cancel()
                    message = (
                        "Request expired before execution"
                        if cancelled
                        else "Operation still running; inspect the model before retrying"
                    )
                    return self.reply(504, {"error": message})
                except Exception as exc:
                    return self.reply(422, {"error": str(exc)})

        return Handler

    def drain(self):
        # Exactly one operation per tick; requests and GUI edits are serialized by Qt.
        try:
            deadline, future, request = self.jobs.get_nowait()
        except queue.Empty:
            return
        if time.monotonic() > deadline:
            future.cancel()
        if not future.set_running_or_notify_cancel():
            return
        try:
            result = self.engine.call(request["method"], request.get("params", {}))
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)

    def start(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to replace an active bridge's state file.
        from .client import LiveClient

        if self.state_file.exists():
            try:
                LiveClient(self.state_file, timeout=1).call("status")
            except Exception:
                pass
            else:
                self.timer.stop()
                self.server.server_close()
                raise RuntimeError("A bridge already uses this state file")
        state = {
            "port": self.server.server_port,
            "token": self.token,
            "pid": os.getpid(),
            "workspace": str(self.engine.workspace.root),
        }
        temp = self.state_file.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as stream:
            os.chmod(temp, 0o600)
            json.dump(state, stream)
        os.replace(temp, self.state_file)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.timer.stop()
        self.server.shutdown()
        self.server.server_close()
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            if state.get("token") == self.token:
                self.state_file.unlink()
        except (OSError, ValueError):
            pass
        while not self.jobs.empty():
            _, future, _ = self.jobs.get_nowait()
            future.cancel()


def start(workspace, state_file, extension_dirs=None):
    global _bridge
    import FreeCAD
    import FreeCADGui

    if _bridge is not None:
        _bridge.stop()
    _bridge = Bridge(workspace, state_file, extension_dirs)
    _bridge.start()
    FreeCADGui.getMainWindow().destroyed.connect(_bridge.stop)
    FreeCAD.Console.PrintMessage(
        "Codex FreeCAD bridge started on loopback. Workspace: " + str(workspace) + "\n"
    )
    return _bridge


def stop():
    global _bridge
    if _bridge is not None:
        _bridge.stop()
        _bridge = None
