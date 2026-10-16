"""Joint-aware Coin viewport dragging, using the same pose engine as MCP."""

import math
import re

from . import assemblies, motion
from .engine import CadError


class JointDrag:
    def __init__(self, engine, document, assembly, notify, changed):
        import FreeCADGui as Gui
        from pivy import coin

        self.engine, self.document, self.assembly = engine, document, assembly
        self.notify, self.changed = notify, changed
        self.coin = coin
        self.view = Gui.getDocument(document).activeView()
        self.active = None
        self.callback = self.view.addEventCallbackPivy(coin.SoEvent.getClassTypeId(), self.event)

    def close(self):
        self.finish(cancel=True)
        if self.callback is not None:
            try:
                self.view.removeEventCallbackPivy(self.coin.SoEvent.getClassTypeId(), self.callback)
            except RuntimeError:
                pass  # The view may already have been closed by the user.
            self.callback = None

    def picked_component(self, doc, asm, info):
        if not info:
            return None
        names = set()
        for key in ("Object", "Component", "ParentObject", "ParentSubName"):
            value = info.get(key)
            if hasattr(value, "Name"):
                names.add(value.Name)
            elif isinstance(value, str):
                names.update(re.split(r"[^A-Za-z0-9_]+", value))
        parts = assemblies.components(asm)
        direct = [p for p in parts if p.Name in names]
        if len(direct) == 1:
            return direct[0]
        candidates = direct or [p for p in parts if p.LinkedObject.Name in names]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        if not all(key in info for key in ("x", "y", "z")):
            raise CadError("Pick a visible instance of this linked source")
        import Part

        point = Part.Vertex(self.engine.app.Vector(info["x"], info["y"], info["z"]))
        return min(candidates, key=lambda p: p.Shape.distToShape(point)[0])

    def movable_joint(self, doc, asm, part):
        incoming = {}
        for joint in assemblies.joints(asm):
            first, second = assemblies.joint_parts(self.engine, doc, asm, joint)
            if second.Name in incoming:
                raise CadError("Dragging requires a directed joint tree")
            incoming[second.Name] = (joint, first)
        visited = set()
        while part.Name in incoming:
            if part.Name in visited:
                raise CadError("Dragging requires a directed joint tree")
            visited.add(part.Name)
            joint, parent = incoming[part.Name]
            if joint.JointType in {"Revolute", "Slider"}:
                return joint, parent
            part = parent
        return None

    def ray(self, pos):
        app = self.engine.app
        point = self.view.getPoint(int(pos[0]), int(pos[1]))
        camera = self.view.getCameraNode()
        if isinstance(camera, self.coin.SoPerspectiveCamera):
            origin = app.Vector(*camera.position.getValue())
            direction = point - origin
        else:
            origin, direction = point, self.view.getViewDirection()
        return origin, direction.normalize()

    def cursor_coordinate(self, pos, frame, kind):
        origin, ray = self.ray(pos)
        axis = frame.Rotation.multVec(self.engine.app.Vector(0, 0, 1))
        dot = axis.dot(ray)
        if kind == "Revolute":
            if abs(dot) < 1e-6:
                raise CadError("View the joint axis more directly before rotating it")
            hit = origin + ray * (axis.dot(frame.Base - origin) / dot)
            vector = hit - frame.Base
            if vector.Length < 1e-6:
                raise CadError("Drag away from the joint axis")
            return vector.normalize()
        if 1 - dot * dot < 1e-6:
            raise CadError("View the slider from the side before dragging it")
        offset = origin - frame.Base
        return (axis.dot(offset) - dot * ray.dot(offset)) / (1 - dot * dot)

    def begin(self, pos):
        import FreeCADGui as Gui

        if self.active is not None:
            return True
        doc = self.engine.document(self.document)
        asm = assemblies.assembly(self.engine, doc, self.assembly)
        part = self.picked_component(doc, asm, self.view.getObjectInfo((int(pos[0]), int(pos[1]))))
        if part is None:
            return False
        if asm.isPartGrounded(part):
            self.notify("This component is grounded")
            return True
        moving = self.movable_joint(doc, asm, part)
        if moving is None:
            self.notify("This component has no movable parent joint")
            return True
        self.engine.require_idle(doc, "dragging")
        joint, parent = moving
        frame = parent.Placement * joint.Placement1
        cursor = self.cursor_coordinate(pos, frame, joint.JointType)
        self.active = {
            "doc": doc,
            "asm": asm,
            "joint": joint,
            "frame": frame,
            "cursor": cursor,
            "value": motion.coordinate(self.engine, doc, asm, joint),
            "delta": 0,
        }
        if not doc.UndoMode:
            doc.UndoMode = 1
        doc.openTransaction("Drag coupled assembly")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(part)
        self.notify("Dragging " + joint.Label + " · release to keep, Esc to cancel")
        return True

    def move(self, pos):
        state = self.active
        cursor = self.cursor_coordinate(pos, state["frame"], state["joint"].JointType)
        if state["joint"].JointType == "Revolute":
            axis = state["frame"].Rotation.multVec(self.engine.app.Vector(0, 0, 1))
            angle = math.degrees(
                math.atan2(axis.dot(state["cursor"].cross(cursor)), state["cursor"].dot(cursor))
            )
            state["delta"] += angle
            state["cursor"] = cursor
            value = state["value"] + state["delta"]
        else:
            value = state["value"] + cursor - state["cursor"]
        assemblies.position(
            self.engine,
            state["doc"],
            state["asm"],
            [{"joint": state["joint"].Name, "position": value}],
        )
        state["doc"].recompute()
        self.changed()

    def finish(self, cancel=False):
        state, self.active = self.active, None
        if state is not None:
            self.engine.finish_transaction(state["doc"], cancel)
            if cancel:
                state["doc"].recompute()
            self.notify("Drag cancelled" if cancel else "Pose updated · Undo restores the drag")
            self.changed()

    def event(self, callback):
        event = callback.getEvent()
        try:
            if (
                event.isOfType(self.coin.SoMouseButtonEvent.getClassTypeId())
                and event.getButton() == self.coin.SoMouseButtonEvent.BUTTON1
            ):
                if event.getState() == self.coin.SoButtonEvent.DOWN:
                    if self.begin(event.getPosition()):
                        callback.setHandled()
                elif self.active is not None:
                    self.finish()
                    callback.setHandled()
            elif self.active is not None and event.isOfType(
                self.coin.SoLocation2Event.getClassTypeId()
            ):
                callback.setHandled()
                self.move(event.getPosition())
            elif (
                self.active is not None
                and event.isOfType(self.coin.SoKeyboardEvent.getClassTypeId())
                and event.getKey() == self.coin.SoKeyboardEvent.ESCAPE
            ):
                self.finish(cancel=True)
                callback.setHandled()
        except Exception as exc:
            self.finish(cancel=True)
            self.notify(str(exc))
            callback.setHandled()
