"""Bounded real stdio fixture; retains its own original Popen handle only."""

import json
import os
import queue
import subprocess
import threading
import time


class Wire:
    def __init__(self, route, *, command=None):
        from codex_freecad.windows_identity import AppProcessDriver

        self.driver = AppProcessDriver()
        self.process = subprocess.Popen(
            command or [route["command"], *route["args"]],
            cwd=route["cwd"],
            env={**os.environ, **route.get("env", {})},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.identity = self.driver.capture_handle(int(self.process._handle), self.process.pid)
        self.messages, self.responses, self.errors = [], queue.Queue(), []
        self.next_id = 0
        self.readers = [
            threading.Thread(target=self._stdout, daemon=True),
            threading.Thread(target=self._stderr, daemon=True),
        ]
        for reader in self.readers:
            reader.start()

    def _stdout(self):
        try:
            for raw in iter(self.process.stdout.readline, b""):
                message = json.loads(raw.decode("utf-8", "strict"))
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise ValueError("Non-protocol stdout")
                self.messages.append(message)
                self.responses.put(message)
        except BaseException as exc:
            self.responses.put(exc)
        finally:
            self.responses.put(None)

    def _stderr(self):
        for raw in iter(self.process.stderr.readline, b""):
            self.errors.append(raw.decode("utf-8", "strict"))

    def send(self, value):
        self.process.stdin.write((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def call(self, method, params=None):
        self.next_id += 1
        request = self.next_id
        self.send({"jsonrpc": "2.0", "id": request, "method": method, "params": params or {}})
        deadline = time.monotonic() + 20
        while True:
            message = self.responses.get(timeout=max(0.01, deadline - time.monotonic()))
            if message is None:
                raise RuntimeError("Fixture server ended: " + "".join(self.errors))
            if isinstance(message, BaseException):
                raise message
            if message.get("id") == request:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message["result"]

    def initialize(self):
        from mcp.types import LATEST_PROTOCOL_VERSION

        result = self.call(
            "initialize",
            {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "FreeCAD stable fixture Ω", "version": "1"},
            },
        )
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def tool(self, name, **arguments):
        result = self.call("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            return result
        body = result.get("structuredContent")
        if body is None:
            body = json.loads(
                next(item["text"] for item in result["content"] if item["type"] == "text")
            )
        return body.get("result", body) if isinstance(body, dict) else body

    def eof(self):
        started = time.monotonic()
        self.process.stdin.close()
        code = self.process.wait(timeout=15)
        for reader in self.readers:
            reader.join(timeout=2)
        assert all(not reader.is_alive() for reader in self.readers)
        return {
            "exit_code": code,
            "elapsed_seconds": time.monotonic() - started,
            "identity": self.identity,
            "identity_state": self.driver.state(self.identity),
            "stdout_messages": len(self.messages),
            "stderr": "".join(self.errors),
        }

    def close(self):
        if self.process.poll() is None:
            try:
                self.eof()
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()  # Exact retained private fixture handle, never a PID sweep.
                self.process.wait(timeout=5)
        for reader in self.readers:
            reader.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass  # A refused child may have closed its original pipe already.

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
