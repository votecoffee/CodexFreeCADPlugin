"""Explicit installer entry; normal serving never imports the checkout."""

import importlib
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if __name__ == "__main__":
    importlib.import_module("codex_freecad.runtime_builder").main()
