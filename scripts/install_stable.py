"""Explicit installer entry; normal serving never imports the checkout."""

import importlib
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
for stream in (sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="strict")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if __name__ == "__main__":
    importlib.import_module("codex_freecad.runtime_builder").main()
