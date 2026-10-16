"""Upgrade a COPY of the jointed demo with saved ratios; headless native checks."""

import hashlib
import json
import math
from pathlib import Path


def build(workspace):
    import FreeCAD as App
    import Part

    from codex_freecad.engine import Engine

    workspace = Path(workspace)
    engine = Engine(workspace)
    source = workspace / "Input-Movable.FCStd"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    doc = engine.open_document(source.name)["name"]
    rules = [
        {"joint": "CarrierJoint", "driver": "SunJoint", "ratio": 0.25, "offset": 0},
        *[
            {"joint": f"PlanetJoint{i}", "driver": "SunJoint", "ratio": -0.75, "offset": 0}
            for i in range(1, 4)
        ],
    ]
    engine.apply_operations(
        doc,
        [
            *[
                {"op": "set_joint_coupling", "assembly": "GearboxAssembly", **rule}
                for rule in rules
            ],
            {
                "op": "set_joint_positions",
                "assembly": "GearboxAssembly",
                "positions": [{"joint": "SunJoint", "position": 0}],
            },
        ],
    )
    saved = engine.save_document(doc, "PlanetaryGearbox-Coupled.FCStd")
    data = engine.inspect_assembly(doc, "GearboxAssembly")
    assert data["couplings"] == rules
    assert len(data["components"]) == 15 and len(data["joints"]) == 14
    native = App.getDocument(doc)
    parts = [native.getObject(x["name"]) for x in data["components"]]
    count = sum(len(x.Shape.Solids) for x in parts)
    volume = sum(x.Shape.Volume for x in parts)
    assert count == 26 and all(x.Shape.isValid() for x in parts)
    exported = engine.export_model(doc, [x.Name for x in parts], "PlanetaryGearbox-Coupled.step")
    snapshot = Part.read(exported["path"])
    assert snapshot.isValid() and len(snapshot.Solids) == count
    assert math.isclose(snapshot.Volume, volume, rel_tol=1e-6)
    before = engine.revision(native)
    samples = engine.sample_motion(
        doc,
        "GearboxAssembly",
        "SunJoint",
        0,
        360,
        18,
        ["SunGearLink", "Planet1Link", "Planet2Link", "Planet3Link"],
    )
    assert samples["overlap_frames"] == 0
    for sample in samples["frames"]:
        coords = sample["coordinates"]
        assert abs(coords["CarrierJoint"] - sample["position"] * 0.25) < 1e-5
        assert all(
            abs(coords[f"PlanetJoint{i}"] + sample["position"] * 0.75) < 1e-5 for i in range(1, 4)
        )
    assert engine.revision(native) == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    report = {
        "plugin_version": engine.status()["plugin_version"],
        "freecad_version": engine.status()["freecad_version"],
        "operation_count": len(engine.status()["operations"]),
        "backend": "headless",
        "source_sha256": source_hash,
        "source_unchanged": True,
        "saved": saved,
        "exported": exported,
        "components": len(parts),
        "joints": len(data["joints"]),
        "solid_count": count,
        "volume_mm3": volume,
        "couplings": rules,
        "sampled_gear_checks": samples,
        "scope": "18 discrete sun/planet/planet BREP checks; source pose/revision preserved. Housing, full-ring mesh, continuous travel, loads and dynamics are outside these new sampled checks.",
        "panel_gui_validation": "pending user-run smoke test",
        "physical_drag_validation": "pending user's manual check",
    }
    (workspace / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    App.closeDocument(doc)


def verify_reopened(workspace):
    import FreeCAD as App

    from codex_freecad.engine import Engine

    workspace = Path(workspace)
    model = workspace / "PlanetaryGearbox-Coupled.FCStd"
    before = hashlib.sha256(model.read_bytes()).hexdigest()
    engine = Engine(workspace)
    doc = engine.open_document(model.name)["name"]
    assert len(engine.inspect_assembly(doc, "GearboxAssembly")["couplings"]) == 4
    # Driving a follower in a fresh native process recovers the input coordinate.
    engine.apply_operations(
        doc,
        [
            {
                "op": "set_joint_positions",
                "assembly": "GearboxAssembly",
                "positions": [{"joint": "CarrierJoint", "position": 300}],
            }
        ],
    )
    joints = {
        x["name"]: x["coordinate"]
        for x in engine.inspect_assembly(doc, "GearboxAssembly")["joints"]
    }
    assert abs(joints["SunJoint"] - 1200) < 1e-5
    assert abs(joints["CarrierJoint"] - 300) < 1e-5
    assert all(abs(joints[f"PlanetJoint{i}"] + 900) < 1e-5 for i in range(1, 4))
    engine.undo_document(doc)
    assert all(
        abs(x["coordinate"]) < 1e-5
        for x in engine.inspect_assembly(doc, "GearboxAssembly")["joints"]
        if x["kind"] in {"revolute", "slider"}
    )
    assert hashlib.sha256(model.read_bytes()).hexdigest() == before
    report = json.loads((workspace / "verification.json").read_text(encoding="utf-8"))
    report["fresh_process_reopen_inverse_pose_undo"] = True
    report["saved_model_unchanged_by_verification"] = True
    (workspace / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    App.closeDocument(doc)
