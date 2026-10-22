"""Opt-in non-MCP Python root fixtures; no engineering or manager service starts."""

import json
import os
import subprocess
import sys
import time

import pytest

from codex_freecad.process_lifetime import ProcessSlots

ResourceLedger = pytest.importorskip("universal_tools.resources").ResourceLedger
pytestmark = [
    pytest.mark.resource_process,
    pytest.mark.skipif(
        os.name != "nt" or os.environ.get("FREECAD_RUN_OFFLINE_FIXTURES") != "1",
        reason="Explicit harmless single-process offline lifetime fixtures only",
    ),
]

CODE = r"""
import json,os,sys,time
from pathlib import Path
sys.path[:0]=json.loads(sys.argv[1])
import pywin32_bootstrap
from universal_tools.resources import ResourceLedger,durable_json
from codex_freecad.offline_session import root_lifetime
state=Path(sys.argv[2]); mode=sys.argv[3]
with root_lifetime(state):
    ledger=ResourceLedger(state/'registry')
    identity=ledger.driver.capture(os.getpid())
    durable_json(state/'identity.json',identity)
    denied=True
    if mode=='capacity':
        import subprocess
        try:
            child=subprocess.Popen([sys.executable,'-I','-S','-c',"from pathlib import Path; import sys; Path(sys.argv[1]).write_text('executed')",str(state/'must-not-execute')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            child.wait(timeout=3); denied=False
        except OSError:
            pass
    print(json.dumps({'identity':identity,'child_denied':denied}),flush=True)
    if mode=='crash': os._exit(23)
    while True: time.sleep(0.05)
"""


def command(state, mode):
    return [
        sys._base_executable,
        "-I",
        "-S",
        "-B",
        "-c",
        CODE,
        json.dumps(sys.path),
        str(state),
        mode,
    ]


def test_single_process_job_refuses_child_creation_and_eof_exits_within_bound(tmp_path):
    process = subprocess.Popen(
        command(tmp_path, "capacity"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        response = json.loads(process.stdout.readline())
        assert response["child_denied"] and not (tmp_path / "must-not-execute").exists()
        process.stdin.close()
        assert process.wait(timeout=15) == 1
        assert ProcessSlots.occupied(tmp_path / "frontends", limit=4) == 0
        assert ResourceLedger(tmp_path / "registry").driver.state(response["identity"]) in {
            "absent",
            "different",
        }
    finally:
        if process.poll() is None:
            process.kill()  # Retained fixture-only Popen handle.
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def test_abrupt_root_exit_releases_slot_without_removing_identity_history(tmp_path):
    result = subprocess.run(
        command(tmp_path, "crash"),
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 23, result.stderr
    identity = json.loads((tmp_path / "identity.json").read_bytes())
    assert ResourceLedger(tmp_path / "registry").driver.state(identity) in {"absent", "different"}
    with ProcessSlots(tmp_path / "frontends", limit=4):
        pass
    assert (tmp_path / "identity.json").exists()


def test_parent_death_ends_root_without_recovery_of_other_apps(tmp_path):
    args = command(tmp_path, "parent")
    supervisor = (
        "import json,os,subprocess,sys,time; from pathlib import Path; "
        "p=subprocess.Popen(json.loads(sys.argv[1]),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW); "
        "path=Path(sys.argv[2]); deadline=time.monotonic()+6\n"
        "while not path.exists():\n"
        "    if p.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Fixture root did not start')\n"
        "    time.sleep(0.02)\n"
        "print(path.read_text(),flush=True); os._exit(29)"
    )
    result = subprocess.run(
        [
            sys._base_executable,
            "-I",
            "-S",
            "-c",
            supervisor,
            json.dumps(args),
            str(tmp_path / "identity.json"),
        ],
        capture_output=True,
        text=True,
        timeout=12,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 29, result.stderr
    identity = json.loads(result.stdout)
    driver = ResourceLedger(tmp_path / "registry").driver
    deadline = time.monotonic() + 15
    while driver.state(identity) not in {"absent", "different"}:
        assert time.monotonic() < deadline, "Harmless offline root outlived its parent bound"
        time.sleep(0.05)
    assert ProcessSlots.occupied(tmp_path / "frontends", limit=4) == 0
    assert (tmp_path / "identity.json").exists()
