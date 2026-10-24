"""Publication integrity checks; synthetic bytes, no native executable or host config."""

import hashlib
from pathlib import Path

import pytest

from codex_freecad import stable_install as install
from codex_freecad.stable_launcher import PINS, selection, sha256


def candidate(root, version):
    for name in ("cwd", "launcher/snapshots", "launcher/backups"):
        (root / name).mkdir(parents=True, exist_ok=True)
    entry = root / "runtimes" / version / "entry.py"
    payload = entry.parent / "runtime"
    payload.mkdir(parents=True)
    (payload / "fixture.py").write_bytes(b"# Never executed\n")
    entry.write_bytes(b"raise RuntimeError('Unit fixture must never execute')\n")
    closure = entry.parent / "closure.json"
    closure.write_bytes(
        install.encoded({"runtime": str(payload), "files": install.inventory(payload)})
    )
    (root / "Start-Mcp.py").write_bytes(
        Path(install.__file__).with_name("stable_launcher.py").read_bytes()
    )
    manifest = {
        "schema_version": 1,
        "application_id": "freecad-mcp-server",
        "package_version": version,
        "profile": "direct-standalone-offline",
        "pins": PINS,
        "entry": entry.relative_to(root).as_posix(),
        "runtime": payload.relative_to(root).as_posix(),
        "args": [],
        "files": {p.relative_to(root).as_posix(): sha256(p) for p in (entry, closure)},
        "stable_entry_sha256": sha256(root / "Start-Mcp.py"),
    }
    raw = install.encoded(manifest)
    snapshot = hashlib.sha256(raw).hexdigest()
    folder = root / "launcher/snapshots" / snapshot
    folder.mkdir()
    (folder / "manifest.json").write_bytes(raw)
    return snapshot, manifest


def test_atomic_update_keeps_prior_selection_and_retained_payloads(tmp_path):
    root = tmp_path / "Installed CAD Ω with spaces"
    first, old = candidate(root, "26.1023.1")
    install.select(root, first, expected_selection="absent")
    previous = (root / "launcher/current.json").read_bytes()
    expected = hashlib.sha256(previous).hexdigest()
    second, new = candidate(root, "26.1023.2")
    assert selection(root)["snapshot"] == first  # Preparation alone never selects.
    install.select(root, second, expected_selection=expected)
    assert selection(root)["snapshot"] == second
    assert (root / "launcher/backups" / (expected + ".json")).read_bytes() == previous
    assert (root / old["entry"]).exists() and (root / new["entry"]).exists()
    with pytest.raises(ValueError, match="concurrently"):
        install.select(root, first, expected_selection=expected)
    assert selection(root)["snapshot"] == second


@pytest.mark.parametrize("part", ["entry", "runtime", "snapshot"])
def test_tampered_candidate_refuses_before_replacing_valid_selection(tmp_path, part):
    first, _ = candidate(tmp_path, "26.1023.1")
    install.select(tmp_path, first, expected_selection="absent")
    previous = (tmp_path / "launcher/current.json").read_bytes()
    second, manifest = candidate(tmp_path, "26.1023.2")
    path = (
        tmp_path / manifest["entry"]
        if part == "entry"
        else tmp_path / manifest["runtime"] / "fixture.py"
        if part == "runtime"
        else tmp_path / "launcher/snapshots" / second / "manifest.json"
    )
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        install.select(tmp_path, second, expected_selection=hashlib.sha256(previous).hexdigest())
    assert (tmp_path / "launcher/current.json").read_bytes() == previous
    assert selection(tmp_path)["snapshot"] == first


def test_interrupted_publication_retains_exact_old_pointer(tmp_path, monkeypatch):
    first, _ = candidate(tmp_path, "26.1023.1")
    install.select(tmp_path, first, expected_selection="absent")
    previous = (tmp_path / "launcher/current.json").read_bytes()
    second, _ = candidate(tmp_path, "26.1023.2")

    def refuse(*args):
        raise OSError("Synthetic interrupted replacement")

    monkeypatch.setattr(install.os, "replace", refuse)
    with pytest.raises(OSError, match="interrupted"):
        install.select(tmp_path, second, expected_selection=hashlib.sha256(previous).hexdigest())
    assert (tmp_path / "launcher/current.json").read_bytes() == previous
    assert selection(tmp_path)["snapshot"] == first


@pytest.mark.parametrize(
    "pointer", [b"{}", b'{"schema_version":true,"snapshot":"x"}', b"invalid json"]
)
def test_malformed_or_missing_selection_never_chooses_another_directory(tmp_path, pointer):
    candidate(tmp_path, "26.1023.1")
    with pytest.raises(FileNotFoundError):
        selection(tmp_path)
    (tmp_path / "launcher/current.json").write_bytes(pointer)
    with pytest.raises((ValueError, KeyError, TypeError)):
        selection(tmp_path)


def test_extra_bytecode_or_payload_files_refuse_selection(tmp_path):
    snapshot, manifest = candidate(tmp_path, "26.1023.1")
    (tmp_path / manifest["runtime"] / "unexpected.pyc").write_bytes(b"unreviewed")
    with pytest.raises(ValueError, match="bytecode"):
        install.select(tmp_path, snapshot, expected_selection="absent")
    assert not (tmp_path / "launcher/current.json").exists()


def test_windows_dll_path_limit_is_checked_before_publication(tmp_path):
    install.require_windows_dll_paths(tmp_path, ["package/native.pyd"])
    deep = tmp_path / ("x" * 200)
    with pytest.raises(ValueError, match="shorter installation root"):
        install.require_windows_dll_paths(deep, ["package/native.pyd"])
