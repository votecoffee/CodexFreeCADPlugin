"""Build a hollow quarter-circle elbow and a parameter-driven helical solid."""

import argparse
import json
import math
from pathlib import Path

from codex_freecad.client import HeadlessClient, LiveClient


def expected_volumes(outer=6, inner=4, wire=2, height=40):
    return {
        "elbow": math.pi * (outer**2 - inner**2) * (30 * math.pi / 2),
        "coil": math.pi * wire**2 * math.hypot(2 * math.pi * 15 * height / 10, height),
    }


def build(client, document="SweptDemo"):
    client.call("new_document", name=document)
    operations = [
        {
            "op": "create_parameters",
            "name": "Design",
            "parameters": [
                {"name": "OuterRadius", "type": "length", "value": "6 mm"},
                {"name": "InnerRadius", "type": "length", "value": "4 mm"},
                {"name": "WireRadius", "type": "length", "value": "2 mm"},
                {"name": "CoilHeight", "type": "length", "value": "40 mm"},
            ],
        },
        {
            "op": "create_sketch",
            "name": "BendPath",
            "geometry": [
                {
                    "type": "arc",
                    "start": [30, 0],
                    "mid": [30 / math.sqrt(2), 30 / math.sqrt(2)],
                    "end": [0, 30],
                },
            ],
        },
    ]
    for name, radius, parameter in [
        ("OuterProfile", 6, "OuterRadius"),
        ("InnerProfile", 4, "InnerRadius"),
        ("CoilProfile", 2, "WireRadius"),
    ]:
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
                "expression": "Design." + parameter,
            },
        ]
        if name != "CoilProfile":
            operations.append(
                {
                    "op": "set_placement",
                    "object": name,
                    "position": [30, 0, 0],
                    "axis": [1, 0, 0],
                    "angle": 90,
                }
            )
    operations += [
        {"op": "sweep", "name": "OuterSweep", "profiles": ["OuterProfile"], "path": "BendPath"},
        {"op": "sweep", "name": "InnerSweep", "profiles": ["InnerProfile"], "path": "BendPath"},
        {
            "op": "boolean",
            "name": "Elbow",
            "kind": "cut",
            "base": "OuterSweep",
            "tool": "InnerSweep",
        },
        {"op": "create_helix", "name": "CoilPath", "pitch": 10, "height": 40, "radius": 15},
        {
            "op": "set_expression",
            "object": "CoilPath",
            "property": "Height",
            "expression": "Design.CoilHeight",
        },
        {"op": "set_placement", "object": "CoilPath", "position": [80, 0, 0]},
        {
            "op": "set_placement",
            "object": "CoilProfile",
            "position": [95, 0, 0],
            "axis": [1, 0, 0],
            "angle": -math.degrees(math.atan2(2 * math.pi * 15, 10)),
        },
        {
            "op": "sweep",
            "name": "Coil",
            "profiles": ["CoilProfile"],
            "path": "CoilPath",
            "frenet": True,
        },
        {"op": "boolean", "name": "SweptParts", "kind": "fuse", "base": "Elbow", "tool": "Coil"},
    ]
    result = client.call("apply_operations", document=document, operations=operations)
    expected = expected_volumes()
    objects = {obj["name"]: obj for obj in result["document"]["objects"]}
    for name, key in (("Elbow", "elbow"), ("Coil", "coil")):
        if not objects[name]["shape"]["valid"] or not math.isclose(
            objects[name]["shape"]["volume_mm3"], expected[key], rel_tol=1e-5
        ):
            raise RuntimeError(
                name + " does not match its analytic volume within 1e-5 relative tolerance"
            )
    pair = objects["SweptParts"]
    if pair["shape"]["solids"] != 2 or not math.isclose(
        pair["shape"]["volume_mm3"], sum(expected.values()), rel_tol=1e-5
    ):
        raise RuntimeError("Final sweep example must preserve both solids and their total volume")
    return {
        "pair": pair,
        "expected_volumes_mm3": expected,
        "expected_volume_mm3": sum(expected.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("models"))
    parser.add_argument("--mode", choices=["live", "headless"], default="headless")
    parser.add_argument("--name", default="SweptDemo")
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
                "export_model", document=args.name, objects=["SweptParts"], path=args.name + ".step"
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
