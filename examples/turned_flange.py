"""Create a revolved flange, circular bolt holes, and a row of linked finished parts."""

import argparse
import json
import math
from pathlib import Path

from codex_freecad.client import HeadlessClient, LiveClient


def build(client, document="TurnedDemo"):
    client.call("new_document", name=document)
    result = client.call(
        "apply_operations",
        document=document,
        operations=[
            {
                "op": "create_sketch",
                "name": "Profile",
                "geometry": [{"type": "rectangle", "origin": [10, 0], "width": 20, "height": 8}],
            },
            {
                "op": "set_placement",
                "object": "Profile",
                "position": [0, 0, 0],
                "axis": [1, 0, 0],
                "angle": 90,
            },
            {"op": "revolve", "name": "Flange", "source": "Profile"},
            {"op": "create_cylinder", "name": "Drill", "radius": 2, "height": 12},
            {"op": "set_placement", "object": "Drill", "position": [22, 0, -2]},
            {"op": "circular_pattern", "name": "BoltHoles", "source": "Drill", "count": 6},
            {
                "op": "boolean",
                "name": "DrilledFlange",
                "kind": "cut",
                "base": "Flange",
                "tool": "BoltHoles",
            },
            {
                "op": "linear_pattern",
                "name": "FlangeRow",
                "source": "DrilledFlange",
                "count": 3,
                "step": [75, 0, 0],
            },
        ],
    )
    expected = 3 * math.pi * ((30**2 - 10**2) * 8 - 6 * 2**2 * 8)
    row = next(o for o in result["document"]["objects"] if o["name"] == "FlangeRow")
    if not row["shape"]["valid"] or not math.isclose(row["shape"]["volume_mm3"], expected):
        raise RuntimeError("Native flange row did not match its expected volume")
    return {
        "row": row,
        "expected_volume_mm3": expected,
        "width_constraint": result["results"][0]["geometry"][0]["dimension_constraints"]["width"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("models"))
    parser.add_argument("--mode", choices=["live", "headless"], default="headless")
    parser.add_argument("--name", default="TurnedDemo")
    args = parser.parse_args()
    client = (
        HeadlessClient(args.workspace)
        if args.mode == "headless"
        else LiveClient(args.workspace / ".codex-freecad-live.json")
    )
    try:
        print(json.dumps(build(client, args.name), indent=2))
        print(client.call("save_document", document=args.name, path=args.name + ".FCStd"))
        print(
            client.call(
                "export_model", document=args.name, objects=["FlangeRow"], path=args.name + ".step"
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
