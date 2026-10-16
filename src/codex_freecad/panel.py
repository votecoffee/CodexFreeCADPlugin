"""Stable native UI entry points; dock implementation belongs to a reloadable extension."""

from pathlib import Path

from .engine import CadError
from .extension_runtime import get_registry, peek_registry


def implementation():
    module = get_registry().active.modules.get("cad_panel")
    if module is None:
        raise CadError("The installed cad_panel extension is unavailable")
    return module


def show(workspace):
    return implementation().show(workspace)


def shutdown():
    registry = peek_registry()
    if registry is not None and "cad_panel" in registry.active.modules:
        registry.active.modules["cad_panel"].shutdown()


def detach_for_reload():
    state = implementation().capture_state()
    if state is not None:
        shutdown()
    return state


def restore_after_reload(state):
    implementation().restore_state(state)


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
        Gui.getMainWindow().addToolBar(toolbar)
    toolbar.clear()
    action = toolbar.addAction("Codex CAD")
    action.triggered.connect(lambda: show(toolbar.property("CadWorkspace")))
    toolbar.setProperty("CadWorkspace", root)
    return toolbar
