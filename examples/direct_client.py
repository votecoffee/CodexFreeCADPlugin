"""Run with the project's Python: python examples/direct_client.py [--mode live]."""

import argparse
import json
from pathlib import Path

from codex_freecad.client import HeadlessClient, LiveClient

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mode", choices=["live", "headless"], default="headless")
parser.add_argument("--workspace", type=Path, default=Path("models"))
parser.add_argument("--name", default="PlateDemo")
args = parser.parse_args()
client = (
    HeadlessClient(args.workspace)
    if args.mode == "headless"
    else LiveClient(args.workspace / ".codex-freecad-live.json")
)
try:
    created = client.call("new_document", name=args.name)
    operations = json.loads(Path(__file__).with_name("mounting_plate.json").read_text())
    result = client.call(
        "apply_operations",
        document=args.name,
        operations=operations,
        expected_revision=created["revision"],
    )
    print(json.dumps(result, indent=2))
    print(client.call("save_document", document=args.name, path=args.name + ".FCStd"))
    print(
        client.call(
            "export_model", document=args.name, objects=["MountingPlate"], path=args.name + ".step"
        )
    )
finally:
    client.close()
