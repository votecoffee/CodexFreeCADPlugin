"""Bounded real stdio fixture; retains its own original Popen handle only."""

import json
import os
import queue
import subprocess
import threading
import time


def private_memory(peer):
    """Actual commit on the original fixture process handle, never a reopened PID."""
    import ctypes
    from ctypes import wintypes as w

    class Memory(ctypes.Structure):
        _fields_ = [
            ("size", w.DWORD),
            ("faults", w.DWORD),
            *[
                (name, ctypes.c_size_t)
                for name in (
                    "peak_working",
                    "working",
                    "peak_paged",
                    "paged",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                    "private",
                )
            ],
        ]

    assert not original_exit(peer.driver, int(peer.process._handle))["signaled"]
    api = ctypes.WinDLL("psapi", use_last_error=True)
    api.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(Memory), w.DWORD]
    api.GetProcessMemoryInfo.restype = w.BOOL
    memory = Memory()
    memory.size = ctypes.sizeof(memory)
    if not api.GetProcessMemoryInfo(int(peer.process._handle), ctypes.byref(memory), memory.size):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "identity": peer.identity,
        "private_bytes": memory.private,
        "working_bytes": memory.working,
        "peak_private_bytes": memory.peak_pagefile,
    }


def original_exit(driver, handle):
    import ctypes
    from ctypes import wintypes as w

    status = driver.kernel.WaitForSingleObject(handle, 0)
    if status == 0x102:
        return {"signaled": False}
    if status != 0:
        raise ctypes.WinError(ctypes.get_last_error())
    api = driver.kernel.GetExitCodeProcess
    api.argtypes, api.restype = [w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL
    code = w.DWORD()
    if not api(handle, ctypes.byref(code)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"signaled": True, "exit_code": code.value, "observed_at": time.time()}


def retained_writer(stream):
    import ctypes
    import msvcrt
    from ctypes import wintypes as w

    handle = msvcrt.get_osfhandle(stream.fileno())
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetFileType.argtypes, api.GetFileType.restype = [w.HANDLE], w.DWORD
    api.GetHandleInformation.argtypes, api.GetHandleInformation.restype = (
        [w.HANDLE, ctypes.POINTER(w.DWORD)],
        w.BOOL,
    )
    flags = w.DWORD()
    if api.GetFileType(handle) != 3 or not api.GetHandleInformation(handle, ctypes.byref(flags)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"original_writer_valid": True, "file_type": "pipe", "observed_at": time.time()}


class Wire:
    def __init__(self, route, *, command=None):
        from codex_freecad.windows_identity import AppProcessDriver

        self.driver = AppProcessDriver()
        self.started_at = time.monotonic()
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
        try:
            self.process.stdin.write((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))
            self.process.stdin.flush()
        except OSError as exc:
            if self.process.poll() is not None:
                self.readers[1].join(timeout=2)
            raise RuntimeError("Fixture wire write failed: " + "".join(self.errors)) from exc

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
        self.initialize_elapsed = time.monotonic() - self.started_at
        return result

    def tool(self, tool_name, **arguments):
        result = self.call("tools/call", {"name": tool_name, "arguments": arguments})
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
            "original_handle_exit": original_exit(self.driver, int(self.process._handle)),
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
