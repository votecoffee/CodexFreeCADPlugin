"""Demonstrate saved fit/mass limits, a rejected edit and a successful guarded change."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from codex_freecad.client import HeadlessClient, LiveClient
from codex_freecad.engine import CadError


def extension(capability, **arguments):
    return {"op": "extension", "capability": capability, "arguments": arguments}


def build(cad, workspace, name):
    outputs = {"model": name + ".FCStd", "step": name + ".step", "report": name + "-Checks.json"}
    if any((workspace / item).exists() for item in outputs.values()):
        raise ValueError("Choose a fresh --name; existing outputs are preserved")
    if Path(cad.call("status")["workspace"]) != workspace:
        raise ValueError("Client and backend must use the same workspace")
    created = cad.call("new_document", name=name)
    cad.call(
        "apply_operations",
        document=name,
        expected_revision=created["revision"],
        operations=[
            {
                "op": "create_parameters",
                "name": "Design",
                "parameters": [{"name": "ShaftRadius", "type": "length", "value": 7}],
            },
            {"op": "create_cylinder", "name": "Shaft", "radius": 7, "height": 40},
            {
                "op": "set_expression",
                "object": "Shaft",
                "property": "Radius",
                "expression": "Design.ShaftRadius",
            },
            extension(
                "parts.create_tube", name="Sleeve", outer_radius=12, inner_radius=8, height=20
            ),
            {"op": "set_placement", "object": "Sleeve", "position": [0, 0, 10]},
            extension(
                "requirements.create_set",
                name="FitLimits",
                rules=[
                    {
                        "id": "RadialClearance",
                        "metric": "clearance",
                        "object": "Shaft",
                        "other": "Sleeve",
                        "minimum": 0.5,
                        "absolute_tolerance": 1e-6,
                    },
                    {
                        "id": "ShaftMass",
                        "metric": "mass",
                        "object": "Shaft",
                        "density_kg_m3": 7850,
                        "maximum": 0.055,
                    },
                    {
                        "id": "ShaftLength",
                        "metric": "extent",
                        "object": "Shaft",
                        "axis": "z",
                        "maximum": 40,
                        "absolute_tolerance": 1e-6,
                    },
                ],
            ),
        ],
    )

    def preview(radius):
        return cad.call(
            "run_query",
            document=name,
            capability="studies.preview_changes",
            arguments={
                "changes": [{"object": "Design", "property": "ShaftRadius", "value": radius}],
                "objects": ["Shaft"],
                "requirement_sets": ["FitLimits"],
            },
        )["result"]

    baseline = cad.call("inspect_document", document=name)["revision"]
    bad = preview(7.75)
    if bad["requirements"]["all_passed_after"]:
        raise AssertionError("Oversized shaft unexpectedly passed fit/mass requirements")
    try:
        cad.call("apply_operations", **bad["apply_arguments"])
    except CadError as exc:
        if "Design requirements not satisfied" not in str(exc):
            raise
    else:
        raise AssertionError("Requirements failed to reject the oversized shaft")
    if cad.call("inspect_document", document=name)["revision"] != baseline:
        raise AssertionError("Rejected edit changed the model")
    good = preview(7.25)
    if not good["requirements"]["all_passed_after"]:
        raise AssertionError("Expected shaft dimensions failed design requirements")
    cad.call("apply_operations", **good["apply_arguments"])
    checked = cad.call(
        "run_query",
        document=name,
        capability="requirements.evaluate",
        arguments={"set": "FitLimits"},
    )["result"]
    expected_mass = math.pi * 7.25**2 * 40 * 7850e-9
    if (
        not checked["all_passed"]
        or not math.isclose(checked["rules"][0]["value"], 0.75, abs_tol=1e-8)
        or not math.isclose(checked["rules"][1]["value"], expected_mass, rel_tol=1e-8)
    ):
        raise AssertionError("Native fit/mass measurements disagree with independent formulas")
    cad.call("save_document", document=name, path=outputs["model"])
    cad.call("export_model", document=name, objects=["Shaft", "Sleeve"], path=outputs["step"])
    report = {
        "name": name,
        "backend": cad.call("status")["mode"],
        "checks": [
            "oversized shaft rejected with source revision preserved",
            "valid preview applied with final enforcement",
            "radial clearance and mass agree with analytic formulas",
        ],
        "rejected_proposal": bad["requirements"],
        "accepted_proposal": good["requirements"],
        "final_requirements": checked,
        "artifacts": [
            {
                "file": outputs[key],
                "sha256": hashlib.sha256((workspace / outputs[key]).read_bytes()).hexdigest(),
            }
            for key in ("model", "step")
        ],
        "scope": "Nominal evaluated geometry at one pose with explicit density. No manufacturing tolerance, wear, load or thermal expansion assessment.",
    }
    (workspace / outputs["report"]).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("work/requirements-demo"))
    parser.add_argument("--name", default="ShaftSleeve")
    parser.add_argument("--mode", choices=["headless", "live"], default="headless")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    client = (
        HeadlessClient(workspace)
        if args.mode == "headless"
        else LiveClient(workspace / ".codex-freecad-live.json")
    )
    try:
        report = build(client, workspace, args.name)
        print(
            json.dumps(
                {
                    "name": report["name"],
                    "checks": report["checks"],
                    "all_passed": report["final_requirements"]["all_passed"],
                    "report": args.name + "-Checks.json",
                    "artifacts": report["artifacts"],
                },
                indent=2,
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
