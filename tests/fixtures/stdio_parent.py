"""Private test parent: forward original wire unchanged and wait for its child."""

import json
import subprocess
import sys
from pathlib import Path

spec = json.loads(Path(sys.argv[1]).read_bytes())
process = subprocess.Popen(
    spec["command"],
    stdin=sys.stdin,
    stdout=sys.stdout,
    stderr=sys.stderr,
    cwd=spec["cwd"],
    creationflags=subprocess.CREATE_NO_WINDOW,
)
Path(spec["child_pid_file"]).write_text(str(process.pid), encoding="ascii")
raise SystemExit(process.wait())
