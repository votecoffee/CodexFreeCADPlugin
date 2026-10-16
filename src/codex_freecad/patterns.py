"""Solid patterns backed by FreeCAD's native compact link arrays."""

from .engine import CadError, number


def count_value(value):
    if type(value) is not int or not 2 <= value <= 200:
        raise CadError("Pattern count must be an integer between 2 and 200, including the original")
    return value


def apply(engine, doc, op):
    creating = op["op"] in {"linear_pattern", "circular_pattern"}
    kind = "linear" if op["op"] in {"linear_pattern", "set_linear_pattern"} else "circular"
    count = count_value(op["count"])
    if creating:
        source = engine.obj(doc, op["source"])
    else:
        pattern = engine.obj(doc, op["object"])
        if pattern.TypeId != "App::Link" or getattr(pattern, "CadPatternKind", None) != kind:
            raise CadError("Target must be a matching integration-created native pattern")
        source = pattern.LinkedObject
    shape = engine.shape(doc, source.Name)
    if not shape.Solids:
        raise CadError("Pattern source must contain a solid")
    if any(parent.TypeId in {"PartDesign::Body", "App::Part"} for parent in source.InList):
        raise CadError("Use a top-level solid or the top-level Body itself as the pattern source")
    source_placement = source.Placement
    if kind == "linear":
        step = engine.vector(op["step"])
        if step.Length == 0:
            raise CadError("Pattern step must be nonzero")
        placements = [
            engine.app.Placement(step * i, engine.app.Rotation()).multiply(source_placement)
            for i in range(count)
        ]
    else:
        center, axis = (
            engine.vector(op.get("center", [0, 0, 0])),
            engine.vector(op.get("axis", [0, 0, 1])),
        )
        angle = number(op.get("angle", 360))
        if axis.Length == 0 or angle == 0 or abs(angle) > 360:
            raise CadError(
                "Circular pattern needs a nonzero axis and nonzero angle within +/-360 degrees"
            )
        increment = angle / (count if abs(angle) == 360 else count - 1)
        placements = []
        for i in range(count):
            rotation = engine.app.Rotation(axis, increment * i)
            transform = engine.app.Placement(center - rotation.multVec(center), rotation)
            placements.append(transform.multiply(source_placement))
    if creating:
        pattern = engine.add(doc, "App::Link", op["name"])
        pattern.setLink(source)
        pattern.addProperty("App::PropertyString", "CadPatternKind", "CAD pattern")
        pattern.addProperty("App::PropertyVector", "CadPatternStep", "CAD pattern")
        pattern.addProperty("App::PropertyVector", "CadPatternCenter", "CAD pattern")
        pattern.addProperty("App::PropertyVector", "CadPatternAxis", "CAD pattern")
        pattern.addProperty("App::PropertyAngle", "CadPatternAngle", "CAD pattern")
        pattern.CadPatternKind = kind
    root_placement = pattern.Placement
    pattern.LinkTransform = False
    pattern.ShowElement = False
    pattern.ElementCount = count
    pattern.PlacementList = placements
    pattern.Placement = root_placement
    if kind == "linear":
        pattern.CadPatternStep = step
    else:
        pattern.CadPatternCenter, pattern.CadPatternAxis, pattern.CadPatternAngle = (
            center,
            axis,
            angle,
        )
    for prop in (
        "CadPatternKind",
        "CadPatternStep",
        "CadPatternCenter",
        "CadPatternAxis",
        "CadPatternAngle",
        "ElementCount",
    ):
        pattern.setEditorMode(prop, 1)
    engine.hide(source)
    return pattern


def summary(obj):
    data = {
        "kind": obj.CadPatternKind,
        "source": obj.LinkedObject.Name,
        "count": obj.ElementCount,
        "includes_original": True,
        "fused": False,
        "placement_behavior": "source placement sampled at creation/update; native source dimensions remain linked",
    }
    if obj.CadPatternKind == "linear":
        step = obj.CadPatternStep
        data["step_mm"] = [step.x, step.y, step.z]
    else:
        for prop, key in ((obj.CadPatternCenter, "center_mm"), (obj.CadPatternAxis, "axis")):
            data[key] = [prop.x, prop.y, prop.z]
        data["angle_degrees"] = obj.CadPatternAngle.Value
    return data
