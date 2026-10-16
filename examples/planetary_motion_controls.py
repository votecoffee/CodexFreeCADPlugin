"""Native FreeCAD controls for the jointed 18/18/54-tooth planetary demo."""

from pathlib import Path


def joint_positions(input_degrees):
    """Willis relation, fixed ring: carrier = sun/4; planet relative to carrier = -3*sun/4."""
    return [
        {"joint": "SunJoint", "position": input_degrees},
        {"joint": "CarrierJoint", "position": input_degrees / 4},
        *[{"joint": f"PlanetJoint{i + 1}", "position": -3 * input_degrees / 4} for i in range(3)],
    ]


def set_angle(engine, doc, angle):
    from codex_freecad.assemblies import position

    doc.openTransaction("Planetary gearbox motion")
    try:
        position(engine, doc, doc.getObject("GearboxAssembly"), joint_positions(angle))
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        doc.recompute()
        raise


def show_controls(folder):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui

    from codex_freecad.engine import Engine

    folder = Path(folder).resolve()
    doc = App.ActiveDocument
    if doc is None or doc.getObject("GearboxAssembly") is None:
        doc = App.openDocument(str(folder / "PlanetaryGearbox-Movable.FCStd"))
    engine = Engine(folder, gui=True)
    if not doc.UndoMode:
        doc.UndoMode = 1

    class MotionPanel(QtGui.QWidget):
        def __init__(self):
            super().__init__(Gui.getMainWindow(), QtCore.Qt.Tool)
            self.setWindowTitle("Planetary gearbox · motion controls")
            self.setMinimumWidth(430)
            self.busy = False
            layout = QtGui.QVBoxLayout(self)
            layout.addWidget(QtGui.QLabel("18 / 18 / 54 teeth · fixed ring · 4:1 reduction"))
            self.readout = QtGui.QLabel()
            layout.addWidget(self.readout)
            self.slider = QtGui.QSlider(QtCore.Qt.Horizontal)
            self.slider.setRange(0, 1440)
            self.slider.setSingleStep(6)
            self.slider.setPageStep(90)
            layout.addWidget(self.slider)
            row = QtGui.QHBoxLayout()
            self.play = QtGui.QPushButton("Play")
            self.play.setCheckable(True)
            self.play.toggled.connect(self.toggle_play)
            row.addWidget(self.play)
            reset = QtGui.QPushButton("Reset")
            reset.clicked.connect(self.reset)
            row.addWidget(reset)
            layout.addLayout(row)
            self.status = QtGui.QLabel(
                "Drag the slider, or press Play. Position changes support Undo."
            )
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(80)
            self.timer.timeout.connect(self.tick)
            self.slider.valueChanged.connect(self.changed)
            self.changed(0)

        def changed(self, value):
            if self.busy:
                return
            self.busy = True
            try:
                set_angle(engine, doc, value)
                self.readout.setText(
                    f"Input {value}°    Carrier {value / 4:g}°    Planet spin {-value / 2:g}°"
                )
                Gui.updateGui()
            except Exception as exc:
                self.play.setChecked(False)
                self.status.setText(str(exc))
            finally:
                self.busy = False

        def toggle_play(self, checked):
            self.play.setText("Pause" if checked else "Play")
            self.timer.start() if checked else self.timer.stop()

        def tick(self):
            if not self.busy:
                self.slider.setValue((self.slider.value() + 6) % 1440)

        def reset(self):
            self.play.setChecked(False)
            self.slider.setValue(0)

        def closeEvent(self, event):
            self.timer.stop()
            super().closeEvent(event)

    global panel
    if "panel" in globals():
        panel.close()
    panel = MotionPanel()
    panel.show()
    return panel
