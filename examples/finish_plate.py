"""Round an example plate, chamfer its hole, then save and reimport STEP.

python examples/finish_plate.py --workspace models --name FinishedDemo [--mode live]
"""

import argparse
import json
import math
from pathlib import Path

from codex_freecad.client import HeadlessClient, LiveClient


def finish_existing_plate(client, document):
    topology = client.call("inspect_topology", document=document, object_name="MountingPlate")
    corner_edges = [
        edge["name"]
        for edge in topology["items"]
        if edge["curve"] == "Line"
        and math.isclose(edge["length_mm"], 8)
        and any(math.isclose(edge["center_mm"][0], x, abs_tol=1e-8) for x in (0, 80))
        and any(math.isclose(edge["center_mm"][1], y, abs_tol=1e-8) for y in (0, 50))
    ]
    if len(corner_edges) != 4:
        raise RuntimeError("Example plate did not have its four expected outer vertical edges")
    client.call(
        "apply_operations",
        document=document,
        expected_revision=topology["revision"],
        operations=[
            {
                "op": "fillet",
                "name": "RoundCorners",
                "base": "MountingPlate",
                "edges": corner_edges,
                "size": 3,
            }
        ],
    )
    topology = client.call("inspect_topology", document=document, object_name="RoundCorners")
    rim = [
        edge["name"]
        for edge in topology["items"]
        if edge["curve"] == "Circle"
        and math.isclose(edge.get("radius_mm", 0), 5)
        and math.isclose(edge["center_mm"][2], 8, abs_tol=1e-8)
    ]
    if len(rim) != 1:
        raise RuntimeError("Example plate did not have its expected top circular hole edge")
    return client.call(
        "apply_operations",
        document=document,
        expected_revision=topology["revision"],
        operations=[
            {
                "op": "chamfer",
                "name": "FinishedPlate",
                "base": "RoundCorners",
                "edges": rim,
                "size": 0.8,
            }
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("models"))
    parser.add_argument("--mode", choices=["live", "headless"], default="headless")
    parser.add_argument("--name", default="FinishedDemo")
    args = parser.parse_args()
    client = (
        HeadlessClient(args.workspace)
        if args.mode == "headless"
        else LiveClient(args.workspace / ".codex-freecad-live.json")
    )
    try:
        client.call("new_document", name=args.name)
        operations = json.loads(Path(__file__).with_name("mounting_plate.json").read_text())
        client.call("apply_operations", document=args.name, operations=operations)
        result = finish_existing_plate(client, args.name)
        final = next(obj for obj in result["document"]["objects"] if obj["name"] == "FinishedPlate")
        print(json.dumps(final, indent=2))
        print(client.call("save_document", document=args.name, path=args.name + ".FCStd"))
        exported = client.call(
            "export_model", document=args.name, objects=["FinishedPlate"], path=args.name + ".step"
        )
        print(exported)
        imported = client.call(
            "import_model", document=args.name, path=args.name + ".step", name="ImportedCopy"
        )
        print(json.dumps(imported["results"], indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
