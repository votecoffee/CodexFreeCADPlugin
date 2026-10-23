"""Encode generated TOML once, with explicit line endings and no text-mode translation."""

import os
import re
import tomllib

BOM = b"\xef\xbb\xbf"


def encode_toml(
    text: str, *, newline: str | None = None, source_bytes: bytes | None = None
) -> bytes:
    """Return validated UTF-8 bytes; reject malformed CR instead of silently repairing it.

    Callers choose the target file. This module does not read or update a user's
    configuration. LF and CRLF input are supported, including mixed valid endings.
    Windows output defaults to explicit CRLF; other platforms default to LF.
    For a publication based on an existing file, pass its original bytes so an
    earlier utf-8-sig decode cannot silently discard its BOM.
    """
    if newline is None:
        newline = "\r\n" if os.name == "nt" else "\n"
    if newline not in {"\n", "\r\n"}:
        raise ValueError("Choose LF or CRLF for TOML output")

    def validate(value):
        if re.search(r"\r(?!\n)", value):
            raise ValueError("Malformed TOML line ending: carriage return without newline")
        value = value.removeprefix("\ufeff").replace("\r\n", "\n")
        tomllib.loads(value)
        return value

    preserve_bom = text.startswith("\ufeff")
    if source_bytes is not None:
        validate(source_bytes.decode("utf-8-sig"))
        preserve_bom = preserve_bom or source_bytes.startswith(BOM)
    normalized = validate(text)
    return (BOM if preserve_bom else b"") + normalized.replace("\n", newline).encode("utf-8")
