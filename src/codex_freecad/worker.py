"""Executed as a script by FreeCADCmd, never by the host Python interpreter."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_freecad.engine import Engine  # noqa: E402

PREFIX = "@@CODEX_FREECAD@@"


def emit(value):
    sys.stdout.write("\n" + PREFIX + json.dumps(value, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def main():
    engine = Engine(os.environ["CODEX_FREECAD_WORKSPACE"])
    emit({"ready": True, "status": engine.status()})
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if request.get("method") == "shutdown":
                break
            result = engine.call(request["method"], request.get("params", {}))
            emit({"id": request["id"], "result": result})
        except Exception as exc:
            emit(
                {
                    "id": request.get("id") if isinstance(request, dict) else None,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )


# FreeCADCmd imports a .py script with its stem as __name__.
main()
