"""Windowless base interpreter and inherited UTF-8 pipe contract; stdlib only."""

import ctypes
import io
import os
import struct
import sys
from pathlib import Path


def pe_identity(path):
    with Path(path).open("rb") as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError("Offline interpreter requires a Windows PE image")
        offset = struct.unpack_from("<I", dos, 60)[0]
        if not 64 <= offset <= 1024 * 1024:
            raise ValueError("Invalid PE header offset")
        stream.seek(offset)
        header = stream.read(24)
        if len(header) != 24 or header[:4] != b"PE\0\0":
            raise ValueError("Invalid PE image signature")
        size = struct.unpack_from("<H", header, 20)[0]
        if not 70 <= size <= 4096:
            raise ValueError("Invalid PE optional header size")
        optional = stream.read(size)
        if len(optional) != size or struct.unpack_from("<H", optional)[0] not in {0x10B, 0x20B}:
            raise ValueError("Unsupported PE optional header")
        return {
            "machine": struct.unpack_from("<H", header, 4)[0],
            "subsystem": struct.unpack_from("<H", optional, 68)[0],
        }


def windowless_interpreter(python=None, *, base=None):
    if os.name != "nt":
        raise OSError("The offline profile requires Windows and its paired windowless interpreter")
    base = Path(base or sys._base_executable).resolve(strict=True)
    if base.name.lower() not in {"python.exe", "pythonw.exe"}:
        raise ValueError("Use a real base Python installation, without launcher wrappers")
    expected = base.with_name("pythonw.exe").resolve(strict=True)
    selected = Path(python).resolve(strict=True) if python is not None else expected
    if selected != expected:
        raise ValueError(
            "Use the paired real pythonw.exe; console/redirector overrides are refused"
        )
    identity = pe_identity(selected)
    if identity["subsystem"] != 2 or identity["machine"] != pe_identity(base)["machine"]:
        raise ValueError("The paired interpreter must be a matching Windows GUI PE image")
    return selected


def require_windowless_root():
    if Path(sys.executable).resolve() != windowless_interpreter():
        raise ValueError("Serve the offline profile with the generated windowless connection")


def inherited_stdio():
    """Use inherited pipes, including GUI-Python startup with missing sys streams.

    No console is allocated/attached. Rebuilt wrappers retain CRT fd 0/1/2 so the
    SDK can claim/divert them normally; the early guard duplicates the same wire.
    """
    if os.name != "nt":
        raise OSError("Inherited offline pipe setup currently requires Windows")
    import msvcrt
    from ctypes import wintypes as w

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetStdHandle.argtypes, api.GetStdHandle.restype = [w.DWORD], w.HANDLE
    api.GetFileType.argtypes, api.GetFileType.restype = [w.HANDLE], w.DWORD
    api.GetCurrentProcess.restype = w.HANDLE
    api.DuplicateHandle.argtypes = [
        w.HANDLE,
        w.HANDLE,
        w.HANDLE,
        ctypes.POINTER(w.HANDLE),
        w.DWORD,
        w.BOOL,
        w.DWORD,
    ]
    api.DuplicateHandle.restype = w.BOOL
    api.SetStdHandle.argtypes, api.SetStdHandle.restype = [w.DWORD, w.HANDLE], w.BOOL
    api.CloseHandle.argtypes = [w.HANDLE]
    result = {}
    for name, fd, identifier, reading in (
        ("stdin", 0, -10, True),
        ("stdout", 1, -11, False),
        ("stderr", 2, -12, False),
    ):
        slot = w.DWORD(identifier).value
        wire = api.GetStdHandle(slot)
        if (
            not wire
            or wire == ctypes.c_void_p(-1).value
            or api.GetFileType(wire) not in ({3} if fd < 2 else {1, 3})
        ):
            raise OSError(
                "Offline stdin/stdout require inherited pipes and stderr requires a retained sink"
            )
        stream = getattr(sys, name)
        rebuilt = stream is None
        if rebuilt:
            duplicate = w.HANDLE()
            owner = api.GetCurrentProcess()
            if not api.DuplicateHandle(owner, wire, owner, ctypes.byref(duplicate), 0, False, 2):
                raise ctypes.WinError(ctypes.get_last_error())
            descriptor = None
            try:
                descriptor = msvcrt.open_osfhandle(
                    duplicate.value, os.O_BINARY | (os.O_RDONLY if reading else os.O_WRONLY)
                )
                duplicate = w.HANDLE()  # The CRT descriptor now owns this duplicate.
                if descriptor != fd:
                    os.dup2(descriptor, fd, inheritable=False)
                stream = io.TextIOWrapper(
                    io.FileIO(fd, "rb" if reading else "wb", closefd=False),
                    encoding="utf-8",
                    errors="strict",
                    newline="\n",
                    line_buffering=not reading,
                )
                setattr(sys, name, stream)
            finally:
                if descriptor is not None and descriptor != fd:
                    os.close(descriptor)
                if duplicate.value:
                    api.CloseHandle(duplicate)
        if (
            not hasattr(stream, "reconfigure")
            or not hasattr(stream, "buffer")
            or stream.buffer.fileno() != fd
        ):
            raise OSError("Offline streams must retain the inherited CRT descriptors")
        stream.reconfigure(
            encoding="utf-8", errors="strict", newline="\n", line_buffering=not reading
        )
        if not api.SetStdHandle(slot, msvcrt.get_osfhandle(fd)):
            raise ctypes.WinError(ctypes.get_last_error())
        result[name] = {
            "rebuilt": rebuilt,
            "encoding": stream.encoding,
            "fd": fd,
            "file_type": api.GetFileType(api.GetStdHandle(slot)),
        }
    return result
