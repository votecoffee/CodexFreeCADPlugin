"""Isolated simple mechanism for panel and real pointer-interaction verification."""

import json
import traceback
from pathlib import Path


def verify_panel(dock, engine, doc):
    """Direct Qt/model checks for the opt-in GUI smoke test; no pointer automation."""
    import FreeCADGui as Gui
    from PySide import QtCore

    checks = []
    dock.joint.setCurrentIndex(dock.joint.findData("Shoulder"))
    dock.follower.setCurrentIndex(dock.follower.findData("Extension"))
    dock.ratio.setValue(0.15)
    dock.offset.setValue(2)
    dock.edit_coupling(clear=False)
    dock.position.setValue(60)
    dock.apply_position()
    data = engine.inspect_assembly(doc.Name, "ArmAssembly")
    assert abs(data["joints"][0]["coordinate"] - 60) < 1e-5
    assert abs(data["joints"][1]["coordinate"] - 11) < 1e-5
    checks.append("panel coupling creation and forward pose")
    dock.undo()
    dock.edit_coupling(clear=True)
    assert not engine.inspect_assembly(doc.Name, "ArmAssembly")["couplings"]
    dock.edit_coupling(clear=False)
    checks.append("panel Undo, clear and restore coupling")

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.ArmLink)
    dock.inspect_source()
    item = next(
        dock.properties.topLevelItem(i)
        for i in range(dock.properties.topLevelItemCount())
        if dock.properties.topLevelItem(i).text(0) == "Length"
    )
    assert item.data(0, QtCore.Qt.UserRole) == "App::PropertyLength"
    item.setText(1, "41 mm")
    assert abs(doc.Arm.Length.Value - 41) < 1e-6
    assert abs(doc.ArmLink.Shape.Volume - 41 * 6 * 6) < 1e-6
    dock.undo()
    assert abs(doc.Arm.Length.Value - 40) < 1e-6
    checks.append("linked source parameter edit, recompute and Undo")

    Gui.Selection.clearSelection()
    dock.check_current()
    assert dock.last_report["pair_count"] == 3
    dock.start.setValue(0)
    dock.end.setValue(60)
    dock.steps.setValue(3)
    before = engine.revision(doc)
    dock.check_range()
    assert engine.revision(doc) == before
    assert len(dock.last_report["frames"]) == 3
    assert abs(dock.last_report["frames"][-1]["coordinates"]["Extension"] - 11) < 1e-6
    dock.frames.setCurrentIndex(1)
    dock.move_frame()
    assert abs(doc.Shoulder.CadMotionCoordinate - 30) < 1e-6
    dock.frames.setCurrentIndex(2)
    dock.move_frame()
    assert abs(doc.Shoulder.CadMotionCoordinate - 60) < 1e-6
    checks.append("current-pose check, copy-based sampling and sample navigation")

    dock.disconnect_bridge()
    assert dock.connection.text().startswith("Chat disconnected")
    dock.connect_bridge()
    assert dock.connection.text() == "Live chat connected"
    checks.append("disconnect and reconnect local chat bridge")
    dock.position.setValue(0)
    dock.apply_position()
    dock.drag_button.setChecked(True)
    assert dock.drag is not None
    dock.drag_button.setChecked(False)
    assert dock.drag is None
    checks.append("Coin drag callback registration and cleanup; physical drag pending")
    from codex_freecad import bridge, panel

    credentials = bridge._bridge.state_file.read_bytes()
    old_bridge = bridge._bridge
    old_revision = engine.revision(doc)
    source = Path(engine.registry.directories[0]) / "smoke" / "__init__.py"
    source.write_text("def ping(engine, doc, args):\n    return {'version': 2}\n", encoding="utf-8")
    result = engine.reload_extensions()
    assert result["reloaded"] and result["panel_rebuilt"]
    dock = panel.show(engine.workspace.root)
    assert not dock.play.isChecked() and not dock.timer.isActive()
    assert dock.document.currentData() == doc.Name and dock.joint.currentData() == "Shoulder"
    assert bridge._bridge is old_bridge and bridge._bridge.state_file.read_bytes() == credentials
    assert engine.revision(doc) == old_revision
    assert engine.run_query(doc.Name, "smoke.ping", {})["result"]["version"] == 2
    checks.append(
        "native dock rebuilt after extension update; bridge/token, document, pose and selectors preserved"
    )
    return dock, checks


def boot(workspace, run):
    import FreeCAD as App
    import FreeCADGui as Gui
    from movable_arm import build
    from PySide import QtCore

    from codex_freecad import bridge, panel
    from codex_freecad.engine import Engine

    global dock, engine, timer
    run = Path(run)

    class Client:
        def call(self, method, **params):
            return engine.call(method, params)

    def finish():
        panel.shutdown()
        bridge.stop()
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        Gui.getMainWindow().close()

    try:
        extension = run / "extensions/smoke"
        extension.mkdir(parents=True)
        (extension / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "smoke",
                    "version": "1.0.0",
                    "api_version": 1,
                    "description": "Isolated panel reload check",
                    "ui": False,
                    "capabilities": {
                        "ping": {
                            "kind": "query",
                            "description": "Native test version",
                            "handler": "ping",
                            "parameters": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {},
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (extension / "__init__.py").write_text(
            "def ping(engine, doc, args):\n    return {'version': 1}\n", encoding="utf-8"
        )
        engine = Engine(workspace, gui=True, extension_dirs=[run / "extensions"])
        build(Client())
        engine.apply_operations(
            "MovableArm",
            [
                {
                    "op": "set_joint_coupling",
                    "assembly": "ArmAssembly",
                    "joint": "Extension",
                    "driver": "Shoulder",
                    "ratio": 0.15,
                    "offset": 2,
                },
                {
                    "op": "set_joint_positions",
                    "assembly": "ArmAssembly",
                    "positions": [{"joint": "Shoulder", "position": 0}],
                },
            ],
        )
        doc = App.ActiveDocument
        doc.Base.ViewObject.ShapeColor = (0.3, 0.35, 0.4)
        doc.Arm.ViewObject.ShapeColor = (0.1, 0.45, 0.8)
        doc.Tool.ViewObject.ShapeColor = (0.95, 0.55, 0.15)
        bridge.start(workspace, str(Path(workspace) / ".codex-freecad-live.json"))
        panel.install_command(workspace)
        dock = panel.show(workspace)
        dock.tabs.setCurrentIndex(1)
        dock, checks = verify_panel(dock, engine, doc)
        dock.drag_button.setChecked(True)
        assert dock.drag is not None
        dock.position.setValue(60)
        dock.apply_position()
        data = engine.inspect_assembly("MovableArm", "ArmAssembly")
        assert abs(data["joints"][0]["coordinate"] - 60) < 1e-5
        assert abs(data["joints"][1]["coordinate"] - 11) < 1e-5
        dock.position.setValue(0)
        dock.apply_position()
        view = Gui.activeDocument().activeView()
        view.setCameraType("Orthographic")
        view.viewTop()
        view.fitAll()
        Gui.getMainWindow().resize(1400, 950)
        Gui.getMainWindow().setWindowTitle("Codex CAD panel verification")

        def observe():
            data = engine.inspect_assembly("MovableArm", "ArmAssembly")
            data["pending_edit"] = App.getActiveTransaction() is not None
            (run / "state.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            if (run / "stop.flag").exists():
                timer.stop()
                finish()

        timer = QtCore.QTimer()
        timer.timeout.connect(observe)
        timer.start(300)
        (run / "ready.json").write_text(
            json.dumps(
                {
                    "ready": True,
                    "workspace": str(workspace),
                    "checks": checks,
                    "physical_drag_verified": False,
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        (run / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        finish()
