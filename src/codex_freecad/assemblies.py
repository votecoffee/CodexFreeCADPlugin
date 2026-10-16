"""Native FreeCAD Assembly joints and bounded, transactional joint positioning.

Only FreeCAD's installed Assembly workbench proxies are persisted in documents.
No integration proxy, host dependency or executable model expression is required.
"""

import math

from .engine import CadError, encode, number

JOINT_TYPES = {"fixed": "Fixed", "revolute": "Revolute", "slider": "Slider"}
TOLERANCE = 1e-5


def mark(obj, role):
    obj.addProperty("App::PropertyString", "CadAssemblyRole", "CAD assembly")
    obj.CadAssemblyRole = role
    obj.setEditorMode("CadAssemblyRole", 1)
    return obj


def assembly(engine, doc, name):
    obj = engine.obj(doc, name)
    if obj.TypeId != "Assembly::AssemblyObject" or obj.getParentGeoFeatureGroup():
        raise CadError("Use a top-level native Assembly::AssemblyObject")
    if not obj.Placement.isIdentity():
        raise CadError("Assembly placement must be identity; position its components instead")
    return obj


def group(asm):
    groups = [x for x in asm.Group if x.TypeId == "Assembly::JointGroup"]
    if len(groups) != 1:
        raise CadError("Assembly must have exactly one native joint group")
    return groups[0]


def components(asm):
    return [x for x in asm.Group if getattr(x, "CadAssemblyRole", None) == "component"]


def component(engine, doc, asm, name):
    obj = engine.obj(doc, name)
    if obj not in components(asm) or obj.TypeId != "App::Link":
        raise CadError("Joint references must be integration-created components in this assembly")
    if obj.ElementCount or obj.LinkTransform or obj.ExpressionEngine:
        raise CadError("Assembly components require single links without placement expressions")
    return obj


def frame(engine, data):
    data = {} if data is None else data
    if not isinstance(data, dict) or set(data) - {"position", "axis", "angle"}:
        raise CadError("Joint frames accept position, axis and angle only")
    for key in ("position", "axis"):
        if key in data and (not isinstance(data[key], (list, tuple)) or len(data[key]) != 3):
            raise CadError("Joint frame position and axis require three coordinates")
    position = engine.vector(data.get("position", [0, 0, 0]))
    axis = engine.vector(data.get("axis", [0, 0, 1]))
    if axis.Length == 0:
        raise CadError("Joint frame rotation axis cannot be zero")
    return engine.app.Placement(position, engine.app.Rotation(axis, number(data.get("angle", 0))))


def joint_parts(engine, doc, asm, joint):
    parts = []
    for ref in (joint.Reference1, joint.Reference2):
        if not ref or ref[0] != asm or len(ref[1]) != 2:
            raise CadError("Joint references must use direct assembly component origins")
        names = ref[1]
        if names[0] != names[1] or not names[0].endswith(".") or names[0].count(".") != 1:
            raise CadError(
                "Nested or topological joint references are not supported for positioning"
            )
        parts.append(component(engine, doc, asm, names[0][:-1]))
    if parts[0] == parts[1]:
        raise CadError("Joint components must be different")
    if not joint.Detach1 or not joint.Detach2:
        raise CadError("Positioning requires explicit detached local joint frames")
    return parts


def joints(asm):
    return [x for x in group(asm).Group if hasattr(x, "JointType")]


def grounds(asm):
    return [x for x in group(asm).Group if hasattr(x, "ObjectToGround")]


def connected_names(engine, doc, asm):
    known = {x.ObjectToGround.Name for x in grounds(asm) if x.ObjectToGround is not None}
    edges = [joint_parts(engine, doc, asm, x) for x in joints(asm) if x.Activated]
    changed = True
    while changed:
        before = len(known)
        for a, b in edges:
            if a.Name in known or b.Name in known:
                known.update((a.Name, b.Name))
        changed = len(known) != before
    return known


def joint_value(engine, doc, asm, joint):
    first, second = joint_parts(engine, doc, asm, joint)
    a = first.Placement * joint.Placement1
    b = second.Placement * joint.Placement2
    relative = a.inverse() * b
    x = relative.Rotation.multVec(engine.app.Vector(1, 0, 0))
    value = math.degrees(math.atan2(x.y, x.x)) if joint.JointType == "Revolute" else relative.Base.z
    return value, relative


def limits(joint):
    prefix = "Angle" if joint.JointType == "Revolute" else "Length"
    return {
        "minimum": getattr(joint, prefix + "Min")
        if getattr(joint, "Enable" + prefix + "Min")
        else None,
        "maximum": getattr(joint, prefix + "Max")
        if getattr(joint, "Enable" + prefix + "Max")
        else None,
    }


def check_limit(joint, value, *, wrapped=False):
    bounds = limits(joint)
    candidates = [value]
    if wrapped and joint.JointType == "Revolute":
        candidates += [value - 360, value + 360]
    for candidate in candidates:
        if (bounds["minimum"] is None or candidate >= bounds["minimum"] - TOLERANCE) and (
            bounds["maximum"] is None or candidate <= bounds["maximum"] + TOLERANCE
        ):
            return
    raise CadError("Joint position is outside its travel limits: " + joint.Name)


def validate(engine, doc, asm, connected=True):
    if len(components(asm)) > 200 or len(group(asm).Group) > 400:
        raise CadError("Assembly is limited to 200 components and 400 joints")
    if not grounds(asm):
        raise CadError("Ground at least one component before solving or positioning")
    for fixed in grounds(asm):
        if fixed.ObjectToGround is None:
            raise CadError("Ground joint is missing its component")
        part = component(engine, doc, asm, fixed.ObjectToGround.Name)
        if not part.Placement.isSame(fixed.Placement, TOLERANCE):
            raise CadError("Grounded component moved: " + part.Name)
    connected_parts = connected_names(engine, doc, asm)
    for part in components(asm):
        component(engine, doc, asm, part.Name)
        if connected and part.Name not in connected_parts:
            raise CadError("Component is not connected to ground: " + part.Name)
    for joint in joints(asm):
        if joint.JointType not in JOINT_TYPES.values() or not joint.Activated:
            raise CadError("Solving supports active fixed, revolute and slider joints only")
        joint_parts(engine, doc, asm, joint)


def check_residuals(engine, doc, asm):
    """Native success codes alone do not prove that all constraints were satisfied."""
    for joint in joints(asm):
        value, relative = joint_value(engine, doc, asm, joint)
        if joint.JointType == "Revolute":
            position_error = relative.Base.Length
            z = relative.Rotation.multVec(engine.app.Vector(0, 0, 1))
            rotation_error = (z - engine.app.Vector(0, 0, 1)).Length
        else:
            position_error = (
                math.hypot(relative.Base.x, relative.Base.y)
                if joint.JointType == "Slider"
                else relative.Base.Length
            )
            angle = relative.Rotation.Angle
            rotation_error = abs((angle + math.pi) % (2 * math.pi) - math.pi)
        if position_error > TOLERANCE or rotation_error > TOLERANCE:
            raise CadError(
                "Assembly constraint was not satisfied: "
                + joint.Name
                + f" (position error {position_error:g} mm, rotation error {rotation_error:g})"
            )
        if joint.JointType != "Fixed":
            check_limit(joint, value, wrapped=True)


def solve(engine, doc, asm):
    validate(engine, doc, asm)
    result = asm.solve()
    if result != 0:
        raise CadError("Native assembly solver failed with code " + str(result))
    doc.recompute()
    validate(engine, doc, asm)
    check_residuals(engine, doc, asm)


def seed_tree(engine, doc, asm, values):
    """Seed large motions exactly; FreeCAD 1.0's pre-drag solver needs a nearby pose.

    Explicit positioning supports directed trees rooted at grounded components.
    Closed loops and multiple incoming joints need a different drive strategy.
    """
    known = {x.ObjectToGround.Name for x in grounds(asm)}
    pending = []
    children = set()
    for joint in joints(asm):
        first, second = joint_parts(engine, doc, asm, joint)
        if second.Name in children or second.Name in known:
            raise CadError(
                "Joint positioning requires a directed tree rooted at grounded components"
            )
        children.add(second.Name)
        value = values.get(joint.Name, joint_value(engine, doc, asm, joint)[0])
        motion = engine.app.Placement()
        if joint.JointType == "Revolute":
            motion.Rotation = engine.app.Rotation(engine.app.Vector(0, 0, 1), value)
        elif joint.JointType == "Slider":
            motion.Base = engine.app.Vector(0, 0, value)
        pending.append((joint, first, second, motion))
    while pending:
        ready = [x for x in pending if x[1].Name in known]
        if not ready:
            raise CadError(
                "Joint positioning requires a directed tree rooted at grounded components"
            )
        for joint, first, second, motion in ready:
            second.Placement = (
                first.Placement * joint.Placement1 * motion * joint.Placement2.inverse()
            )
            known.add(second.Name)
        pending = [x for x in pending if x not in ready]


def position(engine, doc, asm, items):
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise CadError("Provide between 1 and 100 joint positions")
    validate(engine, doc, asm)
    prepared = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"joint", "position"}:
            raise CadError("Each joint position requires joint and position only")
        joint = engine.obj(doc, item["joint"])
        if joint not in joints(asm) or joint.JointType not in {"Revolute", "Slider"}:
            raise CadError("Position only revolute or slider joints belonging to this assembly")
        if joint.Name in seen:
            raise CadError("Joint positions must be unique")
        seen.add(joint.Name)
        value = number(item["position"])
        if abs(value) > 1e6:
            raise CadError("Joint position magnitude is limited to 1,000,000 mm or degrees")
        check_limit(joint, value)
        motion = engine.app.Placement()
        if joint.JointType == "Revolute":
            motion.Rotation = engine.app.Rotation(engine.app.Vector(0, 0, 1), value)
        else:
            motion.Base = engine.app.Vector(0, 0, value)
        prepared.append((joint, joint.JointType, joint.Placement1, motion, value))
    seed_tree(engine, doc, asm, {x[0].Name: x[4] for x in prepared})
    try:
        # Temporarily close each driven DOF with a native fixed joint. This drives
        # connected parts in a single solve without creating redundant joints.
        for joint, _kind, original, motion, _value in prepared:
            joint.JointType = "Fixed"
            joint.Placement1 = original * motion
        solve(engine, doc, asm)
    finally:
        for joint, kind, original, _motion, _value in prepared:
            joint.Placement1 = original
            joint.JointType = kind
    doc.recompute()
    validate(engine, doc, asm)
    check_residuals(engine, doc, asm)
    for joint, kind, _original, _motion, value in prepared:
        actual, relative = joint_value(engine, doc, asm, joint)
        error = (actual - value + 180) % 360 - 180 if kind == "Revolute" else actual - value
        if abs(error) > TOLERANCE:
            raise CadError("Solver could not reach requested joint position: " + joint.Name)


def apply(engine, doc, op):
    kind = op["op"]
    if kind == "create_assembly":
        import Assembly  # noqa: F401 - registers native document types

        if any(x.TypeId == "Assembly::AssemblyObject" for x in doc.Objects):
            raise CadError("Only one root assembly per document is supported")
        asm = mark(engine.add(doc, "Assembly::AssemblyObject", op["name"]), "assembly")
        asm.Type = "Assembly"
        asm.newObject("Assembly::JointGroup", asm.Name + "Joints")
        return asm
    asm = assembly(engine, doc, op["assembly"])
    if kind == "add_component":
        from .features import top_level

        if len(components(asm)) >= 200:
            raise CadError("Assembly is limited to 200 components")
        source = top_level(engine, doc, op["source"])
        if not source.Shape.Solids or getattr(source, "CadAssemblyRole", None):
            raise CadError("Component source must contain a solid outside the assembly")
        obj = mark(engine.add(doc, "App::Link", op["name"]), "component")
        obj.setLink(source)
        obj.LinkTransform = False
        obj.Placement = source.Placement
        asm.addObject(obj)
        engine.hide(source)
        return obj
    if kind in {"ground_component", "create_joint"}:
        import JointObject

        if len(group(asm).Group) >= 400:
            raise CadError("Assembly is limited to 400 joints")
        if kind == "ground_component":
            part = component(engine, doc, asm, op["component"])
            if asm.isPartGrounded(part):
                raise CadError("Component is already grounded")
            obj = mark(engine.add(doc, "App::FeaturePython", op["name"]), "ground")
            group(asm).addObject(obj)
            JointObject.GroundedJoint(obj, part)
            if engine.gui:
                JointObject.ViewProviderGroundedJoint(obj.ViewObject)
        else:
            if op["kind"] not in JOINT_TYPES:
                raise CadError("Joint kind must be fixed, revolute or slider")
            first = component(engine, doc, asm, op["component_a"])
            second = component(engine, doc, asm, op["component_b"])
            if first == second:
                raise CadError("Joint components must be different")
            a, b = frame(engine, op.get("frame_a")), frame(engine, op.get("frame_b"))
            obj = mark(engine.add(doc, "App::FeaturePython", op["name"]), "joint")
            group(asm).addObject(obj)
            JointObject.Joint(obj, JointObject.JointTypes.index(JOINT_TYPES[op["kind"]]))
            obj.Detach1 = obj.Detach2 = True
            obj.Reference1 = (asm, [first.Name + ".", first.Name + "."])
            obj.Reference2 = (asm, [second.Name + ".", second.Name + "."])
            obj.Placement1, obj.Placement2 = a, b
            if engine.gui:
                JointObject.ViewProviderJoint(obj.ViewObject)
        engine.hide(obj)
        return obj
    if kind == "set_joint_limits":
        joint = engine.obj(doc, op["joint"])
        if joint not in joints(asm) or joint.JointType not in {"Revolute", "Slider"}:
            raise CadError("Travel limits require a revolute or slider joint in this assembly")
        low, high = op.get("minimum"), op.get("maximum")
        if low is not None:
            number(low)
        if high is not None:
            number(high)
        if low is not None and high is not None and low > high:
            raise CadError("Minimum joint limit must not exceed maximum")
        if joint.JointType == "Revolute" and any(
            x is not None and not -180 <= x <= 180 for x in (low, high)
        ):
            raise CadError("Revolute limits must lie between -180 and 180 degrees")
        prefix = "Angle" if joint.JointType == "Revolute" else "Length"
        for suffix, value in (("Min", low), ("Max", high)):
            setattr(joint, "Enable" + prefix + suffix, value is not None)
            if value is not None:
                setattr(joint, prefix + suffix, value)
        solve(engine, doc, asm)
        return joint
    if kind == "set_joint_positions":
        position(engine, doc, asm, op["positions"])
    elif kind == "solve_assembly":
        solve(engine, doc, asm)
    else:
        raise CadError("Unsupported assembly operation")
    return asm


def inspect(engine, doc, asm):
    connected = connected_names(engine, doc, asm)
    items = []
    for joint in joints(asm):
        first, second = joint_parts(engine, doc, asm, joint)
        value, relative = joint_value(engine, doc, asm, joint)
        items.append(
            {
                "name": joint.Name,
                "kind": str(joint.JointType).lower(),
                "active": joint.Activated,
                "component_a": first.Name,
                "component_b": second.Name,
                "frame_a": encode(joint.Placement1),
                "frame_b": encode(joint.Placement2),
                "position": value if joint.JointType != "Fixed" else None,
                "units": "degrees" if joint.JointType == "Revolute" else "mm",
                "limits": limits(joint) if joint.JointType != "Fixed" else None,
            }
        )
    return {
        "name": asm.Name,
        "type": asm.TypeId,
        "revision": engine.revision(doc),
        "components": [
            {
                "name": x.Name,
                "source": x.LinkedObject.Name,
                "grounded": asm.isPartGrounded(x),
                "connected_to_ground": x.Name in connected,
                "placement": encode(x.Placement),
            }
            for x in components(asm)
        ],
        "joints": items,
        "angle_convention": "Relative frame rotation about local +Z, wrapped to [-180, 180] degrees",
        "scope": "Position commands support directed joint trees rooted at grounded components; no closed-loop motion, collision detection or dynamics",
    }
