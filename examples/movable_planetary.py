"""Convert the editable gearbox into a native jointed assembly and render its motion."""

import hashlib
import json
import math
import shutil
from pathlib import Path

from planetary_motion_controls import joint_positions, set_angle


def frame_data(placement):
    return {
        "position": list(placement.Base),
        "axis": list(placement.Rotation.Axis),
        "angle": math.degrees(placement.Rotation.Angle),
    }


def build_and_render(workspace):
    import FreeCAD as App
    import FreeCADGui as Gui
    from pivy import coin  # noqa: F401 - registers camera wrappers

    from codex_freecad.engine import Engine

    workspace = Path(workspace).resolve()
    engine = Engine(workspace, gui=True)
    source_path = workspace / "PlanetaryGearbox.FCStd"
    doc = App.openDocument(str(source_path))
    doc.Label = "CODEX · Movable planetary gearbox · 4:1"
    asm_name = "GearboxAssembly"
    sources = [
        "FinishedBase",
        "RingHousing",
        "SunGear",
        "Carrier",
        "PlanetPins",
        "PlanetWashers",
        "InputShaft",
        "OutputShaft",
        "OutputCollar",
        "InputCollar",
        "CarrierBolts",
        "HousingBolts",
    ]
    source_for = {name + "Link": name for name in sources}
    source_for.update({f"Planet{i + 1}Link": "PlanetGear" for i in range(3)})
    rest = {name: doc.getObject(source).Placement for name, source in source_for.items()}
    for i in range(3):
        rotation = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), 120 * i))
        rest[f"Planet{i + 1}Link"] = rotation * rest[f"Planet{i + 1}Link"]
    operations = [{"op": "create_assembly", "name": asm_name}]
    operations += [
        {"op": "add_component", "assembly": asm_name, "name": name, "source": source}
        for name, source in source_for.items()
    ]
    operations.append(
        {
            "op": "ground_component",
            "assembly": asm_name,
            "name": "BaseGround",
            "component": "FinishedBaseLink",
        }
    )

    def joint(name, kind, first, second, world_frame=None):
        world = App.Placement() if world_frame is None else world_frame
        operations.append(
            {
                "op": "create_joint",
                "assembly": asm_name,
                "name": name,
                "kind": kind,
                "component_a": first,
                "component_b": second,
                "frame_a": frame_data(rest[first].inverse() * world),
                "frame_b": frame_data(rest[second].inverse() * world),
            }
        )

    joint("SunJoint", "revolute", "FinishedBaseLink", "SunGearLink")
    joint("CarrierJoint", "revolute", "FinishedBaseLink", "CarrierLink")
    for i in range(3):
        name = f"Planet{i + 1}Link"
        joint(f"PlanetJoint{i + 1}", "revolute", "CarrierLink", name, rest[name])
    for parent, children in [
        ("FinishedBaseLink", ["RingHousing", "HousingBolts"]),
        ("SunGearLink", ["InputShaft", "InputCollar"]),
        (
            "CarrierLink",
            ["PlanetPins", "PlanetWashers", "CarrierBolts", "OutputShaft", "OutputCollar"],
        ),
    ]:
        for child in children:
            joint(child + "Mount", "fixed", parent, child + "Link")
    operations.append(
        {"op": "set_joint_positions", "assembly": asm_name, "positions": joint_positions(0)}
    )
    engine.apply_operations(doc.Name, operations)
    doc.getObject("PlanetGears").Visibility = False
    for name in source_for:
        doc.getObject(name).Visibility = True
    doc.recompute()
    view = Gui.getDocument(doc.Name).activeView()
    view.setCameraType("Orthographic")
    direction = App.Vector(0.8, -1.2, 1.7)
    right = App.Vector(0, 0, 1).cross(direction)
    view.setCameraOrientation(App.Rotation(right, direction.cross(right), direction, "ZXY").Q)
    view.fitAll()
    camera = view.getCameraNode()
    camera.height.setValue(180)
    camera.position.setValue(*(App.Vector(0, 0, 18) + direction.normalize() * 400))
    camera.nearDistance.setValue(1)
    camera.farDistance.setValue(2000)
    Gui.updateGui()
    view.saveImage(str(workspace / "PlanetaryGearbox-Movable.png"), 1440, 1200, "White")
    saved = engine.save_document(doc.Name, "PlanetaryGearbox-Movable.FCStd")
    frames = workspace / "frames"
    frames.mkdir(exist_ok=True)
    for index in range(60):
        set_angle(engine, doc, index * 8)
        Gui.updateGui()
        view.saveImage(str(frames / f"{index:03}.png"), 900, 750, "White")
    set_angle(engine, doc, 0)
    report = engine.inspect_assembly(doc.Name, asm_name)
    report.update(
        {
            "saved": saved,
            "rendered_frames": 60,
            "input_degrees_per_frame": 8,
            "loop_degrees": 480,
            "carrier_to_input_ratio": 0.25,
            "planet_absolute_to_input_ratio": -0.5,
        }
    )
    (workspace / "motion-build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # A portable native-only subset supports the optional player without MCP/Pydantic.
    root = Path(__file__).resolve().parents[1]
    native = workspace / "native"
    package = native / "codex_freecad"
    package.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "engine.py", "assemblies.py"):
        shutil.copy2(root / "src" / "codex_freecad" / name, package / name)
    shutil.copy2(
        root / "examples" / "planetary_motion_controls.py", native / "planetary_motion_controls.py"
    )
    (workspace / "PlayPlanetary.FCMacro").write_text(
        "import sys\nfrom pathlib import Path\nimport FreeCAD as App\n"
        "_folder = Path(__file__).resolve().parent\n"
        "sys.path.insert(0, str(_folder / 'native'))\n"
        "from planetary_motion_controls import show_controls\n"
        "_planetary_panel = show_controls(_folder)\n",
        encoding="utf-8",
    )
    App.closeDocument(doc.Name)


def verify(workspace):
    import FreeCAD as App
    import Part

    from codex_freecad.engine import Engine

    workspace = Path(workspace).resolve()
    source = workspace / "PlanetaryGearbox-Movable.FCStd"
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    engine = Engine(workspace)
    opened = engine.open_document("PlanetaryGearbox-Movable.FCStd")
    doc = App.getDocument(opened["name"])
    report = engine.inspect_assembly(doc.Name, "GearboxAssembly")
    parts = [doc.getObject(x["name"]) for x in report["components"]]
    assert len(parts) == 15 and len(report["joints"]) == 14
    assert all(
        x.Proxy.__class__.__module__ == "JointObject" for x in doc.GearboxAssemblyJoints.Group
    )
    assert all(x["connected_to_ground"] for x in report["components"])
    count = sum(len(x.Shape.Solids) for x in parts)
    volume = sum(x.Shape.Volume for x in parts)
    assert count == 26 and all(x.Shape.isValid() for x in parts)
    sun = doc.getObject("SunGearLink")
    planets = [doc.getObject(f"Planet{i + 1}Link") for i in range(3)]
    full_ring = doc.getObject("FullRingGear").Shape
    samples = []
    for angle in range(0, 1441, 120):
        set_angle(engine, doc, angle)
        actual = engine.inspect_assembly(doc.Name, "GearboxAssembly")
        expected = {x["joint"]: x["position"] for x in joint_positions(angle)}
        for joint in actual["joints"]:
            if joint["name"] in expected:
                error = (joint["position"] - expected[joint["name"]] + 180) % 360 - 180
                assert abs(error) < 1e-5
        overlaps = [
            {
                "sun_mm3": sun.Shape.common(planet.Shape).Volume,
                "ring_mm3": full_ring.common(planet.Shape).Volume,
            }
            for planet in planets
        ]
        assert all(x.Shape.isValid() for x in parts)
        assert sum(len(x.Shape.Solids) for x in parts) == count
        assert math.isclose(sum(x.Shape.Volume for x in parts), volume, rel_tol=1e-9)
        for item in overlaps:
            assert item["sun_mm3"] < 1e-6 and item["ring_mm3"] < 1e-6, (angle, overlaps)
        samples.append({"input_degrees": angle, "gear_intersections": overlaps})
    set_angle(engine, doc, 180)
    before_undo = engine.inspect_assembly(doc.Name, "GearboxAssembly")
    set_angle(engine, doc, 270)
    engine.undo_document(doc.Name)
    assert (
        engine.inspect_assembly(doc.Name, "GearboxAssembly")["components"]
        == before_undo["components"]
    )
    engine.export_model(doc.Name, [x.Name for x in parts], "PlanetaryGearbox-Movable.step")
    exported = Part.read(str(workspace / "PlanetaryGearbox-Movable.step"))
    assert exported.isValid() and len(exported.Solids) == count
    assert math.isclose(exported.Volume, volume, rel_tol=1e-6)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
    result = {
        "passed": True,
        "components": len(parts),
        "joints": len(report["joints"]),
        "solid_count": count,
        "volume_mm3": volume,
        "samples": samples,
        "undo": True,
        "step_solids": len(exported.Solids),
        "source_sha256": before_hash,
        "source_unchanged": True,
        "scope": "Sampled kinematic gear clearance; no continuous collision, contact, strength or dynamics validation",
    }
    (workspace / "motion-verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    App.closeDocument(doc.Name)


def smoke_player(workspace):
    import sys

    import FreeCAD as App
    from PySide import QtCore

    workspace = Path(workspace).resolve()
    macro = workspace / "PlayPlanetary.FCMacro"
    sys.modules.pop("planetary_motion_controls", None)
    namespace = {"__file__": str(macro)}
    exec(compile(macro.read_text(encoding="utf-8"), str(macro), "exec"), namespace)
    import codex_freecad
    from codex_freecad.engine import Engine

    assert Path(codex_freecad.__file__).resolve().is_relative_to(workspace / "native")
    panel = namespace["_planetary_panel"]
    doc = App.ActiveDocument
    engine = Engine(workspace, gui=True)
    panel.slider.setValue(180)
    assert math.isclose(
        abs(engine.inspect_assembly(doc.Name, "GearboxAssembly")["joints"][0]["position"]),
        180,
        abs_tol=1e-6,
    )
    panel.play.setChecked(True)
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(1200, loop.quit)
    loop.exec_()
    panel.play.setChecked(False)
    assert panel.slider.value() > 180
    panel.reset()
    assert panel.slider.value() == 0
    assert math.isclose(
        engine.inspect_assembly(doc.Name, "GearboxAssembly")["joints"][0]["position"],
        0,
        abs_tol=1e-6,
    )
    panel.close()
    assert not panel.timer.isActive()
    (workspace / "player-verification.json").write_text(
        json.dumps(
            {
                "passed": True,
                "slider": True,
                "play_pause": True,
                "reset": True,
                "closed_timer_stopped": True,
                "portable_native_modules": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    App.closeDocument(doc.Name)
