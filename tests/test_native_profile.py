"""Source/pure native candidate checks. No MCP connection or FreeCAD execution."""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from codex_freecad import __package_version__, native, native_session
from codex_freecad.engine import CadError, Workspace


class Backend:
    def __init__(self):
        self.calls = []
        self.revision = "revision-a"
        self.fail = False

    def call(self, method, **params):
        self.calls.append((method, params))
        if method == "status":
            return {"plugin_package_version": __package_version__, "mode": "headless"}
        if self.fail:
            raise OSError("Synthetic lost native reply")
        if method in {"inspect_document", "new_document", "apply_operations"}:
            return {"name": params.get("document", "Demo"), "revision": self.revision}
        if method in {"save_document", "export_model"}:
            return {"path": params["path"]}
        return {}

    def close(self):
        self.calls.append(("close", {}))


@pytest.fixture
def client(tmp_path):
    pytest.importorskip("universal_tools.resources")
    result = native_session.NativeClient(
        Backend(), tmp_path / "models", tmp_path / "state", mode="headless"
    )
    try:
        yield result
    finally:
        # A test exercising close failure must retain the lease until teardown.
        result.client.close = lambda: None
        result.close()


def receipts(client):
    return [json.loads(path.read_bytes()) for path in client.journal.glob("*.json")]


def test_native_document_write_receipt_and_known_revision(client):
    result = client.call("new_document", name="Demo")
    assert result["native_receipt"]["state"] == "reply-received"
    assert not result["native_receipt"]["replay_allowed"]
    assert client.revisions["Demo"] == "revision-a"
    client.call("apply_operations", document="Demo", expected_revision="revision-a", operations=[])
    assert len(receipts(client)) == 2


def test_missing_review_and_revision_never_dispatch(client):
    with pytest.raises(CadError, match="expected_revision"):
        client.call("apply_operations", document="Demo", operations=[])
    with pytest.raises(CadError, match="Review this exact"):
        client.call("save_document", document="Demo", path="demo.FCStd")
    assert all(
        method not in {"apply_operations", "save_document"} for method, _ in client.client.calls
    )
    assert not receipts(client)


def test_source_and_output_guards_reach_native_engine(client):
    source = client.workspace.root / "input.FCStd"
    source.write_bytes(b"source fixture, no native load")
    reviewed = client.review_target(source.name)
    client.call("open_document", path=source.name)
    assert client.client.calls[-1][1]["expected_sha256"] == reviewed["sha256"]
    client.call("inspect_document", document="Demo")
    client.review_target("output.step")
    client.call("export_model", document="Demo", objects=["Box"], path="output.step")
    assert client.client.calls[-1][1]["expected_target_sha256"] == "absent"


def test_changed_target_or_document_refused_before_dispatch(client):
    client.call("inspect_document", document="Demo")
    client.review_target("output.FCStd")
    client.client.revision = "manual-edit"
    with pytest.raises(CadError, match="current document"):
        client.call("save_document", document="Demo", path="output.FCStd")
    (client.workspace.root / "output.FCStd").write_bytes(b"another user's source")
    with pytest.raises(CadError, match="Review this exact"):
        client.call("save_document", document="Demo", path="output.FCStd", overwrite=True)
    assert all(method != "save_document" for method, _ in client.client.calls)


def test_lost_reply_blocks_same_and_new_generation_without_replay(client):
    client.client.fail = True
    with pytest.raises(OSError, match="lost native reply"):
        client.call("new_document", name="Demo")
    record = receipts(client)[0]
    assert record["state"] == "uncertain" and record["replay_allowed"] is False
    with pytest.raises(CadError, match="uncertain"):
        client.call("new_document", name="Demo")
    other = native_session.NativeClient(
        Backend(), client.workspace.root, client.state, mode="headless"
    )
    with pytest.raises(CadError, match="Unresolved native receipt"):
        other.call("new_document", name="Demo")
    assert not other.client.calls


def test_admission_close_and_binding_are_fail_closed(client):
    with client.lock:
        with pytest.raises(CadError, match="capacity"):
            client.call("status")
        with pytest.raises(CadError, match="still active"):
            client.close()
    client.binding_check = lambda: (_ for _ in ()).throw(ValueError("Bridge descriptor changed"))
    with pytest.raises(ValueError, match="descriptor changed"):
        client.call("new_document", name="Demo")
    assert not client.client.calls
    client.close()
    client.close()
    assert client.client.calls == [("close", {})]


def test_backend_close_failure_is_not_marked_closed(client):
    client.call("status")
    client.client.close = lambda: (_ for _ in ()).throw(OSError("retained job close failed"))
    with pytest.raises(OSError):
        client.close()
    assert not client.closed
    assert client.native_admitted


def test_idle_frontends_share_metadata_but_native_admission_stays_one(client):
    from codex_freecad.process_lifetime import ProcessSlots

    other = native_session.NativeClient(
        Backend(), client.workspace.root, client.state, mode="headless"
    )
    try:
        client.review_target("demo.FCStd")
        other.review_target("demo.FCStd")
        assert not client.client.calls and not other.client.calls
        assert ProcessSlots.occupied(client.state / "native-pilot", limit=1) == 0
        client.call("status")
        with pytest.raises(native_session.NativeCapacityError, match="native capacity is busy"):
            other.call("new_document", name="Other")
        assert not other.client.calls and not other.uncertain and not receipts(other)
        assert not other.native_admitted
        # A capacity refusal leaves the connection usable for metadata.
        assert other.review_target("demo.FCStd")["native_opened"] is False
        client.close()
        assert ProcessSlots.occupied(client.state / "native-pilot", limit=1) == 0
        assert (
            other.call("new_document", name="Other")["native_receipt"]["state"] == "reply-received"
        )
        other.close()
        assert ProcessSlots.occupied(client.state / "native-pilot", limit=1) == 0
    finally:
        other.close()


def test_failed_backend_cleanup_keeps_capacity_until_cleanup_succeeds(client):
    client.call("status")
    client.client.close = lambda: (_ for _ in ()).throw(OSError("retained worker"))
    other = native_session.NativeClient(
        Backend(), client.workspace.root, client.state, mode="headless"
    )
    try:
        with pytest.raises(OSError, match="retained worker"):
            client.close()
        with pytest.raises(native_session.NativeCapacityError, match="native capacity is busy"):
            other.call("status")
        assert not other.client.calls
        client.client.close = lambda: None
        client.close()
        other.call("status")
    finally:
        other.close()


@pytest.mark.parametrize("path", ["../outside.FCStd", "outside.py"])
def test_native_review_preserves_workspace_boundary(client, path):
    with pytest.raises(CadError):
        client.review_target(path)


def test_worker_side_target_recheck_preserves_changed_source(tmp_path):
    workspace = Workspace(tmp_path)
    target = tmp_path / "demo.FCStd"
    target.write_bytes(b"first")
    reviewed = native_session.digest(target)
    target.write_bytes(b"changed")
    with pytest.raises(CadError, match="changed after review"):
        workspace.prepare_write(target.name, {".fcstd"}, True, reviewed)
    assert target.read_bytes() == b"changed" and not (tmp_path / "backups").exists()
    with pytest.raises(CadError, match="changed after review"):
        workspace.prepare_write(target.name, {".fcstd"}, True, "absent")


def test_native_hard_exit_occurs_after_cleanup_and_failure_exits_one(monkeypatch):
    from codex_freecad import process_lifetime

    events = []

    @contextmanager
    def session(*args):
        events.append("registered")
        try:
            yield
        finally:
            events.append("client-and-manager-closed")

    def run(server, *, exit_process, close_resources):
        assert not close_resources
        events.append("SDK-EOF")
        exit_process(0)

    monkeypatch.setattr(native, "native_session", session)
    monkeypatch.setattr(process_lifetime, "run_stdio", run)
    native.run_native(None, None, None, None, exit_process=lambda code: events.append(code))
    assert events == ["registered", "SDK-EOF", "client-and-manager-closed", 0]

    @contextmanager
    def failed(*args):
        yield
        raise OSError("unverified native cleanup")

    monkeypatch.setattr(native, "native_session", failed)
    with pytest.raises(OSError):
        native.run_native(None, None, None, None, exit_process=lambda code: events.append(code))
    assert events[-1] == 1


def test_explicit_executable_pin_refuses_before_native_launch(tmp_path, monkeypatch):
    from codex_freecad.client import HeadlessClient

    executable = tmp_path / "FreeCADCmd.exe"
    executable.write_bytes(b"harmless non-executable fixture")
    client = HeadlessClient(tmp_path / "models", str(executable), executable_sha256="0" * 64)
    monkeypatch.setattr(
        "codex_freecad.owned_process.spawn_owned", lambda *a, **k: pytest.fail("launched")
    )
    with pytest.raises(CadError, match="executable changed"):
        client._start()
    assert client.process is None


def test_native_static_candidate_uses_fixed_entry_and_no_live_state(tmp_path):
    from codex_freecad.native_setup import generate

    source = Path(__file__).parents[1] / "src/codex_freecad"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    for name, version in {
        "codex_freecad": __package_version__,
        "mcp": "2.3.0",
        "universal_codex_tools": "0.20.0",
    }.items():
        metadata = runtime / f"{name}-{version}.dist-info"
        metadata.mkdir()
        (metadata / "METADATA").write_text(f"Name: {name.replace('_', '-')}\nVersion: {version}\n")
    for name in (
        "__init__.py",
        "release.json",
        "offline.py",
        "offline_interpreter.py",
        "offline_session.py",
        "process_lifetime.py",
        "native.py",
        "native_session.py",
        "guidance/native.md",
        "standalone_skill.md",
    ):
        target = runtime / "codex_freecad" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / name).read_bytes())
    executable = tmp_path / "FreeCADCmd.exe"
    executable.write_bytes(b"fixture; never executed")
    output = tmp_path / "candidate"
    result = generate(tmp_path, output, runtime, native_target=executable)
    launcher = (output / "native-launch.py").read_text(encoding="utf-8")
    compile(launcher, "native-launch.py", "exec")
    assert "from codex_freecad.native import main" in launcher and "process_limit=4" in launcher
    assert not (output / "offline-launch.py").exists()
    assert not (output / "state").exists() and not (output / "registry").exists()
    assert not result["installed"] and not result["started"]
    config = json.loads((output / "plugin/.mcp.json").read_bytes())["mcpServers"]
    assert set(config) == {"freecad"} and config["freecad"]["args"][:3] == ["-I", "-S", "-B"]
    assert "--expected-target-sha256" in config["freecad"]["args"]
    assert (output / "plugin/skills/freecad-modeling/SKILL.md").is_file()


def test_native_budget_cannot_change_an_admitted_offline_root(tmp_path, monkeypatch):
    from codex_freecad import offline_session

    monkeypatch.setattr(offline_session, "_root_state", tmp_path)
    monkeypatch.setattr(offline_session, "_root_limit", 1)
    with pytest.raises(RuntimeError, match="differs"):
        with offline_session.root_lifetime(tmp_path, process_limit=4):
            pytest.fail("Existing offline containment was weakened")


def test_native_owner_cleanup_failure_keeps_uncertain_root_history(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    import universal_tools.management as management

    from codex_freecad import offline_session, process_lifetime, resource_ownership

    events = []

    @contextmanager
    def root(*args, **kwargs):
        assert kwargs["process_limit"] == 4
        yield

    @contextmanager
    def slot(*args, **kwargs):
        assert (
            kwargs["limit"] == {"history-admission": 1, "native-frontends": 4}[Path(args[0]).name]
        )
        yield

    @contextmanager
    def owner(*args, **kwargs):
        yield SimpleNamespace(
            owner_id="a" * 32, identity=SimpleNamespace(model_dump=lambda **k: {"pid": 123})
        )
        events.append("owner-close-failed")
        raise OSError("Unresolved launch reservation")

    @contextmanager
    def manager(*args, **kwargs):
        assert args[2]().restart_allowed is False
        yield
        events.append("manager-closed")

    client = SimpleNamespace(
        mode="headless",
        generation="b" * 32,
        uncertain=False,
        native_admitted=False,
        validated=False,
        lock=threading.Lock(),
        close=lambda: events.append("client-closed"),
    )
    monkeypatch.setattr(offline_session, "root_lifetime", root)
    monkeypatch.setattr(process_lifetime, "ProcessSlots", slot)
    monkeypatch.setattr(resource_ownership, "resource_session", owner)
    monkeypatch.setattr(management, "ManagedService", manager)
    with pytest.raises(OSError, match="Unresolved"):
        with native.native_session(client, tmp_path, tmp_path / "registry"):
            events.append("SDK-closed")
    records = list((tmp_path / "native-sessions").glob("*.json"))
    assert len(records) == 1 and json.loads(records[0].read_bytes())["state"] == "uncertain"
    assert events == ["SDK-closed", "client-closed", "manager-closed", "owner-close-failed"]


def test_native_session_lifetime_frontend_cap_and_release(tmp_path, monkeypatch):
    import threading
    from contextlib import ExitStack
    from types import SimpleNamespace

    import universal_tools.management as management

    from codex_freecad import offline_session, resource_ownership
    from codex_freecad.process_lifetime import ProcessSlots

    @contextmanager
    def root(*args, **kwargs):
        yield  # No process jobs/watchers in this source-only test.

    count = 0

    @contextmanager
    def owner(*args, **kwargs):
        nonlocal count
        count += 1
        yield SimpleNamespace(
            owner_id=f"{count:032x}",
            identity=SimpleNamespace(model_dump=lambda **k: {"pid": count}),
        )

    @contextmanager
    def manager(*args, **kwargs):
        yield

    monkeypatch.setattr(offline_session, "root_lifetime", root)
    monkeypatch.setattr(resource_ownership, "resource_session", owner)
    monkeypatch.setattr(management, "ManagedService", manager)

    def session():
        return native.native_session(
            SimpleNamespace(
                mode="headless", generation="fixture", lock=threading.Lock(), close=lambda: None
            ),
            tmp_path,
            tmp_path / "registry",
        )

    with ExitStack() as stack:
        for _ in range(4):
            stack.enter_context(session())
        assert ProcessSlots.occupied(tmp_path / "native-frontends", limit=4) == 4
        assert ProcessSlots.occupied(tmp_path / "native-pilot", limit=1) == 0
        with pytest.raises(RuntimeError, match="frontend limit"):
            with session():
                pytest.fail("Fifth frontend admitted")
        assert len(list((tmp_path / "native-sessions").glob("*.json"))) == 4
    assert ProcessSlots.occupied(tmp_path / "native-frontends", limit=4) == 0
    with session():
        assert ProcessSlots.occupied(tmp_path / "native-frontends", limit=4) == 1
