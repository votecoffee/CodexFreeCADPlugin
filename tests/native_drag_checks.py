"""Native controller checks without FreeCADGui, input events or a desktop window."""

import json
import math
from pathlib import Path


def verify(workspace):
    import FreeCAD as App
    from movable_arm import build

    from codex_freecad import assemblies, motion
    from codex_freecad.engine import CadError, Engine
    from codex_freecad.viewport import JointDrag

    engine = Engine(workspace)

    class Client:
        def call(self, method, **params):
            return engine.call(method, params)

    build(Client())
    doc = App.ActiveDocument
    asm = doc.ArmAssembly
    engine.apply_operations(
        doc.Name,
        [
            {
                "op": "set_joint_coupling",
                "assembly": asm.Name,
                "joint": "Extension",
                "driver": "Shoulder",
                "ratio": 0.1,
                "offset": 2,
            },
            {
                "op": "set_joint_positions",
                "assembly": asm.Name,
                "positions": [{"joint": "Shoulder", "position": 0}],
            },
        ],
    )
    controller = JointDrag.__new__(JointDrag)
    controller.engine = engine
    controller.notify = lambda *_args: None
    controller.changed = lambda: None
    frame = App.Placement()
    # A plane hit maps to the expected radial direction, independent of depth.
    controller.ray = lambda _pos: (App.Vector(3, 4, 100), App.Vector(0, 0, -1))
    assert (
        controller.cursor_coordinate((0, 0), frame, "Revolute") - App.Vector(0.6, 0.8, 0)
    ).Length < 1e-9
    controller.ray = lambda _pos: (App.Vector(3, 0, 7), App.Vector(-1, 0, 0))
    assert abs(controller.cursor_coordinate((0, 0), frame, "Slider") - 7) < 1e-9
    for kind, origin, direction in (
        ("Revolute", App.Vector(0, 0, 1), App.Vector(1, 0, 0)),
        ("Revolute", App.Vector(0, 0, 1), App.Vector(0, 0, -1)),
        ("Slider", App.Vector(0, 0, 1), App.Vector(0, 0, -1)),
    ):
        controller.ray = lambda _pos, o=origin, d=direction: (o, d)
        try:
            controller.cursor_coordinate((0, 0), frame, kind)
        except CadError:
            pass
        else:
            raise AssertionError("Singular camera alignment was accepted")
    assert controller.picked_component(doc, asm, {"ParentSubName": "ArmLink.Face1"}) == doc.ArmLink
    assert controller.picked_component(doc, asm, {"Object": "Arm"}) == doc.ArmLink
    assert controller.picked_component(doc, asm, {"Object": "NotInAssembly"}) is None
    assert controller.movable_joint(doc, asm, doc.ArmLink)[0] == doc.Shoulder
    assert controller.movable_joint(doc, asm, doc.ToolLink)[0] == doc.Extension
    assert controller.movable_joint(doc, asm, doc.BaseLink) is None

    def state(joint, value, cursor):
        return {
            "doc": doc,
            "asm": asm,
            "joint": joint,
            "frame": frame,
            "value": value,
            "cursor": cursor,
            "delta": 0,
        }

    def values():
        return [motion.coordinate(engine, doc, asm, x) for x in (doc.Shoulder, doc.Extension)]

    # Controller movement and its coupled follower are one Undo transaction.
    controller.active = state(doc.Shoulder, 0, App.Vector(1, 0, 0))
    controller.cursor_coordinate = lambda *_args: App.Vector(0, 1, 0)
    doc.openTransaction("Controller verification")
    before_undo = doc.UndoCount
    controller.move((0, 0))
    assert all(abs(a - b) < 1e-6 for a, b in zip(values(), [90, 11], strict=True))
    controller.finish()
    assert doc.UndoCount == before_undo + 1
    engine.undo_document(doc.Name)
    assert all(abs(a - b) < 1e-6 for a, b in zip(values(), [0, 2], strict=True))

    controller.active = state(doc.Extension, 2, 0)
    controller.cursor_coordinate = lambda *_args: 6
    doc.openTransaction("Inverse slider drag")
    controller.move((0, 0))
    assert all(abs(a - b) < 1e-6 for a, b in zip(values(), [60, 8], strict=True))
    controller.finish(cancel=True)
    assert all(abs(a - b) < 1e-6 for a, b in zip(values(), [0, 2], strict=True))
    assert not doc.HasPendingTransaction

    # An ongoing drag must survive unrelated rejected writes, Undo and save.
    before = engine.revision(doc)
    doc.openTransaction("Pending user edit")
    for operation in (
        lambda: engine.reload_extensions(),
        lambda: engine.apply_operations(
            doc.Name, [{"op": "set_property", "object": "Arm", "property": "Length", "value": 50}]
        ),
        lambda: engine.undo_document(doc.Name),
        lambda: engine.save_document(doc.Name, "Pending.FCStd"),
        lambda: engine.export_model(doc.Name, ["ArmLink"], "Pending.step"),
        lambda: engine.sample_motion(
            doc.Name, asm.Name, "Shoulder", 0, 30, 2, ["ArmLink", "ToolLink"]
        ),
    ):
        try:
            operation()
        except CadError as exc:
            assert "current document edit" in str(exc)
        else:
            raise AssertionError("Write/read-copy accepted a pending edit")
        assert App.getActiveTransaction()[0] == "Pending user edit"
    engine.finish_transaction(doc, cancel=True)
    assert engine.revision(doc) == before
    assert not (Path(workspace) / "Pending.FCStd").exists()
    assert not (Path(workspace) / "Pending.step").exists()
    assert App.getActiveTransaction() is None
    for cancel in (False, True):
        controller.active = state(doc.Shoulder, 0, App.Vector(1, 0, 0))
        doc.openTransaction("Click without movement")
        controller.finish(cancel=cancel)
        assert App.getActiveTransaction() is None

    # Angular deltas cross the signed half-turn without jumping backwards.
    engine.apply_operations(
        doc.Name,
        [
            {"op": "set_joint_limits", "assembly": asm.Name, "joint": "Shoulder"},
            {"op": "set_joint_limits", "assembly": asm.Name, "joint": "Extension"},
        ],
    )

    def radial(degrees):
        return App.Vector(math.cos(math.radians(degrees)), math.sin(math.radians(degrees)), 0)

    assemblies.position(engine, doc, asm, [{"joint": "Shoulder", "position": 170}])
    controller.active = state(doc.Shoulder, 170, radial(170))
    controller.cursor_coordinate = lambda *_args: radial(-170)
    doc.openTransaction("Cross half turn")
    controller.move((0, 0))
    assert abs(values()[0] - 190) < 1e-6
    controller.finish(cancel=True)

    # The panel's editable-field policy uses native string editor flags.
    assert not {"ReadOnly", "Hidden"}.intersection(doc.Arm.getEditorMode("Length"))
    assert "ReadOnly" in doc.Shoulder.getEditorMode("CadMotionCoordinate")
    (Path(workspace) / "controller-checks.json").write_text(
        json.dumps({"passed": True, "desktop_input": False})
    )
    App.closeDocument(doc.Name)
