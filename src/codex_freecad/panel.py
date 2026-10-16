"""FreeCAD dock panel: model inspection, coupled motion and interference checks.

Imported only by FreeCAD's GUI. Modeling calls still use the shared native engine.
"""

from pathlib import Path

from .engine import SCALAR_TYPES, CadError, Engine

_panel = None


def show(workspace):
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

    global _panel
    if _panel is not None:
        if _panel.engine.workspace.root == Path(workspace).resolve():
            _panel.show()
            _panel.raise_()
            return _panel
        _panel.close()

    class ValueEditor(QtWidgets.QStyledItemDelegate):
        def createEditor(self, parent, option, index):
            if (
                index.column() != 1
                or index.sibling(index.row(), 0).data(QtCore.Qt.UserRole) is None
            ):
                return None
            return super().createEditor(parent, option, index)

    class CadPanel(QtWidgets.QDockWidget):
        def __init__(self):
            super().__init__("Codex CAD", Gui.getMainWindow())
            self.setObjectName("CodexFreeCADPanel")
            self.setMinimumWidth(320)
            self.engine = Engine(workspace, gui=True)
            self.drag = None
            self.updating = False
            self.last_report = None
            self.inspected = None
            body = QtWidgets.QWidget()
            self.setWidget(body)
            layout = QtWidgets.QVBoxLayout(body)
            self.connection = QtWidgets.QLabel()
            self.connection.setWordWrap(True)
            self.connection.setToolTip(str(self.engine.workspace.root))
            layout.addWidget(self.connection)
            row = QtWidgets.QHBoxLayout()
            for label, callback in (
                ("Connect chat", self.connect_bridge),
                ("Disconnect", self.disconnect_bridge),
            ):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(lambda _checked=False, cb=callback: self.run(cb))
                row.addWidget(button)
            layout.addLayout(row)
            self.document = QtWidgets.QComboBox()
            self.document.setObjectName("CadDocument")
            self.document.currentIndexChanged.connect(lambda: self.run(self.load_assemblies))
            layout.addWidget(self.document)
            self.assembly = QtWidgets.QComboBox()
            self.assembly.setObjectName("CadAssembly")
            self.assembly.currentIndexChanged.connect(lambda: self.run(self.load_joints))
            layout.addWidget(self.assembly)
            self.tabs = QtWidgets.QTabWidget()
            layout.addWidget(self.tabs)
            model = QtWidgets.QWidget()
            model_layout = QtWidgets.QVBoxLayout(model)
            self.selection_label = QtWidgets.QLabel("Select a part to inspect its parameters")
            self.selection_label.setWordWrap(True)
            model_layout.addWidget(self.selection_label)
            self.properties = QtWidgets.QTreeWidget()
            self.properties.setHeaderLabels(["Parameter", "Value"])
            self.properties.setItemDelegate(ValueEditor(self.properties))
            self.properties.itemChanged.connect(self.edit_property)
            model_layout.addWidget(self.properties)
            for label, callback in (
                ("Refresh selection", self.inspect_selection),
                ("Edit linked source parameters", self.inspect_source),
                ("Undo last edit", self.undo),
            ):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(lambda _checked=False, cb=callback: self.run(cb))
                model_layout.addWidget(button)
            self.tabs.addTab(model, "Model")
            motion_tab = QtWidgets.QWidget()
            motion_layout = QtWidgets.QVBoxLayout(motion_tab)
            self.joint = QtWidgets.QComboBox()
            self.joint.setObjectName("CadJoint")
            self.joint.currentIndexChanged.connect(lambda: self.run(self.joint_changed))
            motion_layout.addWidget(self.joint)
            self.position = QtWidgets.QDoubleSpinBox()
            self.position.setObjectName("CadPosition")
            self.position.setRange(-1e6, 1e6)
            self.position.setDecimals(3)
            motion_layout.addWidget(self.position)
            self.apply = QtWidgets.QPushButton("Apply position")
            self.apply.clicked.connect(lambda: self.run(self.apply_position))
            motion_layout.addWidget(self.apply)
            self.drag_button = QtWidgets.QPushButton("Drag parts in viewport")
            self.drag_button.setObjectName("CadDrag")
            self.drag_button.setCheckable(True)
            self.drag_button.toggled.connect(
                lambda enabled: self.run(lambda: self.enable_drag(enabled))
            )
            motion_layout.addWidget(self.drag_button)
            self.play = QtWidgets.QPushButton("Play")
            self.play.setCheckable(True)
            self.play.toggled.connect(self.toggle_play)
            motion_layout.addWidget(self.play)
            self.increment = QtWidgets.QDoubleSpinBox()
            self.increment.setRange(-1000, 1000)
            self.increment.setValue(3)
            self.increment.setPrefix("Step per frame: ")
            motion_layout.addWidget(self.increment)
            self.coupling_info = QtWidgets.QLabel()
            self.coupling_info.setWordWrap(True)
            motion_layout.addWidget(self.coupling_info)
            coupling = QtWidgets.QGroupBox("Couple another joint to the selected joint")
            form = QtWidgets.QFormLayout(coupling)
            self.follower = QtWidgets.QComboBox()
            self.follower.setObjectName("CadFollower")
            form.addRow("Follower", self.follower)
            self.ratio = QtWidgets.QDoubleSpinBox()
            self.ratio.setRange(-1e6, 1e6)
            self.ratio.setDecimals(6)
            self.ratio.setValue(1)
            self.ratio.setToolTip("Follower units per driver unit (degrees or mm)")
            form.addRow("Ratio", self.ratio)
            self.offset = QtWidgets.QDoubleSpinBox()
            self.offset.setRange(-1e6, 1e6)
            self.offset.setDecimals(6)
            form.addRow("Offset", self.offset)
            for label, callback in (
                ("Set coupling", lambda: self.edit_coupling(clear=False)),
                ("Clear follower coupling", lambda: self.edit_coupling(clear=True)),
            ):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(lambda _checked=False, cb=callback: self.run(cb))
                form.addRow(button)
            motion_layout.addWidget(coupling)
            motion_layout.addStretch()
            self.tabs.addTab(motion_tab, "Motion")
            checks = QtWidgets.QWidget()
            checks_layout = QtWidgets.QVBoxLayout(checks)
            self.clearance = QtWidgets.QDoubleSpinBox()
            self.clearance.setRange(0, 1000)
            self.clearance.setSuffix(" mm clearance")
            checks_layout.addWidget(self.clearance)
            hint = QtWidgets.QLabel(
                "Select two or more components to check them; otherwise check the whole assembly."
            )
            hint.setWordWrap(True)
            checks_layout.addWidget(hint)
            check_now = QtWidgets.QPushButton("Check current pose")
            check_now.setObjectName("CadCheck")
            check_now.clicked.connect(lambda: self.run(self.check_current))
            checks_layout.addWidget(check_now)
            range_row = QtWidgets.QHBoxLayout()
            self.start = QtWidgets.QDoubleSpinBox()
            self.end = QtWidgets.QDoubleSpinBox()
            for widget in (self.start, self.end):
                widget.setRange(-1e6, 1e6)
            self.end.setValue(360)
            range_row.addWidget(self.start)
            range_row.addWidget(self.end)
            checks_layout.addLayout(range_row)
            self.steps = QtWidgets.QSpinBox()
            self.steps.setRange(2, 101)
            self.steps.setValue(13)
            self.steps.setSuffix(" samples")
            checks_layout.addWidget(self.steps)
            sample_button = QtWidgets.QPushButton("Check motion range")
            sample_button.clicked.connect(lambda: self.run(self.check_range))
            checks_layout.addWidget(sample_button)
            self.frames = QtWidgets.QComboBox()
            self.frames.currentIndexChanged.connect(self.show_frame)
            checks_layout.addWidget(self.frames)
            move_frame = QtWidgets.QPushButton("Move to selected sample")
            move_frame.clicked.connect(lambda: self.run(self.move_frame))
            checks_layout.addWidget(move_frame)
            self.pairs = QtWidgets.QTreeWidget()
            self.pairs.setHeaderLabels(["Parts / status", "Overlap mm³ / gap mm"])
            self.pairs.itemSelectionChanged.connect(self.highlight_pair)
            checks_layout.addWidget(self.pairs)
            self.tabs.addTab(checks, "Checks")
            self.status = QtWidgets.QLabel(
                "Select an assembly. Use Motion to drag parts or drive a joint."
            )
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(100)
            self.timer.timeout.connect(lambda: self.run(self.tick))
            self.refresh_timer = QtCore.QTimer(self)
            self.refresh_timer.setInterval(1000)
            self.refresh_timer.timeout.connect(lambda: self.run(self.refresh_documents))
            self.refresh_timer.start()
            Gui.Selection.addObserver(self)
            self.refresh_documents()

        def run(self, callback):
            try:
                return callback()
            except Exception as exc:
                self.play.setChecked(False)
                if self.drag is None:
                    self.drag_button.blockSignals(True)
                    self.drag_button.setChecked(False)
                    self.drag_button.blockSignals(False)
                self.status.setText(str(exc))
                return None

        def current(self):
            doc = self.engine.document(self.document.currentData())
            return doc, self.engine.obj(doc, self.assembly.currentData())

        def refresh_documents(self):
            from . import bridge

            connected = (
                bridge._bridge is not None
                and not bridge._bridge.stopped
                and bridge._bridge.engine.workspace.root == self.engine.workspace.root
            )
            self.connection.setText(
                "Live chat connected" if connected else "Chat disconnected · local tools available"
            )
            docs = self.engine.list_documents()
            names = [x["name"] for x in docs]
            if names != [self.document.itemData(i) for i in range(self.document.count())]:
                current = self.document.currentData()
                self.document.blockSignals(True)
                self.document.clear()
                for item in docs:
                    self.document.addItem(item["label"], item["name"])
                active = self.engine.app.ActiveDocument
                target = current if current in names else (active.Name if active else None)
                self.document.setCurrentIndex(max(0, self.document.findData(target)))
                self.document.blockSignals(False)
                self.load_assemblies()
            elif self.document.currentData():
                doc = self.engine.document(self.document.currentData())
                assemblies = [x.Name for x in doc.Objects if x.TypeId == "Assembly::AssemblyObject"]
                if assemblies != [self.assembly.itemData(i) for i in range(self.assembly.count())]:
                    self.load_assemblies()

        def load_assemblies(self, _index=None):
            self.stop_motion()
            self.last_report = None
            self.frames.clear()
            self.pairs.clear()
            current = self.assembly.currentData()
            self.assembly.blockSignals(True)
            self.assembly.clear()
            name = self.document.currentData()
            if name:
                for obj in self.engine.document(name).Objects:
                    if obj.TypeId == "Assembly::AssemblyObject":
                        self.assembly.addItem(obj.Label, obj.Name)
            self.assembly.setCurrentIndex(max(0, self.assembly.findData(current)))
            self.assembly.blockSignals(False)
            self.load_joints()
            self.inspect_selection()

        def load_joints(self, _index=None):
            from . import assemblies

            self.stop_motion()
            self.last_report = None
            self.frames.clear()
            self.pairs.clear()
            current = self.joint.currentData()
            self.joint.blockSignals(True)
            self.joint.clear()
            self.follower.clear()
            if self.assembly.currentData():
                doc, asm = self.current()
                for joint in assemblies.joints(asm):
                    if joint.JointType in {"Revolute", "Slider"}:
                        self.joint.addItem(joint.Label, joint.Name)
                        self.follower.addItem(joint.Label, joint.Name)
            self.joint.setCurrentIndex(max(0, self.joint.findData(current)))
            self.joint.blockSignals(False)
            self.follower.setCurrentIndex(min(1, self.follower.count() - 1))
            self.read_pose()

        def joint_changed(self):
            self.play.setChecked(False)
            self.read_pose()

        def edit_coupling(self, clear):
            self.stop_motion()
            doc, asm = self.current()
            operation = {
                "op": "clear_joint_coupling" if clear else "set_joint_coupling",
                "assembly": asm.Name,
                "joint": self.follower.currentData(),
            }
            if not clear:
                operation.update(
                    driver=self.joint.currentData(),
                    ratio=self.ratio.value(),
                    offset=self.offset.value(),
                )
            self.engine.apply_operations(doc.Name, [operation], self.engine.revision(doc))
            self.read_pose()
            self.status.setText(
                "Coupling cleared; pose retained"
                if clear
                else "Coupling saved and pose aligned · Undo is available"
            )

        def read_pose(self, _index=None):
            from . import motion

            if not self.joint.currentData():
                return
            doc, asm = self.current()
            joint = self.engine.obj(doc, self.joint.currentData())
            self.position.setSuffix(" °" if joint.JointType == "Revolute" else " mm")
            self.position.setValue(motion.coordinate(self.engine, doc, asm, joint))
            rules = motion.validate(asm)
            self.coupling_info.setText(
                "\n".join(
                    f"{r['joint']} = {r['ratio']:g} × {r['driver']} + {r['offset']:g}"
                    for r in rules
                )
                or "No motion couplings saved in this assembly"
            )

        def pose(self, joint, value):
            from .assemblies import position

            doc, asm = self.current()
            self.engine.require_idle(doc, "changing a joint")
            if not doc.UndoMode:
                doc.UndoMode = 1
            doc.openTransaction("Codex CAD joint pose")
            try:
                position(self.engine, doc, asm, [{"joint": joint, "position": value}])
                doc.recompute()
                self.engine.finish_transaction(doc)
            except Exception:
                self.engine.finish_transaction(doc, cancel=True)
                doc.recompute()
                raise
            self.read_pose()

        def apply_position(self):
            self.pose(self.joint.currentData(), self.position.value())
            self.status.setText("Pose updated · all stored couplings applied")

        def enable_drag(self, enabled):
            from .viewport import JointDrag

            if self.drag:
                self.drag.close()
                self.drag = None
            if enabled:
                self.play.setChecked(False)
                if Gui.Control.activeDialog():
                    raise CadError("Finish the active task before enabling dragging")
                doc, asm = self.current()
                self.engine.app.setActiveDocument(doc.Name)
                Gui.getDocument(doc.Name).resetEdit()
                self.drag = JointDrag(
                    self.engine, doc.Name, asm.Name, self.status.setText, self.read_pose
                )
                self.status.setText(
                    "Drag a moving part in the viewport. Release to keep; Esc cancels. Grounded parts stay fixed."
                )

        def toggle_play(self, enabled):
            self.play.setText("Pause" if enabled else "Play")
            if enabled:
                self.drag_button.setChecked(False)
                self.timer.start()
            else:
                self.timer.stop()

        def tick(self):
            self.pose(self.joint.currentData(), self.position.value() + self.increment.value())

        def stop_motion(self):
            self.play.setChecked(False)
            self.drag_button.setChecked(False)

        def selected_objects(self):
            doc, asm = self.current()
            from .assemblies import components

            names = {x.Name for x in components(asm)}
            selected = [
                x.Name
                for x in Gui.Selection.getSelection()
                if x.Document == doc and x.Name in names
            ]
            return selected if len(selected) >= 2 else sorted(names)

        def check_current(self):
            self.stop_motion()
            doc, asm = self.current()
            self.last_report = self.engine.check_interference(
                doc.Name, self.selected_objects(), self.clearance.value()
            )
            self.frames.clear()
            self.display_pairs(self.last_report)

        def check_range(self):
            self.stop_motion()
            doc, asm = self.current()
            self.status.setText("Checking discrete poses on a hidden model copy…")
            self.last_report = self.engine.sample_motion(
                doc.Name,
                asm.Name,
                self.joint.currentData(),
                self.start.value(),
                self.end.value(),
                self.steps.value(),
                self.selected_objects(),
                self.clearance.value(),
            )
            self.frames.clear()
            worst = 0
            for frame in self.last_report["frames"]:
                self.frames.addItem(
                    f"{frame['position']:g} · {frame['counts']['overlap']} overlaps", frame["index"]
                )
                if sum(p["overlap_mm3"] for p in frame["pairs"]) > sum(
                    p["overlap_mm3"] for p in self.last_report["frames"][worst]["pairs"]
                ):
                    worst = frame["index"]
            self.frames.setCurrentIndex(worst)
            self.show_frame(worst)

        def display_pairs(self, report):
            self.pairs.clear()
            for pair in report["pairs"]:
                item = QtWidgets.QTreeWidgetItem(
                    [
                        f"{pair['object_a']} / {pair['object_b']} · {pair['status']}",
                        f"{pair['overlap_mm3']:.6g} / {pair['distance_mm']:.6g}",
                    ]
                )
                item.setData(0, QtCore.Qt.UserRole, pair)
                self.pairs.addTopLevelItem(item)
            counts = report["counts"]
            self.status.setText(
                f"{counts['overlap']} overlaps · {counts['contact']} contacts · {counts['insufficient_clearance']} below clearance. Select a row to highlight parts."
            )

        def show_frame(self, index):
            if (
                self.last_report
                and "frames" in self.last_report
                and 0 <= index < len(self.last_report["frames"])
            ):
                self.display_pairs(self.last_report["frames"][index])

        def move_frame(self):
            if self.last_report and "frames" in self.last_report:
                if self.last_report.get("revision") != self.engine.revision(self.current()[0]):
                    raise CadError("Model changed since sampling; check the motion range again")
                self.pose(
                    self.last_report["joint"],
                    self.last_report["frames"][self.frames.currentIndex()]["position"],
                )
                self.last_report["revision"] = self.engine.revision(self.current()[0])

        def highlight_pair(self):
            selected = self.pairs.selectedItems()
            if selected:
                pair = selected[0].data(0, QtCore.Qt.UserRole)
                Gui.Selection.clearSelection()
                for name in (pair["object_a"], pair["object_b"]):
                    Gui.Selection.addSelection(self.document.currentData(), name)

        def inspect_selection(self):
            if self.updating:
                return
            self.updating = True
            try:
                self.properties.clear()
                self.inspected = None
                selected = Gui.Selection.getSelection()
                if not selected:
                    self.selection_label.setText(
                        "Select a part or its source feature to edit parameters"
                    )
                    return
                obj = selected[0]
                if obj.Document.Name != self.document.currentData():
                    self.selection_label.setText("Select a part in the panel's document")
                    return
                self.selection_label.setText(obj.Label + " · " + obj.Name)
                self.inspected = (obj.Document.Name, obj.Name, self.engine.revision(obj.Document))
                for name, prop in self.engine.properties(obj).items():
                    if prop.get("type") not in SCALAR_TYPES:
                        continue
                    value = prop.get("value")
                    text = (
                        value.get("quantity", str(value)) if isinstance(value, dict) else str(value)
                    )
                    item = QtWidgets.QTreeWidgetItem([name, text])
                    editable = name == "Label" or (
                        prop["type"] != "App::PropertyString"
                        and "CadAssemblyRole" not in obj.PropertiesList
                        and "CadPatternKind" not in obj.PropertiesList
                    )
                    editable = editable and not {"ReadOnly", "Hidden"}.intersection(
                        obj.getEditorMode(name)
                    )
                    editable = editable and not any(
                        path == name or path.startswith(name + ".")
                        for path, _ in obj.ExpressionEngine
                    )
                    item.setData(0, QtCore.Qt.UserRole, prop["type"] if editable else None)
                    if editable:
                        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
                    self.properties.addTopLevelItem(item)
            finally:
                self.updating = False

        def inspect_source(self):
            selected = Gui.Selection.getSelection()
            if not selected:
                raise CadError("Select a linked component first")
            obj = selected[0]
            if obj.TypeId != "App::Link":
                raise CadError("Select a linked component to inspect its source")
            source = obj.LinkedObject
            if source is None or source.Document.Name != self.document.currentData():
                raise CadError("The source must belong to the panel's document")
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(source)
            self.inspect_selection()

        def edit_property(self, item, column):
            if self.updating or column != 1 or not self.inspected:
                return

            def edit():
                kind = item.data(0, QtCore.Qt.UserRole)
                if kind is None:
                    raise CadError("This parameter is managed by a dedicated modeling operation")
                value = item.text(1)
                if kind == "App::PropertyBool":
                    if value.lower() not in {"true", "false"}:
                        raise CadError("Enter True or False")
                    value = value.lower() == "true"
                elif kind == "App::PropertyInteger":
                    value = int(value)
                elif kind != "App::PropertyString":
                    try:
                        value = float(value)
                    except ValueError:
                        pass  # Unit-bearing values go through native quantity parsing.
                document, name, revision = self.inspected
                self.engine.apply_operations(
                    document,
                    [
                        {
                            "op": "set_property",
                            "object": name,
                            "property": item.text(0),
                            "value": value,
                        }
                    ],
                    revision,
                )
                self.status.setText("Parameter updated · Undo is available")

            self.run(edit)
            self.inspect_selection()

        def addSelection(self, *_args):
            if self.drag is None or self.drag.active is None:
                self.inspect_selection()

        def removeSelection(self, *_args):
            self.addSelection()

        def clearSelection(self, *_args):
            self.addSelection()

        def undo(self):
            self.stop_motion()
            self.engine.undo_document(self.document.currentData())
            self.read_pose()
            self.inspect_selection()

        def connect_bridge(self):
            from . import bridge

            bridge.start(
                self.engine.workspace.root, self.engine.workspace.root / ".codex-freecad-live.json"
            )
            self.refresh_documents()

        def disconnect_bridge(self):
            from . import bridge

            bridge.stop()
            self.refresh_documents()

        def closeEvent(self, event):
            self.stop_motion()
            self.refresh_timer.stop()
            Gui.Selection.removeObserver(self)
            global _panel
            _panel = None
            super().closeEvent(event)

    _panel = CadPanel()
    Gui.getMainWindow().addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
    _panel.show()
    return _panel


def install_command(workspace):
    import FreeCADGui as Gui
    from PySide import QtWidgets

    root = str(Path(workspace).resolve())

    class OpenPanel:
        def GetResources(self):
            return {
                "MenuText": "Codex CAD",
                "ToolTip": "Model parameters, coupled motion and interference checks",
            }

        def Activated(self):
            show(root)

    Gui.addCommand("CodexFreeCAD_OpenPanel", OpenPanel())
    toolbar = Gui.getMainWindow().findChild(QtWidgets.QToolBar, "CodexFreeCADToolbar")
    if toolbar is None:
        toolbar = QtWidgets.QToolBar("Codex CAD", Gui.getMainWindow())
        toolbar.setObjectName("CodexFreeCADToolbar")
        action = toolbar.addAction("Codex CAD")
        action.triggered.connect(lambda: show(toolbar.property("CadWorkspace")))
        Gui.getMainWindow().addToolBar(toolbar)
    toolbar.setProperty("CadWorkspace", root)
    return toolbar


def shutdown():
    if _panel is not None:
        _panel.close()
