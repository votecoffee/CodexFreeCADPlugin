"""Read verified installed selection; never infer native/backend health."""

import argparse
import json
import runpy
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, required=True)
args = parser.parse_args()
loader = runpy.run_path(str(args.root / "Start-Mcp.py"))
selected = loader["selection"](args.root)
manifest = selected["manifest"]
print(
    json.dumps(
        {
            "selected_version": manifest["package_version"],
            "profile": manifest["profile"],
            "mode": manifest.get("mode"),
            "source_commit": manifest.get("source_commit"),
            "snapshot": selected["snapshot"],
            "route": manifest["route"],
            "running_health": "Not reporting; selection is not running-backend health",
            "restart": "Close the owning Codex connection after saving work; inspect uncertain operations",
        },
        indent=2,
    )
)
