"""Bounded FCStd ZIP metadata inspection. Never load native objects or execute code."""

import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_XML = 8 * 1024 * 1024
MAX_MEMBERS = 4096


def _file_key(value):
    # Windows stat/fstat disagree on legacy ctime for freshly closed ZIP files.
    # Compare stable file identity, size and last-write time, not access/ctime.
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def inspect_fcstd(workspace, path, expected_sha256=None):
    root = Path(workspace).resolve(strict=True)
    selected = (root / path).resolve(strict=True)
    if not selected.is_relative_to(root) or selected.suffix.lower() != ".fcstd":
        raise ValueError("Select an FCStd file inside the configured offline workspace")
    before = selected.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_ARCHIVE:
        raise ValueError("FCStd input must be a regular file of at most 64 MiB")
    with selected.open("rb") as stream:
        if _file_key(os.fstat(stream.fileno())) != _file_key(before):
            raise ValueError("Source identity changed before snapshot capture")
        raw = stream.read(MAX_ARCHIVE + 1)
    after = selected.stat()
    if (
        _file_key(before) != _file_key(after)
        or len(raw) != before.st_size
        or len(raw) > MAX_ARCHIVE
    ):
        raise ValueError("Source changed during snapshot capture; inspect a stable copy")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise ValueError("FCStd source hash differs from the inspected revision")
    entries, xml = [], None
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_EXPANDED:
            raise ValueError("FCStd member count or expanded byte budget exceeded")
        seen = set()
        for member in members:
            name = member.orig_filename
            parts = PurePosixPath(name)
            if (
                not name
                or name != member.filename
                or "\\" in name
                or ":" in name
                or parts.is_absolute()
                or ".." in parts.parts
                or parts.as_posix() != name.rstrip("/")
                or name.casefold() in seen
                or member.flag_bits & 1
                or stat.S_ISLNK(member.external_attr >> 16)
                or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise ValueError("Ambiguous or unsupported FCStd ZIP member")
            seen.add(name.casefold())
            if member.filename == "Document.xml" and member.file_size > MAX_XML:
                raise ValueError("Document.xml exceeds its 8 MiB budget")
            hashed, size = hashlib.sha256(), 0
            content = bytearray() if member.filename == "Document.xml" else None
            with bundle.open(member) as payload:
                while chunk := payload.read(64 * 1024):
                    size += len(chunk)
                    if size > member.file_size:
                        raise ValueError("ZIP payload exceeds its declared size")
                    hashed.update(chunk)
                    if content is not None:
                        content.extend(chunk)
            if size != member.file_size:
                raise ValueError("Truncated FCStd ZIP member")
            entries.append({"name": name, "bytes": size, "sha256": hashed.hexdigest()})
            if content is not None:
                xml = bytes(content)
    if xml is None:
        raise ValueError("FCStd package requires one root Document.xml")
    # Require UTF-8 text and reject declarations before XML parsing. Saved Python
    # proxies/expressions are data; neither modules nor native documents are opened.
    text = xml.decode("utf-8-sig")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("XML document/entity declarations are unavailable offline")
    tree = ElementTree.fromstring(text)
    if tree.tag != "Document":
        raise ValueError("Expected an FCStd Document XML root")
    objects = [
        {"name": item.get("name", ""), "type": item.get("type", "")}
        for item in tree.findall("./Objects/Object")
    ]
    if len(objects) > 10000 or any(len(v) > 256 for obj in objects for v in obj.values()):
        raise ValueError("FCStd object inventory exceeds its metadata budget")
    return {
        "scope": "offline ZIP/XML metadata; geometry/recompute/native acceptance unassessed",
        "path": selected.relative_to(root).as_posix(),
        "sha256": digest,
        "bytes": len(raw),
        "crc_verified": True,
        "objects": objects,
        "members": entries,
        "native_execution": False,
        "source_written": False,
    }


def bundled_capabilities():
    from .extension_runtime import Registry

    # Never accept external roots, evaluate a handler or use environment paths.
    sources = Registry(load=False).scan()
    capabilities = [
        {
            "id": extension + "." + name,
            "kind": item["kind"],
            "description": item["description"],
            "parameters": item["parameters"],
            "source_sha256": source["sha256"],
            "native_execution": False,
        }
        for extension, source in sources.items()
        for name, item in source["manifest"]["capabilities"].items()
    ]
    if len(json.dumps(capabilities).encode()) > 512 * 1024:
        raise ValueError("Bundled capability metadata exceeds its budget")
    return {
        "scope": "bundled schema reference only; no capability invocation",
        "capabilities": capabilities,
    }
