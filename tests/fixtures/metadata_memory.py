"""Harmless actual Windows commit-limit proof; never imports native CAD or SDK."""

# ruff: noqa: E402
import json
import os
import sys
from pathlib import Path

runtime, state, output = (Path(v) for v in sys.argv[1:4])
sys.path.insert(0, str(runtime))
from codex_freecad.offline_interpreter import inherited_stdio, require_windowless_root
from codex_freecad.offline_session import root_lifetime
from codex_freecad.process_lifetime import (
    METADATA_MEMORY_BYTES,
    ProcessSlots,
    admit_native_memory,
    job_memory_status,
    process_tree_snapshot,
)

require_windowless_root()
inherited_stdio()
with root_lifetime(state, process_limit=4):
    report = {"before": job_memory_status(), "native_executed": False}
    try:
        payload = bytearray(METADATA_MEMORY_BYTES)
    except MemoryError:
        report["oversized_commit_refused"] = True
    else:
        del payload
        raise RuntimeError("Metadata commit limit was not enforced")
    with ProcessSlots(state / "native-pilot", limit=1):
        admit_native_memory()
        payload = bytearray(METADATA_MEMORY_BYTES)
        report["after_native_admission"] = job_memory_status()
        report["process_bound_after_admission"] = process_tree_snapshot()["maximum_processes"]
        del payload
    output.write_bytes(json.dumps(report, indent=2).encode())
os._exit(0)
