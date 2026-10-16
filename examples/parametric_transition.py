"""Create a mirrored pair of lofted solids driven by named native parameters."""

import argparse
import json
import math
from pathlib import Path

from codex_freecad.client import HeadlessClient, LiveClient


def expected_volume(base=20, top=10, height=45):
    return 2 * math.pi * height * (base * base + base * top + top * top) / 3


def build(client, document="ParametricDemo"):
    client.call("new_document", name=document)
    operations = [
        {
            "op": "create_parameters",
            "name": "Design",
            "parameters": [
                {"name": "BaseRadius", "type": "length", "value": "20 mm"},
                {"name": "TopRadius", "type": "length", "value": "10 mm"},
                {"name": "Height", "type": "length", "value": "45 mm"},
            ],
        }
    ]
    for name, radius, prop in [("Lower", 20, "BaseRadius"), ("Upper", 10, "TopRadius")]:
        operations += [
            {
                "op": "create_sketch",
                "name": name,
                "geometry": [{"type": "circle", "center": [0, 0], "radius": radius}],
            },
            {"op": "add_constraint", "object": name, "type": "Coincident", "args": [0, 3, -1, 1]},
            {"op": "add_constraint", "object": name, "type": "Radius", "args": [0, float(radius)]},
            {
                "op": "set_expression",
                "object": name,
                "property": "Constraints[1]",
                "expression": "Design." + prop,
            },
        ]
    operations += [
        {
            "op": "set_expression",
            "object": "Upper",
            "property": "Placement.Base.z",
            "expression": "Design.Height",
        },
        {"op": "loft", "name": "Transition", "profiles": ["Lower", "Upper"], "ruled": True},
        {"op": "mirror", "name": "Reflected", "source": "Transition", "point": [40, 0, 0]},
        {
            "op": "boolean",
            "name": "TransitionPair",
            "kind": "fuse",
            "base": "Transition",
            "tool": "Reflected",
        },
    ]
    result = client.call("apply_operations", document=document, operations=operations)
    pair = next(o for o in result["document"]["objects"] if o["name"] == "TransitionPair")
    shape = pair["shape"]
    if (
        not shape["valid"]
        or shape["solids"] != 2
        or not math.isclose(shape["volume_mm3"], expected_volume())
    ):
        raise RuntimeError("Native loft/mirror pair did not match its analytic volume")
    return {"pair": pair, "expected_volume_mm3": expected_volume()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("models"))
    parser.add_argument("--mode", choices=["live", "headless"], default="headless")
    parser.add_argument("--name", default="ParametricDemo")
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
                "export_model",
                document=args.name,
                objects=["TransitionPair"],
                path=args.name + ".step",
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
