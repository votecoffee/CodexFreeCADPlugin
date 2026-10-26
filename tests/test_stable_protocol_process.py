"""Opt-in real protocol/launch checks with an invalid, never-run native target."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import pytest
from stable_process_checks import Wire, original_exit, private_memory, retained_writer

from codex_freecad import __package_version__, __version__
from codex_freecad.process_lifetime import METADATA_CONNECTIONS, ProcessSlots, metadata_slot_memory
from codex_freecad.stable_install import prepare, select
from codex_freecad.stable_launcher import selection

pytestmark = [
    pytest.mark.resource_process,
    pytest.mark.skipif(
        os.name != "nt" or os.environ.get("FREECAD_RUN_STABLE_FIXTURES") != "1",
        reason="Explicit isolated stable-launch fixtures only; no engineering apps",
    ),
]


@pytest.fixture(scope="module")
def reviewed_runtime():
    value = os.environ.get("FREECAD_STABLE_RUNTIME")
    if not value:
        pytest.fail("Set FREECAD_STABLE_RUNTIME to the explicit reviewed current runtime")
    root = Path(value)
    release = json.loads((root / "codex_freecad/release.json").read_bytes())
    assert release["package_version"] == __package_version__
    closure = json.loads((root.parent / "connection/closure.json").read_bytes())
    from codex_freecad.offline_setup import inventory

    assert inventory(root) == closure["files"]
    return root


def installed(tmp_path, runtime):
    root = tmp_path / "App owned Ω with spaces"
    workspace = tmp_path / "Models Ω"
    workspace.mkdir()
    target = tmp_path / "FreeCADCmd.exe"
    target.write_bytes(b"Invalid executable: must NEVER run in metadata fixtures")
    prepared = prepare(
        root,
        runtime,
        workspace,
        native_target=target,
        state=tmp_path / "shared-state",
        registry=tmp_path / "shared-registry",
    )
    select(root, prepared["snapshot"], expected_selection="absent")
    return Path(prepared["root"]), workspace, prepared


def generation(state, identity):
    records = [json.loads(p.read_bytes()) for p in (state / "process-generations").glob("*.json")]
    return next(r for r in records if r["owner"] == identity)


def record(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def integer_defaults(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "integer" and "default" in schema:
            value = schema["default"]
            assert type(value) is int
            assert value >= schema.get("minimum", value)
            assert value <= schema.get("maximum", value)
            if "exclusiveMinimum" in schema:
                assert value > schema["exclusiveMinimum"]
            if "exclusiveMaximum" in schema:
                assert value < schema["exclusiveMaximum"]
        for value in schema.values():
            integer_defaults(value)
    elif isinstance(schema, list):
        for value in schema:
            integer_defaults(value)


def test_cache_removal_and_immutable_update_preserve_active_peer(tmp_path, reviewed_runtime):
    root, workspace, first = installed(tmp_path, reviewed_runtime)
    cache = tmp_path / "positively-identified-disposable-cache" / __package_version__
    shutil.copytree(first["plugin"], cache)
    route = json.loads((cache / ".mcp.json").read_bytes())["mcpServers"]["freecad"]
    assert not any(
        str(cache) in value for value in [route["command"], route["cwd"], *route["args"]]
    )
    fixture = workspace / "Préview-Ω.FCStd"
    fixture.write_bytes(b"Synthetic hash fixture only; never opened by native software")
    with Wire(route) as peer:
        initialized = peer.initialize()
        assert initialized["serverInfo"]["version"] == __version__
        tools = peer.call("tools/list")["tools"]
        assert len(tools) == 27
        integer_defaults(tools)
        overview = peer.tool("get_workflow")
        old_guide = peer.tool("get_native_workflow")
        reviewed = peer.tool("review_native_target", path=fixture.name)
        assert reviewed["sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
        assert reviewed["native_opened"] is False and "Ω" in reviewed["path"]
        state = Path(first["manifest"]["state"])
        observed = generation(state, peer.identity)
        assert observed["current_job"]["maximum_processes"] == 4
        assert observed["actors"] == [peer.identity]
        # Only this complete, positively identified test cache is removed.
        assert cache.resolve().is_relative_to(tmp_path.resolve())
        cache_hashes = {
            str(p.relative_to(cache)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in cache.rglob("*")
            if p.is_file()
        }
        shutil.rmtree(cache)
        assert not cache.exists()
        with Wire(route) as after_cache:
            after_cache.initialize()
            assert after_cache.tool("get_native_workflow")["sha256"] == old_guide["sha256"]
            assert after_cache.eof()["exit_code"] == 0
        updated = tmp_path / "reviewed-synthetic-guide-update"
        shutil.copytree(reviewed_runtime, updated)
        guide = updated / "codex_freecad/guidance/native.md"
        guide.write_bytes(
            guide.read_bytes() + b"\nSynthetic launcher update fixture, no domain changes.\n"
        )
        second = prepare(
            root,
            updated,
            workspace,
            native_target=tmp_path / "FreeCADCmd.exe",
            state=first["manifest"]["state"],
            registry=first["manifest"]["registry"],
        )
        select(root, second["snapshot"], expected_selection=selection(root)["selection_sha256"])
        assert second["route"] == route
        with Wire(route) as replacement:
            replacement.initialize()
            new_guide = replacement.tool("get_native_workflow")
            assert new_guide["sha256"] != old_guide["sha256"]
            retained = peer.tool("get_native_workflow")
            assert retained["sha256"] == old_guide["sha256"]
            assert retained["deployment"]["running_snapshot"] == first["snapshot"]
            assert retained["deployment"]["selected_snapshot"] == second["snapshot"]
            assert ProcessSlots.occupied(state / "native-pilot", limit=1) == 0
            new_exit = replacement.eof()
            assert new_exit["exit_code"] == 0
        old_exit = peer.eof()
        assert old_exit["exit_code"] == 0
    assert ProcessSlots.occupied(state / "frontends", limit=4) == 0
    record(
        tmp_path / "cache-update-evidence.json",
        {
            "initialized": initialized,
            "tool_count": len(tools),
            "emitted_tool_schemas": tools,
            "overview": overview,
            "cache_hashes_before_removal": cache_hashes,
            "cache_removed": True,
            "old_snapshot": first["snapshot"],
            "new_snapshot": second["snapshot"],
            "old_guide_sha256": old_guide["sha256"],
            "new_guide_sha256": new_guide["sha256"],
            "old_exit": old_exit,
            "new_exit": new_exit,
            "native_started": False,
        },
    )


def test_budgeted_metadata_frontdoors_preserve_legacy_and_native_capacity(
    tmp_path, reviewed_runtime
):
    root, workspace, prepared = installed(tmp_path, reviewed_runtime)
    state = Path(prepared["manifest"]["state"])
    with ExitStack() as stack:
        # Hold every original lease. New metadata must not consume, clear or
        # reinterpret those live legacy owners' files.
        for _ in range(4):
            stack.enter_context(ProcessSlots(state / "frontends", limit=4))
            stack.enter_context(ProcessSlots(state / "native-frontends", limit=4))
        peers = []
        memory = []
        phases = []
        marker = workspace / "hash-only.FCStd"
        marker.write_bytes(b"Synthetic metadata fixture; never open with native software")
        for phase in ("steady-24", "reconnect-overlap-48"):
            added = [stack.enter_context(Wire(prepared["route"])) for _ in range(24)]
            peers.extend(added)
            for peer in added:
                peer.initialize()
                assert peer.initialize_elapsed < 30
                assert len(peer.call("tools/list")["tools"]) == 27
                guide = peer.tool("get_native_workflow")
                assert guide["mode"] == "headless"
                assert "48 metadata connections" in guide["text"]
                assert guide["ownership"]["actors"] == 1
                admission = guide["connection_admission"]
                limit = metadata_slot_memory(admission["slot"])
                assert guide["memory"]["limit_bytes"] == limit
                assert 0 < guide["memory"]["peak_commit_bytes"] <= limit
                reviewed = peer.tool("review_native_target", path=marker.name)
                assert reviewed["native_opened"] is False
                assert reviewed["sha256"] == hashlib.sha256(marker.read_bytes()).hexdigest()
                assert not any(guide["native_policy"].values())
                memory.append(guide["memory"])
            phases.append({"phase": phase, "roots": [private_memory(p) for p in peers]})
        assert ProcessSlots.occupied(state / "frontends", limit=4) == 4
        assert ProcessSlots.occupied(state / "metadata-frontdoors-v2", limit=48) == 48
        assert ProcessSlots.occupied(state / "native-pilot", limit=1) == 0
        with Wire(prepared["route"]) as refused:
            with pytest.raises((RuntimeError, BrokenPipeError), match=".*"):
                refused.initialize()
            assert refused.process.wait(timeout=15) == 1
            for reader in refused.readers:
                reader.join(timeout=2)
            assert "metadata connection" in "".join(refused.errors)
            assert original_exit(refused.driver, int(refused.process._handle))["signaled"]
        exits = [peers[0].eof()]
        with Wire(prepared["route"]) as replacement:
            replacement.initialize()
            exits.append(replacement.eof())
        for peer in peers[1:]:
            exits.append(peer.eof())
        assert all(e["exit_code"] == 0 and e["original_handle_exit"]["signaled"] for e in exits)
    assert ProcessSlots.occupied(state / "metadata-frontdoors-v2", limit=48) == 0
    record(
        tmp_path / "admission-evidence.json",
        {
            "limit": METADATA_CONNECTIONS,
            "simulated_legacy_leases_preserved": 4,
            "excess_refused": True,
            "actual_memory_phases": phases,
            "memory_measurements": memory,
            "cold_initialize_seconds": [p.initialize_elapsed for p in peers],
            "native_leases": 0,
            "peer_identities": [p.identity for p in peers],
            "original_handle_exits": exits,
        },
    )


def test_compatible_runtime_and_new_reconnects_share_the_same_pool(tmp_path, reviewed_runtime):
    compatibility = os.environ.get("FREECAD_COMPAT_RUNTIME")
    if not compatibility:
        pytest.skip("Explicit reviewed 26.1024.101538 runtime required for mixed-version proof")
    old_runtime = Path(compatibility)
    assert (
        json.loads((old_runtime / "codex_freecad/release.json").read_bytes())["package_version"]
        == "26.1024.101538"
    )
    from codex_freecad.offline_setup import inventory

    old_closure = json.loads((old_runtime.parent / "connection/closure.json").read_bytes())
    assert inventory(old_runtime) == old_closure["files"]
    _, workspace, prepared = installed(tmp_path, reviewed_runtime)
    state = Path(prepared["manifest"]["state"])
    # Run the compatible package's own preparer, including its release checks.
    # This creates a PRIVATE app with an invalid native target and the SAME fixture pool.
    code = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from codex_freecad.stable_install import prepare, select
args = json.loads(sys.argv[2])
result = prepare(**args)
select(Path(result['root']), result['snapshot'], expected_selection='absent')
print(json.dumps(result))
"""
    args = {
        "root": str(tmp_path / "Compatible app"),
        "runtime": str(old_runtime),
        "workspace": str(workspace),
        "native_target": str(tmp_path / "FreeCADCmd.exe"),
        "state": str(state),
        "registry": prepared["manifest"]["registry"],
    }
    old = json.loads(
        subprocess.check_output(
            [
                sys._base_executable,
                "-I",
                "-S",
                "-B",
                "-c",
                code,
                str(old_runtime),
                json.dumps(args),
            ],
            stderr=subprocess.PIPE,
            timeout=120,
        )
    )
    exits, phases = [], []
    with ExitStack() as stack:
        old_peers = [stack.enter_context(Wire(old["route"])) for _ in range(16)]
        for peer in old_peers:
            assert peer.initialize()["serverInfo"]["version"] == "26.1024.101538"
            guide = peer.tool("get_native_workflow")
            assert guide["memory"]["limit_bytes"] == 128 * 1024**2
            assert guide["ownership"]["actors"] == 1
        new_peers = []
        for added_count, phase in ((8, "steady-24"), (24, "full-reconnect-48")):
            added = [stack.enter_context(Wire(prepared["route"])) for _ in range(added_count)]
            new_peers.extend(added)
            for peer in added:
                assert peer.initialize()["serverInfo"]["version"] == __version__
                assert peer.initialize_elapsed < 30
                assert len(peer.call("tools/list")["tools"]) == 27
                guide = peer.tool("get_native_workflow")
                assert guide["ownership"]["actors"] == 1
                assert guide["connection_admission"]["slot"] >= 16
                assert guide["memory"]["limit_bytes"] == 96 * 1024**2
                assert not any(guide["native_policy"].values())
            phases.append(
                {
                    "phase": phase,
                    "compatible": [private_memory(p) for p in old_peers],
                    "new": [private_memory(p) for p in new_peers],
                }
            )
        report = new_peers[0].tool("get_native_workflow")["connection_admission"]
        assert report["metadata_occupied"] == 48
        assert report["metadata_occupied_commit_reservation_bytes"] == 5 * 1024**3
        assert (
            old_peers[0].tool("get_native_workflow")["connection_admission"]["metadata_occupied"]
            == 16
        )  # Its old limited observation does not erase the other 32 owners.
        with Wire(prepared["route"]) as refused:
            with pytest.raises((RuntimeError, BrokenPipeError)):
                refused.initialize()
            assert refused.process.wait(timeout=15) == 1
        exits.append(old_peers[0].eof())
        with Wire(prepared["route"]) as replacement:
            replacement.initialize()
            guide = replacement.tool("get_native_workflow")
            assert guide["connection_admission"]["slot"] < 16
            assert guide["memory"]["limit_bytes"] == 128 * 1024**2
            exits.append(replacement.eof())
        for peer in [*old_peers[1:], *new_peers]:
            exits.append(peer.eof())
        assert all(e["exit_code"] == 0 and e["original_handle_exit"]["signaled"] for e in exits)
    assert ProcessSlots.occupied(state / "metadata-frontdoors-v2", limit=48) == 0
    assert ProcessSlots.occupied(state / "native-pilot", limit=1) == 0
    record(
        tmp_path / "mixed-version-evidence.json",
        {
            "old_snapshot": old["snapshot"],
            "new_snapshot": prepared["snapshot"],
            "old_runtime_closure_verified": True,
            "phases": phases,
            "excess_refused": True,
            "original_handle_exits": exits,
            "native_executed": False,
            "same_pool": str(state / "metadata-frontdoors-v2"),
        },
    )


def test_unknown_receipt_is_caller_safe_and_preserved_without_native_dispatch(
    tmp_path, reviewed_runtime
):
    root, workspace, prepared = installed(tmp_path, reviewed_runtime)
    state = Path(prepared["manifest"]["state"])
    original = state / "native-receipts" / ("a" * 32) / "fixture.json"
    original.parent.mkdir(parents=True)
    raw = b'{"state":"uncertain","replay_allowed":false,"method":"synthetic-no-effect"}'
    original.write_bytes(raw)
    with Wire(prepared["route"]) as peer:
        peer.initialize()
        refused = peer.tool("new_document", name="MustNotDispatch")
        assert refused["isError"] and "Unresolved native receipt" in refused["content"][0]["text"]
        assert original.read_bytes() == raw
        assert ProcessSlots.occupied(state / "native-pilot", limit=1) == 0
        assert generation(state, peer.identity)["actors"] == [peer.identity]
        assert peer.eof()["exit_code"] == 0
    record(
        tmp_path / "uncertainty-evidence.json",
        {
            "refusal": refused,
            "original_receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "native_started": False,
        },
    )


@pytest.mark.parametrize(
    "damage",
    [
        "missing-pointer",
        "bad-pointer",
        "bootstrap",
        "runtime",
        "unexpected-arguments",
        "package-junction",
    ],
)
def test_selected_damage_refuses_actual_startup_without_fallback(
    tmp_path, reviewed_runtime, damage
):
    root, workspace, prepared = installed(tmp_path, reviewed_runtime)
    if damage == "missing-pointer":
        (root / "launcher/current.json").unlink()
    elif damage == "bad-pointer":
        (root / "launcher/current.json").write_bytes(b"bad selection")
    elif damage == "unexpected-arguments":
        prepared["route"] = {
            **prepared["route"],
            "args": [*prepared["route"]["args"], "--workspace", "must-not-override"],
        }
    elif damage == "package-junction":
        package = root / prepared["manifest"]["runtime"] / "codex_freecad"
        retained = tmp_path / "retained-original-package"
        assert package.resolve().is_relative_to(tmp_path.resolve())
        assert retained.resolve().is_relative_to(tmp_path.resolve())
        package.rename(retained)
        subprocess.run(
            [os.environ["ComSpec"], "/d", "/c", "mklink", "/J", str(package), str(retained)],
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        path = (
            root / prepared["manifest"]["entry"]
            if damage == "bootstrap"
            else root / prepared["manifest"]["runtime"] / "codex_freecad/native.py"
        )
        path.write_bytes(path.read_bytes() + b"\n# deliberate private test tamper\n")
    with Wire(prepared["route"]) as peer:
        assert peer.process.wait(timeout=20) == 1
        for reader in peer.readers:
            reader.join(timeout=2)
        assert not peer.messages and peer.errors
        assert peer.driver.state(peer.identity) in {"absent", "different"}
    assert ProcessSlots.occupied(Path(prepared["manifest"]["state"]) / "frontends", limit=4) == 0
    assert (
        ProcessSlots.occupied(
            Path(prepared["manifest"]["state"]) / "metadata-frontdoors-v2", limit=16
        )
        == 0
    )
    record(
        tmp_path / "refusal-evidence.json",
        {
            "damage": damage,
            "stderr": "".join(peer.errors),
            "exit_code": 1,
            "no_protocol_execution": True,
            "identity": peer.identity,
        },
    )


def wait_for(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            pytest.fail("Bounded lifecycle observation timed out")
        time.sleep(0.05)


@pytest.mark.parametrize("compatible_slots", [0, 16])
def test_actual_metadata_memory_limit_and_native_policy_readback(
    tmp_path, reviewed_runtime, compatible_slots
):
    script = Path(__file__).with_name("fixtures") / "metadata_memory.py"
    output = tmp_path / "memory-evidence.json"
    with ExitStack() as stack:
        for _ in range(compatible_slots):
            stack.enter_context(ProcessSlots(tmp_path / "state/metadata-frontdoors-v2", limit=16))
        process = subprocess.run(
            [
                str(Path(sys._base_executable).with_name("pythonw.exe")),
                "-I",
                "-S",
                "-B",
                str(script),
                str(reviewed_runtime),
                str(tmp_path / "state"),
                str(output),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=20,
        )
    assert process.returncode == 0, process.stderr.decode("utf-8", "replace")
    result = json.loads(output.read_bytes())
    assert result["before"]["limit_bytes"] == metadata_slot_memory(compatible_slots)
    assert result["oversized_commit_refused"]
    assert result["after_native_admission"]["limit_bytes"] is None
    assert result["process_bound_after_admission"] == 4


def test_active_owned_fixture_eof_preserves_external_and_uncertain_receipt(
    tmp_path, reviewed_runtime
):
    from codex_freecad.windows_identity import AppProcessDriver

    _, _, prepared = installed(tmp_path, reviewed_runtime)
    state = Path(prepared["manifest"]["state"])
    registry = Path(prepared["manifest"]["registry"])
    script = Path(__file__).with_name("fixtures") / "owned_generation.py"
    ready = tmp_path / "active-ready.json"
    external = subprocess.Popen(
        [sys._base_executable, "-I", "-S", "-B", "-c", "import time; time.sleep(120)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    active = subprocess.Popen(
        [
            prepared["route"]["command"],
            "-I",
            "-S",
            "-B",
            str(script),
            str(reviewed_runtime),
            str(state),
            str(registry),
            str(ready),
            str(external.pid),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    driver, checked = AppProcessDriver(), []
    try:
        wait_for(lambda: ready.exists() or active.poll() is not None)
        assert ready.exists(), active.stderr.read().decode("utf-8", "replace")
        observed = json.loads(ready.read_bytes())
        actors = observed["generation"]["actors"]
        checked = [driver.open(actor) for actor in actors]
        assert len(checked) == 3
        receipt = Path(observed["receipt"])
        original = receipt.read_bytes()
        record(
            tmp_path / "active-eof-trigger.json",
            {"at": time.time(), "writer": retained_writer(active.stdin), "actors": actors},
        )
        active.stdin.close()
        code = active.wait(timeout=15)
        exits = [original_exit(driver, h.handle) for h in checked]
        record(
            tmp_path / "active-eof-evidence.json",
            {
                "exit_code": code,
                "original_handle_exits": exits,
                "external_preserved": external.poll() is None,
                "receipt_preserved": receipt.read_bytes() == original,
                "native_started": False,
                "stderr": active.stderr.read().decode("utf-8", "replace"),
            },
        )
        assert code == 0
        assert all(item["signaled"] for item in exits)
        assert external.poll() is None and receipt.read_bytes() == original
        assert ProcessSlots.occupied(state / "metadata-frontdoors-v2", limit=16) == 0
        assert ProcessSlots.occupied(state / "native-pilot", limit=1) == 0
    finally:
        if active.poll() is None:
            active.kill()
            active.wait(timeout=5)  # Only the original private fixture process handle.
        if external.poll() is None:
            external.kill()
            external.wait(timeout=5)
        for h in checked:
            h.close()
        for stream in (active.stdin, active.stdout, active.stderr):
            if not stream.closed:
                stream.close()


def test_queued_startup_eof_releases_new_admission_without_native_work(tmp_path, reviewed_runtime):
    _, _, prepared = installed(tmp_path, reviewed_runtime)
    state = Path(prepared["manifest"]["state"])
    with ProcessSlots(state / "history-admission", limit=1):
        with Wire(prepared["route"]) as queued:

            def reached_history_queue():
                return any(
                    json.loads(p.read_bytes())["actor"] == queued.identity
                    for p in (state / "recovery-observations").glob("*.json")
                )

            wait_for(reached_history_queue, timeout=30)
            queued.send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2026-07-28",
                        "capabilities": {},
                        "clientInfo": {"name": "queued-fixture", "version": "1"},
                    },
                }
            )
            record(
                tmp_path / "queued-eof-trigger.json",
                {
                    "phase": "history writer wait after recovery observation",
                    "at": time.time(),
                    "writer": retained_writer(queued.process.stdin),
                    "initialize_queued": True,
                },
            )
            started = time.monotonic()
            result = queued.eof()
            record(
                tmp_path / "queued-eof-evidence.json",
                {
                    **result,
                    "elapsed": time.monotonic() - started,
                    "native_started": False,
                    "original_handle_signaled": queued.process.poll() is not None,
                },
            )
            assert result["exit_code"] == 1
            assert time.monotonic() - started < 10
            assert "history writer contention" in result["stderr"]
            assert not list((state / "process-generations").glob("*.json"))
    assert ProcessSlots.occupied(state / "metadata-frontdoors-v2", limit=16) == 0
    assert ProcessSlots.occupied(state / "native-pilot", limit=1) == 0
    with Wire(prepared["route"]) as replacement:
        replacement.initialize()
        assert replacement.eof()["exit_code"] == 0


def test_parent_loss_with_retained_writer_closes_exact_native_frontend(tmp_path, reviewed_runtime):
    root, workspace, prepared = installed(tmp_path, reviewed_runtime)
    state = Path(prepared["manifest"]["state"])
    proxy = Path(__file__).with_name("fixtures") / "stdio_parent.py"
    spec = tmp_path / "parent.json"
    record(
        spec,
        {
            "command": [prepared["route"]["command"], *prepared["route"]["args"]],
            "cwd": prepared["route"]["cwd"],
            "child_pid_file": str(tmp_path / "child.pid"),
        },
    )
    with (
        Wire(prepared["route"]) as peer,
        Wire(
            prepared["route"],
            command=[sys._base_executable, "-I", "-S", "-B", str(proxy), str(spec)],
        ) as owned_parent,
    ):
        peer.initialize()
        owned_parent.initialize()
        wait_for(lambda: len(list((state / "process-generations").glob("*.json"))) == 2)
        histories = [
            json.loads(p.read_bytes()) for p in (state / "process-generations").glob("*.json")
        ]
        lost = next(h for h in histories if h["owner"] != peer.identity)
        target = lost["owner"]
        held = peer.driver.open(target)  # Exact private fixture generation captured while alive.
        try:
            started = time.monotonic()
            owned_parent.process.kill()  # Only our retained parent Popen handle.
            owned_parent.process.wait(timeout=5)
            writer = retained_writer(owned_parent.process.stdin)
            record(
                tmp_path / "parent-loss-trigger.json",
                {"trigger": "retained-parent-handle-killed", "at": time.time(), "writer": writer},
            )
            wait_for(lambda: original_exit(peer.driver, held.handle)["signaled"], timeout=16)
            exit_proof = original_exit(peer.driver, held.handle)
            record(tmp_path / "parent-original-exit.json", exit_proof)
            elapsed = time.monotonic() - started
            assert peer.tool("get_native_workflow")["mode"] == "headless"
            original = (state / "process-generations" / (lost["owner_id"] + ".json")).read_bytes()
            with Wire(prepared["route"]) as reconnected:
                reconnected.initialize()
                assert reconnected.eof()["exit_code"] == 0
            assert (
                state / "process-generations" / (lost["owner_id"] + ".json")
            ).read_bytes() == original
            record(
                tmp_path / "parent-loss-evidence.json",
                {
                    "parent": owned_parent.identity,
                    "lost_root": target,
                    "elapsed_seconds": elapsed,
                    "retained_writer": True,
                    "writer": writer,
                    "original_handle_exit": exit_proof,
                    "original_lifecycle": json.loads(original)["lifecycle"],
                    "live_peer_preserved": True,
                    "native_started": False,
                    "forced_child_cleanup": False,
                },
            )
        finally:
            if held.alive():
                peer.driver.kernel.TerminateProcess(held.handle, 92)
            held.close()


def test_owner_loss_recovers_proven_claims_and_preserves_peer_external_and_uncertainty(
    tmp_path, reviewed_runtime
):
    from test_offline_process_fixtures import children
    from universal_tools.resources import ResourceLedger

    from codex_freecad.windows_identity import AppProcessDriver

    root, workspace, prepared = installed(tmp_path, reviewed_runtime)
    state = Path(prepared["manifest"]["state"])
    registry = Path(prepared["manifest"]["registry"])
    fixture_script = Path(__file__).with_name("fixtures") / "owned_generation.py"
    proxy = fixture_script.with_name("stdio_parent.py")
    ready = tmp_path / "owned-ready.json"
    external = subprocess.Popen(
        [sys._base_executable, "-I", "-S", "-B", "-c", "import time; time.sleep(300)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    spec = tmp_path / "owner-parent.json"
    record(
        spec,
        {
            "command": [
                prepared["route"]["command"],
                "-I",
                "-S",
                "-B",
                str(fixture_script),
                str(reviewed_runtime),
                str(state),
                str(registry),
                str(ready),
                str(external.pid),
            ],
            "cwd": str(tmp_path),
            "child_pid_file": str(tmp_path / "owned-child.pid"),
        },
    )
    parent = subprocess.Popen(
        [sys._base_executable, "-I", "-S", "-B", str(proxy), str(spec)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    driver, held, actor_handles = AppProcessDriver(), None, []
    try:
        with Wire(prepared["route"]) as peer:
            peer.initialize()
            try:
                wait_for(lambda: ready.exists() or parent.poll() is not None)
                assert ready.exists(), "Harmless fixture exited before readiness"
            except BaseException:
                if parent.poll() is not None:
                    stderr = parent.stderr.read().decode("utf-8", "replace")
                    record(
                        tmp_path / "owned-startup-failure.json",
                        {"stderr": stderr, "exit_code": parent.returncode},
                    )
                    pytest.fail("Harmless ownership fixture startup failed: " + stderr)
                raise
            observed = json.loads(ready.read_bytes())
            held = driver.open(observed["owner"])
            actors = observed["generation"]["actors"]
            actor_handles = [driver.open(actor) for actor in actors]
            assert (
                len(actors) >= 3 and observed["generation"]["current_job"]["maximum_processes"] == 4
            )
            descendants, pending = [], [observed["owner"]["pid"]]
            while pending:
                rows = children(pending.pop())
                descendants.extend(rows)
                pending.extend(row["pid"] for row in rows)
                assert len(descendants) <= 3
            assert {row["pid"] for row in descendants} == {
                p["pid"] for p in actors if p != observed["owner"]
            }
            busy = peer.tool("freecad_status")
            assert busy["isError"] and "native capacity is busy" in busy["content"][0]["text"]
            original_receipt = Path(observed["receipt"]).read_bytes()
            ledger = ResourceLedger(registry, driver=driver)
            original_claim = ledger._path(observed["private_resource_id"]).read_bytes()
            started = time.monotonic()
            parent.kill()  # Exact original private test-parent handle only.
            parent.wait(timeout=5)
            writer = retained_writer(parent.stdin)
            record(
                tmp_path / "owner-loss-trigger.json",
                {
                    "trigger": "retained-parent-handle-killed",
                    "at": time.time(),
                    "writer": writer,
                    "actors": actors,
                },
            )
            wait_for(
                lambda: all(
                    original_exit(driver, handle.handle)["signaled"] for handle in actor_handles
                ),
                timeout=16,
            )
            exits = [original_exit(driver, handle.handle) for handle in actor_handles]
            record(
                tmp_path / "owner-original-exits.json",
                {"actors": actors, "exits": exits, "writer": retained_writer(parent.stdin)},
            )
            elapsed = time.monotonic() - started
            assert external.poll() is None
            assert peer.tool("get_native_workflow")["mode"] == "headless"
            with Wire(prepared["route"]) as reconnected:
                reconnected.initialize()
                private = ledger.get(observed["private_resource_id"])
                shared = ledger.get(observed["shared_resource_id"])
                assert private.state == shared.state == "released"
                assert private.recovery_barrier and shared.recovery_barrier
                assert private.reconciliation and shared.reconciliation
                assert Path(observed["receipt"]).read_bytes() == original_receipt
                blocked = reconnected.tool("new_document", name="MustNotReplay")
                assert (
                    blocked["isError"]
                    and "Unresolved native receipt" in blocked["content"][0]["text"]
                )
                assert ProcessSlots.occupied(state / "native-pilot", limit=1) == 0
                assert external.poll() is None
                assert reconnected.eof()["exit_code"] == 0
            assert any(
                p.read_bytes() == original_claim
                for p in (state / "recovery-observations").glob("*.before.json")
            )
            record(
                tmp_path / "owner-loss-recovery-evidence.json",
                {
                    "original_generation": observed,
                    "independent_descendant_inventory": descendants,
                    "actors_gone": [driver.state(p) for p in actors],
                    "original_handle_exits": exits,
                    "writer": writer,
                    "elapsed_seconds": elapsed,
                    "private_reconciled": private.model_dump(mode="json"),
                    "shared_reconciled": shared.model_dump(mode="json"),
                    "external_fixture_preserved_during_recovery": True,
                    "live_peer_preserved": True,
                    "original_claim_sha256": hashlib.sha256(original_claim).hexdigest(),
                    "uncertain_receipt_sha256": hashlib.sha256(original_receipt).hexdigest(),
                    "native_started": False,
                    "forced_generation_cleanup": False,
                },
            )
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if held is not None:
            if held.alive():
                driver.kernel.TerminateProcess(held.handle, 93)
            held.close()
        if external.poll() is None:
            external.kill()  # Own original sentinel handle; never app recovery authority.
            external.wait(timeout=5)
        for handle in actor_handles:
            handle.close()
        for stream in (parent.stdin, parent.stdout, parent.stderr):
            stream.close()
