"""Opt-in non-MCP Python root fixtures; no engineering or manager service starts."""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes as w

import pytest

from codex_freecad.offline_interpreter import windowless_interpreter
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
from codex_freecad.offline_interpreter import require_windowless_root,inherited_stdio
require_windowless_root()
state=Path(sys.argv[2]); mode=sys.argv[3]
if mode=='capacity': inherited_stdio()
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
        str(windowless_interpreter()),
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
        assert_no_children(process, tmp_path)
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


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("usage", w.DWORD),
        ("pid", w.DWORD),
        ("heap", ctypes.c_size_t),
        ("module", w.DWORD),
        ("threads", w.DWORD),
        ("parent", w.DWORD),
        ("priority", w.LONG),
        ("flags", w.DWORD),
        ("image", w.WCHAR * 260),
    ]


def children(pid):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes, api.CreateToolhelp32Snapshot.restype = (
        [w.DWORD, w.DWORD],
        w.HANDLE,
    )
    api.Process32FirstW.argtypes, api.Process32FirstW.restype = (
        [w.HANDLE, ctypes.POINTER(ProcessEntry)],
        w.BOOL,
    )
    api.Process32NextW.argtypes, api.Process32NextW.restype = (
        [w.HANDLE, ctypes.POINTER(ProcessEntry)],
        w.BOOL,
    )
    api.CloseHandle.argtypes = [w.HANDLE]
    handle = api.CreateToolhelp32Snapshot(2, 0)
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        more = api.Process32FirstW(handle, ctypes.byref(entry))
        while more:
            if entry.parent == pid:
                result.append({"pid": entry.pid, "parent": entry.parent, "image": entry.image})
            more = api.Process32NextW(handle, ctypes.byref(entry))
        return result
    finally:
        api.CloseHandle(handle)


def assert_no_children(process, state):
    driver = ResourceLedger(state / "readback-registry").driver
    root = driver.capture_handle(int(process._handle), process.pid)
    samples = []
    for _ in range(5):
        observed = []
        for row in children(process.pid):
            try:
                row["identity"] = driver.capture(row["pid"])
            except ProcessLookupError:
                row["identity"] = "exited-before-capture"
            observed.append(row)
        samples.append(observed)
        (state / "no-child-evidence.json").write_text(
            json.dumps({"root": root, "samples": samples}, indent=2)
        )
        assert not observed, "Unexpected windowless-root child; exact observations retained"
        time.sleep(0.025)


@pytest.mark.parametrize("missing_streams", [False, True])
def test_windowless_inherited_unicode_pipes_and_real_eof_with_missing_sys_streams(
    tmp_path, missing_streams
):
    code = r"""
import json,sys
from pathlib import Path
sys.path[:0]=json.loads(sys.argv[1])
from codex_freecad.offline_interpreter import require_windowless_root,inherited_stdio
from codex_freecad.offline_session import root_lifetime
require_windowless_root()
initial={name:getattr(sys,name) is None for name in ('stdin','stdout','stderr')}
retained_originals=(sys.stdin,sys.stdout,sys.stderr)
if sys.argv[3]=='1': sys.stdin=sys.stdout=sys.stderr=None
streams=inherited_stdio()
with root_lifetime(sys.argv[2]):
    line=sys.stdin.readline()
    eof=sys.stdin.read()==''
    sys.stdout.write(json.dumps({'line':line,'eof':eof,'streams':streams,'initial_none':initial},ensure_ascii=False)+'\n'); sys.stdout.flush()
    sys.stderr.write('stderr Ω 漢字 🛠\n'); sys.stderr.flush()
"""
    process = subprocess.Popen(
        [
            str(windowless_interpreter()),
            "-I",
            "-S",
            "-B",
            "-c",
            code,
            json.dumps(sys.path),
            str(tmp_path),
            "1" if missing_streams else "0",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        assert_no_children(process, tmp_path)
        text = "Français Ω 漢字 🛠\n"
        stdout, stderr = process.communicate(text.encode("utf-8"), timeout=8)
        assert process.returncode == 0, (stdout, stderr)
        result = json.loads(stdout.decode("utf-8"))
        assert result["line"] == text and result["eof"]
        assert stderr.decode("utf-8") == "stderr Ω 漢字 🛠\n"
        assert all(
            result["streams"][name]["encoding"] == "utf-8" for name in ("stdin", "stdout", "stderr")
        )
        if missing_streams:
            assert all(result["streams"][name]["rebuilt"] for name in ("stdin", "stdout", "stderr"))
        (tmp_path / "unicode-stdio-evidence.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


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
