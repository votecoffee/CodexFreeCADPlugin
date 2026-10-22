"""PE and refusal contracts; no interpreter or engineering service is started."""

import struct
import sys
from pathlib import Path

import pytest

from codex_freecad.offline_interpreter import (
    pe_identity,
    require_windowless_root,
    windowless_interpreter,
)


def binary(path, *, subsystem=2, machine=0x8664):
    raw = bytearray(64 + 24 + 112)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 60, 64)
    raw[64:68] = b"PE\0\0"
    struct.pack_into("<H", raw, 68, machine)
    struct.pack_into("<H", raw, 84, 112)
    struct.pack_into("<H", raw, 88, 0x20B)
    struct.pack_into("<H", raw, 88 + 68, subsystem)
    path.write_bytes(raw)
    return path


def test_selects_only_matching_paired_gui_image(tmp_path):
    base = binary(tmp_path / "python.exe", subsystem=3)
    windowless = binary(tmp_path / "pythonw.exe")
    assert windowless_interpreter(base=base) == windowless
    assert pe_identity(windowless) == {"machine": 0x8664, "subsystem": 2}
    with pytest.raises(ValueError, match="console/redirector"):
        windowless_interpreter(base, base=base)
    binary(windowless, subsystem=3)
    with pytest.raises(ValueError, match="GUI PE"):
        windowless_interpreter(base=base)
    binary(windowless, machine=0xAA64)
    with pytest.raises(ValueError, match="matching"):
        windowless_interpreter(base=base)


@pytest.mark.parametrize("content", [b"", b"MZ", b"MZ" + b"\0" * 100])
def test_invalid_image_headers_are_refused(tmp_path, content):
    path = tmp_path / "invalid.exe"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        pe_identity(path)


def test_console_or_venv_server_root_is_refused():
    if Path(sys.executable).resolve() != windowless_interpreter():
        with pytest.raises(ValueError, match="generated windowless"):
            require_windowless_root()


def test_actual_base_pair_has_matching_gui_pe_without_execution():
    selected = windowless_interpreter()
    assert selected.name.lower() == "pythonw.exe"
    assert pe_identity(selected)["subsystem"] == 2
    assert pe_identity(selected)["machine"] == pe_identity(sys._base_executable)["machine"]
