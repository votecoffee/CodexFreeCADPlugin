"""Harmless Python ownership fixture; no FreeCAD, GUI, model, or native effect."""

# Runtime binding intentionally precedes imports from the reviewed closure.
# ruff: noqa: E402

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

if sys.argv[1] == "helper":
    time.sleep(300)
    raise SystemExit(0)
if sys.argv[1] == "worker":
    helper = subprocess.Popen(
        [sys.executable, "-I", "-S", "-B", __file__, "helper"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    raise SystemExit(helper.wait())

runtime, state, registry, ready = (Path(value) for value in sys.argv[1:5])
external_pid = int(sys.argv[5])
sys.dont_write_bytecode = True
sys.path[:0] = [
    str(runtime),
    str(runtime / "win32"),
    str(runtime / "win32/lib"),
    str(runtime / "Pythonwin"),
]
import pywin32_bootstrap  # noqa: F401 - the normal retained bootstrap does this too.
from universal_tools.resources import durable_json

from codex_freecad.offline_interpreter import inherited_stdio, require_windowless_root
from codex_freecad.offline_session import root_lifetime
from codex_freecad.owned_process import spawn_owned
from codex_freecad.process_lifetime import ProcessSlots
from codex_freecad.resource_ownership import resource_session, sample_generation

require_windowless_root()
inherited_stdio()
try:
    with (
        root_lifetime(state, process_limit=4),
        resource_session(registry, state=state) as owner,
        ProcessSlots(state / "native-pilot", limit=1),
    ):
        shared = owner.remember_process(
            external_pid, "External shared Python fixture", ownership="shared"
        )
        owner.set_recovery_barrier(
            shared.resource_id, "External fixture remains outside app ownership"
        )
        windowless = Path(sys.executable)
        worker = spawn_owned(
            [str(windowless), "-I", "-S", "-B", __file__, "worker"],
            resource_owner=owner,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        generation_path = state / "process-generations" / (owner.owner_id + ".json")
        deadline = time.monotonic() + 10
        while True:
            sample_generation()
            observed = json.loads(generation_path.read_bytes())
            if len(observed["current_job"]["owned_processes"]) >= 3:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Indirect harmless fixture actor was not observed")
            time.sleep(0.05)
        receipt = state / "native-receipts" / ("f" * 32) / "synthetic-uncertainty.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_bytes(
            b'{"state":"uncertain","method":"synthetic-no-native-effect","replay_allowed":false}'
        )
        durable_json(
            ready,
            {
                "owner": owner.identity.model_dump(mode="json"),
                "owner_id": owner.owner_id,
                "private_resource_id": worker.claim.resource_id,
                "shared_resource_id": shared.resource_id,
                "generation": observed,
                "receipt": str(receipt),
                "native_started": False,
            },
        )
        sys.stdin.buffer.read(1)  # A blocked reader must not block the independent parent watcher.
        # Private-fixture EOF cleanup only. The acceptance case kills its exact
        # parent while retaining this writer, so this graceful branch is not used.
        if worker.poll() is None:
            worker.terminate()
            worker.wait(timeout=5)
        worker.close_owned_tree()
        owner.release_attachment(shared.resource_id)
    os._exit(0)
except BaseException:
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    os._exit(1)  # Root job handles contain every private fixture descendant.
