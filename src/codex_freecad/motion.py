"""Persistent affine joint couplings, stored as data without a feature proxy."""

import json

from .engine import CadError, number


def rules(asm, items=None):
    if items is None:
        try:
            items = json.loads(getattr(asm, "CadMotionCouplings", "[]"))
        except (TypeError, ValueError) as exc:
            raise CadError("Invalid stored motion couplings") from exc
    if not isinstance(items, list) or len(items) > 100:
        raise CadError("Motion supports at most 100 couplings")
    names = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"joint", "driver", "ratio", "offset"}:
            raise CadError("Invalid stored motion coupling fields")
        if not isinstance(item["joint"], str) or not isinstance(item["driver"], str):
            raise CadError("Coupling references must be joint names")
        if item["joint"] in names or item["joint"] == item["driver"]:
            raise CadError("Coupling followers must be unique and cannot drive themselves")
        names.add(item["joint"])
        if not 1e-9 <= abs(number(item["ratio"])) <= 1e6:
            raise CadError("Coupling ratio magnitude must be between 1e-9 and 1,000,000")
        if abs(number(item["offset"])) > 1e6:
            raise CadError("Coupling offset magnitude is limited to 1,000,000")
    by_name = {x["joint"]: x for x in items}
    for name in by_name:
        seen = set()
        while name in by_name:
            if name in seen:
                raise CadError("Motion coupling dependency cycle")
            seen.add(name)
            name = by_name[name]["driver"]
    return items


def coordinate(engine, doc, asm, joint):
    from .assemblies import joint_value

    value = joint_value(engine, doc, asm, joint)[0]
    previous = getattr(joint, "CadMotionCoordinate", value)
    number(previous)
    if joint.JointType == "Revolute":
        value += 360 * round((previous - value) / 360)
    return value


def moving_joints(asm):
    from .assemblies import joints

    return {x.Name: x for x in joints(asm) if x.JointType in {"Revolute", "Slider"}}


def validate(asm, items=None):
    moving = moving_joints(asm)
    items = rules(asm, items)
    for item in items:
        if item["joint"] not in moving or item["driver"] not in moving:
            raise CadError("Couplings require movable joints in the same assembly")
    return items


def root_coordinate(asm, name, value):
    by_name = {x["joint"]: x for x in validate(asm)}
    while name in by_name:
        item = by_name[name]
        value = (value - item["offset"]) / item["ratio"]
        name = item["driver"]
    number(value)
    return name, value


def resolve(engine, doc, asm, positions):
    moving = moving_joints(asm)
    items = validate(asm)
    roots = {}
    seen = set()
    for item in positions:
        if not isinstance(item, dict) or set(item) != {"joint", "position"}:
            raise CadError("Each joint position requires joint and position only")
        name = item["joint"]
        if name not in moving or name in seen:
            raise CadError("Position only unique revolute or slider joints in this assembly")
        seen.add(name)
        name, value = root_coordinate(asm, name, number(item["position"]))
        if name in roots and abs(roots[name] - value) > 1e-5:
            raise CadError("Requested joint positions conflict with their motion coupling")
        roots[name] = value
    followers = {x["joint"] for x in items}
    for item in items:
        name, _ = root_coordinate(asm, item["driver"], 0)
        if name not in roots:
            roots[name] = coordinate(engine, doc, asm, moving[name])
    values = dict(roots)
    pending = list(items)
    while pending:
        ready = [x for x in pending if x["driver"] in values]
        if not ready:
            raise CadError("Motion coupling dependency cycle")
        for item in ready:
            values[item["joint"]] = number(values[item["driver"]] * item["ratio"] + item["offset"])
        pending = [x for x in pending if x not in ready]
    if followers - values.keys() or len(values) > 200:
        raise CadError("Motion coupling exceeds the supported assembly size")
    return [{"joint": name, "position": value} for name, value in values.items()]


def remember(joint, value):
    if "CadMotionCoordinate" not in joint.PropertiesList:
        joint.addProperty("App::PropertyFloat", "CadMotionCoordinate", "CAD motion")
        joint.setEditorMode("CadMotionCoordinate", 1)
    joint.CadMotionCoordinate = value


def apply(engine, doc, op):
    from .assemblies import assembly, position

    asm = assembly(engine, doc, op["assembly"])
    items = validate(asm)
    if op["joint"] not in moving_joints(asm):
        raise CadError("Coupling follower must be a movable joint in this assembly")
    items = [x for x in items if x["joint"] != op["joint"]]
    if op["op"] == "set_joint_coupling":
        items.append({k: op.get(k, 0) for k in ("joint", "driver", "ratio", "offset")})
    validate(asm, items)
    if "CadMotionCouplings" not in asm.PropertiesList:
        asm.addProperty("App::PropertyString", "CadMotionCouplings", "CAD motion")
        asm.setEditorMode("CadMotionCouplings", 1)
    asm.CadMotionCouplings = json.dumps(items, sort_keys=True, allow_nan=False)
    validate(asm)
    if op["op"] == "set_joint_coupling":
        driver = engine.obj(doc, op["driver"])
        position(
            engine,
            doc,
            asm,
            [{"joint": driver.Name, "position": coordinate(engine, doc, asm, driver)}],
        )
    return asm
