"""Opt-in Python ownership checks; no MCP transport, FreeCAD, GUI or customer files."""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from stable_process_checks import original_exit, retained_writer

from codex_freecad import __package_version__
from codex_freecad import resource_ownership as ownership
from codex_freecad.generation_journal import reconcile_dead_claims

pytest.importorskip("universal_tools.resources")
pytestmark = [
    pytest.mark.resource_process,
    pytest.mark.skipif(
        os.name != "nt" or os.environ.get("FREECAD_RUN_METADATA_OWNERSHIP_FIXTURES") != "1",
        reason="Explicit bounded non-MCP Python ownership fixtures only",
    ),
]


@pytest.fixture(scope="module")
def sealed_runtime():
    from codex_freecad.offline_setup import inventory

    runtime = Path(os.environ["FREECAD_METADATA_OWNERSHIP_RUNTIME"])
    assert (
        json.loads((runtime / "codex_freecad/release.json").read_bytes())["package_version"]
        == __package_version__
    )
    closure = json.loads((runtime.parent / "connection/closure.json").read_bytes())
    assert inventory(runtime) == closure["files"]
    return runtime


@pytest.mark.parametrize("abrupt", [False, True])
def test_metadata_ledger_preserves_external_actor_and_uncertainty(tmp_path, abrupt, sealed_runtime):
    from codex_freecad.windows_identity import AppProcessDriver

    runtime = sealed_runtime
    python = str(Path(sys._base_executable).with_name("pythonw.exe"))
    external = subprocess.Popen(
        [python, "-I", "-S", "-B", "-c", "import time; time.sleep(90)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    state, registry, ready = (tmp_path / name for name in ("state", "registry", "ready.json"))
    root = subprocess.Popen(
        [
            python,
            "-I",
            "-S",
            "-B",
            str(Path(__file__).parent / "fixtures/owned_generation.py"),
            str(runtime),
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
    driver, actor_handles = AppProcessDriver(), []
    try:
        deadline = time.monotonic() + 15
        while not ready.exists():
            if root.poll() is not None:
                pytest.fail(root.stderr.read().decode("utf-8", "strict"))
            assert time.monotonic() < deadline, "Harmless ownership fixture did not become ready"
            time.sleep(0.05)
        observed = json.loads(ready.read_bytes())
        assert observed["native_started"] is False
        assert driver.capture_handle(int(root._handle), root.pid) == observed["owner"]
        assert observed["generation"]["current_job"]["maximum_processes"] == 4
        for identity in observed["generation"]["actors"]:
            handle = driver._open(identity["pid"])
            assert handle.identity == identity and handle.alive()
            actor_handles.append(handle)
        assert len(actor_handles) == 3
        receipt = Path(observed["receipt"])
        before = receipt.read_bytes()
        writer = retained_writer(root.stdin)
        if abrupt:
            root.kill()  # Exact private Popen handle; never a PID sweep.
        else:
            root.stdin.close()
        root.wait(timeout=10)
        root_exit = original_exit(driver, int(root._handle))
        assert root_exit["signaled"]
        if not abrupt:
            assert root_exit["exit_code"] == 0, root.stderr.read().decode("utf-8", "strict")
        for handle in actor_handles:
            deadline = time.monotonic() + 5
            while not original_exit(driver, handle.handle)["signaled"]:
                assert time.monotonic() < deadline, "Original private actor handle did not exit"
                time.sleep(0.02)
        assert not original_exit(driver, int(external._handle))["signaled"]
        if abrupt:
            survivor = ownership.create_owner(registry)
            report = reconcile_dead_claims(survivor, state)
            assert report["processes_terminated"] is False
            private = survivor.ledger.get(observed["private_resource_id"])
            shared = survivor.ledger.get(observed["shared_resource_id"])
            assert private.state == shared.state == "released"
            assert private.recovery_barrier and shared.recovery_barrier
            survivor.close()
        assert receipt.read_bytes() == before
        assert not original_exit(driver, int(external._handle))["signaled"]
        (tmp_path / "ownership-evidence.json").write_bytes(
            (
                json.dumps(
                    {
                        "abrupt": abrupt,
                        "root": observed["owner"],
                        "root_exit": root_exit,
                        "writer": writer,
                        "actor_exits": [
                            {"identity": h.identity, "exit": original_exit(driver, h.handle)}
                            for h in actor_handles
                        ],
                        "external_preserved": True,
                        "uncertainty_bytes_preserved": True,
                        "mcp_started": False,
                        "native_started": False,
                    },
                    indent=2,
                )
                + "\n"
            ).encode()
        )
    finally:
        if root.poll() is None:
            root.kill()  # Only the original private fixture root.
            root.wait(timeout=5)
        for handle in actor_handles:
            handle.close()
        for stream in (root.stdin, root.stdout, root.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        if external.poll() is None:
            external.terminate()  # Only this test-created external marker process.
            external.wait(timeout=5)


def test_concurrent_private_directory_creation_does_not_replace_a_winner(tmp_path, sealed_runtime):
    from codex_freecad.private_directories import ensure_private
    from codex_freecad.windows_identity import AppProcessDriver

    runtime = sealed_runtime
    python = str(Path(sys._base_executable).with_name("pythonw.exe"))
    target = tmp_path / "new-private"
    code = """
import json,sys
from pathlib import Path
runtime=Path(sys.argv[1])
sys.path[:0]=[str(runtime),str(runtime/'win32'),str(runtime/'win32/lib')]
import pywin32_bootstrap
from codex_freecad.offline_interpreter import inherited_stdio
from codex_freecad.private_directories import ensure_private
inherited_stdio()
print('ready',flush=True)
sys.stdin.buffer.read(1)
ensure_private(Path(sys.argv[2]))
info=Path(sys.argv[2]).stat()
ensure_private(Path(sys.argv[2]))
print(json.dumps({'identity':[info.st_dev,info.st_ino]}),flush=True)
"""
    processes, threads, ready = [], [], queue.Queue()
    try:
        for _ in range(4):
            process = subprocess.Popen(
                [python, "-I", "-S", "-B", "-c", code, str(runtime), str(target)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            processes.append(process)
            thread = threading.Thread(target=lambda p=process: ready.put(p.stdout.readline()))
            thread.start()
            threads.append(thread)
        assert [ready.get(timeout=15).strip() for _ in processes] == [b"ready"] * 4
        for process in processes:
            process.stdin.write(b"x")
            process.stdin.flush()
            process.stdin.close()
        exits, reported = [], []
        driver = AppProcessDriver()
        for process in processes:
            assert process.wait(timeout=15) == 0, process.stderr.read().decode("utf-8", "strict")
            exits.append(original_exit(driver, int(process._handle)))
            reported.append(json.loads(process.stdout.read())["identity"])
            assert exits[-1]["signaled"] and exits[-1]["exit_code"] == 0
        ensure_private(target)
        identity = (target.stat().st_dev, target.stat().st_ino)
        assert all(tuple(value) == identity for value in reported)
        ensure_private(target)
        assert identity == (target.stat().st_dev, target.stat().st_ino)
        (tmp_path / "directory-race.json").write_bytes(
            (
                json.dumps(
                    {
                        "creator_exits": exits,
                        "directory_identity": identity,
                        "mcp_started": False,
                        "native_started": False,
                    },
                    indent=2,
                )
                + "\n"
            ).encode()
        )
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()  # Exact original private fixture handle only.
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
        for thread in threads:
            thread.join(timeout=2)
