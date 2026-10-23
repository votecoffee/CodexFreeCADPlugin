"""Offline source/stub checks; no engineering MCP, manager or native service starts."""

import hashlib
import json
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from codex_freecad import __package_version__
from codex_freecad import offline_files as files
from codex_freecad.offline_session import Admission, run_offline
from codex_freecad.offline_setup import generate

XML = b'<Document><Objects><Object name="Box" type="Part::Box"/></Objects></Document>'


def package(path, xml=XML, extra=()):
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("Document.xml", xml)
        for name, raw in extra:
            bundle.writestr(name, raw)
    return path


def test_snapshot_metadata_crc_hash_and_source_preservation(tmp_path):
    path = package(tmp_path / "demo.FCStd", extra=[("Shape.brp", b"opaque geometry")])
    original = path.read_bytes()
    result = files.inspect_fcstd(tmp_path, "demo.FCStd")
    assert result["objects"] == [{"name": "Box", "type": "Part::Box"}]
    assert result["sha256"] == hashlib.sha256(original).hexdigest()
    assert (
        result["crc_verified"] and not result["native_execution"] and not result["source_written"]
    )
    assert files.inspect_fcstd(tmp_path, path.name, result["sha256"]) == result
    with pytest.raises(ValueError, match="source hash"):
        files.inspect_fcstd(tmp_path, path.name, "0" * 64)
    assert path.read_bytes() == original and len(list(tmp_path.iterdir())) == 1


def test_escape_and_other_file_types_are_refused(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    package(tmp_path / "outside.FCStd")
    (root / "input.py").write_text("raise AssertionError('never run')")
    for path in ("../outside.FCStd", "input.py"):
        with pytest.raises(ValueError, match="FCStd file inside"):
            files.inspect_fcstd(root, path)


@pytest.mark.parametrize(
    "name", ["../escape", "/root", "C:/file", "folder\\file", "./alias", "document.xml"]
)
def test_ambiguous_archive_members_are_refused(tmp_path, name):
    path = package(tmp_path / "bad.FCStd", extra=[(name, b"payload")])
    if "\\" in name:
        # zipfile normalizes backslashes when writing on Windows. Alter the
        # stored header names to exercise an actual noncanonical archive.
        path.write_bytes(path.read_bytes().replace(name.replace("\\", "/").encode(), name.encode()))
    with pytest.raises(ValueError, match="ZIP member"):
        files.inspect_fcstd(tmp_path, path.name)


@pytest.mark.parametrize(
    "xml", [b'<!DOCTYPE Document [<!ENTITY x "unsafe">]><Document/>', b"<Other/>"]
)
def test_unsupported_xml_is_data_and_is_refused(tmp_path, xml):
    path = package(tmp_path / "bad.FCStd", xml)
    with pytest.raises(ValueError):
        files.inspect_fcstd(tmp_path, path.name)


@pytest.mark.parametrize("limit", ["MAX_ARCHIVE", "MAX_EXPANDED", "MAX_XML", "MAX_MEMBERS"])
def test_read_budgets_fail_closed(tmp_path, monkeypatch, limit):
    path = package(tmp_path / "limited.FCStd")
    monkeypatch.setattr(files, limit, 0)
    with pytest.raises(ValueError):
        files.inspect_fcstd(tmp_path, path.name)


def test_corrupt_crc_is_rejected_without_native_open(tmp_path):
    path = package(tmp_path / "bad.FCStd")
    path.write_bytes(path.read_bytes().replace(b'name="Box"', b'name="Bad"'))
    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        files.inspect_fcstd(tmp_path, path.name)


def test_only_offline_tools_exist_and_environment_cannot_add_native_routes(tmp_path, monkeypatch):
    from codex_freecad import offline
    from codex_freecad.extension_runtime import Registry

    class StubServer:
        def __init__(self, *args, **kwargs):
            self.tools = {}

        def tool(self, **kwargs):
            def register(function):
                self.tools[function.__name__] = function
                return function

            return register

    monkeypatch.setattr(offline, "MCPServer", StubServer)
    monkeypatch.setattr(Registry, "prepare", lambda *_: pytest.fail("Extension code loaded"))
    for variable in (
        "FREECAD_CMD",
        "CODEX_FREECAD_EXTENSION_PATHS",
        "FREECAD_FRAMEWORK_PYTHON",
        "PYTHONPATH",
    ):
        monkeypatch.setenv(variable, str(tmp_path / "must-not-run"))
    server = offline.create_offline_server(tmp_path, Admission())
    assert set(server.tools) == set(offline.TOOLS)
    assert not server.tools["freecad_offline_status"]()["native_execution"]
    assert server.tools["list_bundled_capabilities"]()["capabilities"]
    assert (
        "read-only" in server.tools["get_offline_workflow"]()["text"].lower()
        or "inspects" in server.tools["get_offline_workflow"]()["text"]
    )


def test_active_read_admission_is_nonblocking_and_recovers_after_failure():
    admission = Admission()
    with admission.operation(), pytest.raises(RuntimeError, match="capacity"):
        with admission.operation():
            pytest.fail("Parallel read admitted")
    with pytest.raises(ValueError), admission.operation():
        raise ValueError("fixture read failure")
    with admission.operation():
        pass


def test_hard_exit_occurs_after_session_cleanup():
    events = []

    @contextmanager
    def session():
        events.append("registered")
        try:
            yield
        finally:
            events.append("unregistered")

    server = SimpleNamespace(run=lambda **_: events.append("stdio-returned"))
    run_offline(server, session(), exit_process=events.append)
    assert events == ["registered", "stdio-returned", "unregistered", 0]


@pytest.mark.parametrize("failed_start", [False, True])
def test_durable_root_identity_is_the_surviving_owner_without_registering_a_fake_child(
    tmp_path, monkeypatch, failed_start
):
    management = pytest.importorskip("universal_tools.management")
    from codex_freecad import process_lifetime, resource_ownership
    from codex_freecad.offline_session import offline_session

    identity = {
        "host_id": "f" * 64,
        "pid": 12345,
        "created": "1234",
        "executable": "C:/fixture/python.exe",
    }
    owner = SimpleNamespace(
        owner_id="a" * 32, identity=SimpleNamespace(model_dump=lambda **_: identity)
    )
    events = []

    @contextmanager
    def lifetime(**kwargs):
        assert kwargs == {"stdio": True, "limit": 1}
        events.append("contained")
        yield

    @contextmanager
    def ownership(registry, **kwargs):
        yield owner

    class Manager:
        def __init__(self, app, display, status, **kwargs):
            self.status = status

        def __enter__(self):
            assert not self.status().restart_allowed
            assert list((tmp_path / "state/sessions").glob("*.json"))
            if failed_start:
                raise RuntimeError("fixture management failure")

        def __exit__(self, *_):
            events.append("manager-closed")

    monkeypatch.setattr(process_lifetime, "_jobs", [])
    monkeypatch.setattr(process_lifetime, "process_lifetime", lifetime)
    monkeypatch.setattr(resource_ownership, "resource_session", ownership)
    monkeypatch.setattr(management, "ManagedService", Manager)
    monkeypatch.setattr(
        management, "private_directory", lambda p: p.mkdir(parents=True, exist_ok=True)
    )
    if failed_start:
        with pytest.raises(RuntimeError, match="management failure"):
            with offline_session(tmp_path / "state", tmp_path / "registry", Admission()):
                pytest.fail("Failed startup admitted protocol work")
    else:
        with offline_session(tmp_path / "state", tmp_path / "registry", Admission()) as record:
            assert record["owner"] == identity and record["child_processes"] == []
    record = json.loads(next((tmp_path / "state/sessions").glob("*.json")).read_bytes())
    assert record["state"] == ("failed" if failed_start else "closed")
    assert record["owner"] == identity and events[0] == "contained"


def test_offline_closure_refuses_unverified_bytecode(tmp_path):
    from codex_freecad.offline_setup import inventory

    (tmp_path / "unsafe.pyc").write_bytes(b"not-a-reviewed-wheel-file")
    with pytest.raises(ValueError, match="bytecode caches"):
        inventory(tmp_path)


def test_console_serving_is_refused_before_server_creation(tmp_path, monkeypatch):
    from codex_freecad import offline

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "offline",
            "--workspace",
            str(tmp_path),
            "--state",
            str(tmp_path / "state"),
            "--registry",
            str(tmp_path / "registry"),
        ],
    )
    monkeypatch.setattr(
        offline, "create_offline_server", lambda *_: pytest.fail("Console root admitted")
    )
    with pytest.raises(SystemExit) as refused:
        offline.main()
    assert refused.value.code == 2
    assert not (tmp_path / "state").exists() and not (tmp_path / "registry").exists()


def test_offline_root_refuses_a_different_state_or_preexisting_job(tmp_path, monkeypatch):
    from codex_freecad import offline_session, process_lifetime

    monkeypatch.setattr(offline_session, "_root_state", tmp_path)
    with offline_session.root_lifetime(tmp_path):
        pass
    with pytest.raises(RuntimeError, match="differs"):
        with offline_session.root_lifetime(tmp_path / "other"):
            pytest.fail("State gate bypassed")
    monkeypatch.setattr(offline_session, "_root_state", None)
    monkeypatch.setattr(process_lifetime, "_jobs", [123])
    with pytest.raises(RuntimeError, match="fresh root"):
        with offline_session.root_lifetime(tmp_path):
            pytest.fail("Weaker job accepted")


def test_generation_pins_real_interpreter_and_does_not_create_live_state(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    for name, version in {
        "codex_freecad": __package_version__,
        "mcp": "2.3.0",
        "universal_codex_tools": "0.20.0",
    }.items():
        folder = runtime / f"{name}-{version}.dist-info"
        folder.mkdir()
        (folder / "METADATA").write_text(f"Name: {name.replace('_', '-')}\nVersion: {version}\n")
    source = Path(__file__).parents[1] / "src/codex_freecad"
    (runtime / "codex_freecad").mkdir()
    (runtime / "codex_freecad/offline.py").write_text("# source fixture")
    (runtime / "codex_freecad/release.json").write_bytes((source / "release.json").read_bytes())
    for name in (
        "__init__.py",
        "process_lifetime.py",
        "offline_session.py",
        "offline_interpreter.py",
    ):
        (runtime / "codex_freecad" / name).write_bytes((source / name).read_bytes())
    output = tmp_path / "candidate"
    result = generate(tmp_path, output, runtime)
    compile((output / "offline-launch.py").read_text(), "offline-launch.py", "exec")
    config = json.loads((Path(result["plugin"]) / ".mcp.json").read_bytes())["mcpServers"]
    assert list(config) == ["freecad"]
    from codex_freecad.offline_interpreter import windowless_interpreter

    assert config["freecad"]["command"] == str(windowless_interpreter())
    assert result["python_image"]["subsystem"] == 2
    assert config["freecad"]["args"][:3] == ["-I", "-S", "-B"]
    assert not (output / "state").exists() and not (output / "registry").exists()
    assert not result["installed"] and not result["started"]
    assert (Path(result["plugin"]) / "skills/freecad-offline/SKILL.md").is_file()
    assert (
        hashlib.sha256((output / "offline-launch.py").read_bytes()).hexdigest()
        == result["launcher_sha256"]
    )


@pytest.mark.parametrize(
    "option",
    [
        ["--mode", "headless"],
        ["--freecad-cmd", "unsafe.exe"],
        ["--extensions", "unsafe"],
        ["--framework-backend"],
    ],
)
def test_native_and_shared_host_cli_options_are_refused_before_server_construction(
    tmp_path, monkeypatch, option
):
    from codex_freecad import offline

    monkeypatch.setattr(
        offline, "create_offline_server", lambda *_: pytest.fail("Unsupported route admitted")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "offline",
            "--workspace",
            str(tmp_path),
            "--state",
            str(tmp_path / "state"),
            "--registry",
            str(tmp_path / "registry"),
            *option,
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        offline.main()
    assert stopped.value.code == 2
    assert not (tmp_path / "state").exists() and not (tmp_path / "registry").exists()
