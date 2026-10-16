"""Persistent native drill features; no executable model proxies or import side effects."""

import math

from codex_freecad.engine import CadError, encode

EPSILON = 0.1  # mm, extends tools beyond end planes, clear of native boolean edge tolerances.


def direction(engine, arguments):
    vector = engine.vector(arguments["direction"])
    if vector.Length < 1e-12:
        raise CadError("Hole direction must be nonzero")
    return vector / vector.Length


def settings(arguments):
    style, mode = arguments["style"], arguments["mode"]
    diameter = arguments["diameter"]
    if mode == "blind" and "depth" not in arguments:
        raise CadError("Blind holes require depth, measured to a flat bottom")
    if mode == "through" and "depth" in arguments:
        raise CadError("Through holes calculate their depth; omit depth")
    recess_diameter = arguments.get("recess_diameter")
    recess_depth = arguments.get("recess_depth")
    angle = arguments.get("countersink_angle", 90)
    if style == "simple":
        if any(k in arguments for k in ("recess_diameter", "recess_depth", "countersink_angle")):
            raise CadError("Simple holes do not accept recess dimensions")
    else:
        if recess_diameter is None or recess_diameter <= diameter:
            raise CadError("Recess diameter must be greater than hole diameter")
        if style == "counterbore":
            if recess_depth is None or "countersink_angle" in arguments:
                raise CadError("Counterbores require recess_depth and no countersink_angle")
        else:
            if recess_depth is not None:
                raise CadError("Countersinks derive recess depth from countersink_angle")
            recess_depth = (recess_diameter - diameter) / (2 * math.tan(math.radians(angle / 2)))
        if mode == "blind" and recess_depth >= arguments["depth"]:
            raise CadError("Recess depth must be less than blind hole depth")
    return recess_diameter, recess_depth, angle


def through_extent(shape, positions, axis):
    box = shape.BoundBox
    projections = [
        axis.x * x + axis.y * y + axis.z * z
        for x in (box.XMin, box.XMax)
        for y in (box.YMin, box.YMax)
        for z in (box.ZMin, box.ZMax)
    ]
    entries = [position.dot(axis) for position in positions]
    near, far = min(projections), max(projections)
    offset = max(0, max(entries) - near) + EPSILON
    depth = max(0, far - min(entries)) + offset + EPSILON
    if not 0.01 <= depth <= 1e6:
        raise CadError("Through-hole extent must be between 0.01 and 1000000 mm")
    return depth, offset


def validate_shape(engine, doc, result, parameters):
    """Check each bore hits material, each recess has an effect, and the result stays solid."""
    base = engine.shape(doc, result.Base.Name)
    if not base.Solids or base.Volume <= 0:
        raise CadError("Hole base must contain positive-volume BREP solids")
    if parameters.Mode == "blind" and parameters.Style != "simple":
        if parameters.RecessDepth.Value >= parameters.Depth.Value:
            raise CadError("Recess depth must be less than blind hole depth")
    if (
        parameters.Style != "simple"
        and parameters.RecessDiameter.Value <= parameters.Diameter.Value
    ):
        raise CadError("Recess diameter must be greater than hole diameter")
    for index in range(len(parameters.Positions)):
        prefix = result.Name + "Bore" + str(index + 1)
        shaft = engine.shape(doc, prefix)
        if base.common(shaft).Volume <= 1e-9:
            raise CadError("Hole " + str(index + 1) + " does not intersect solid material")
        if parameters.Style != "simple":
            recess = engine.shape(doc, prefix + "Recess")
            if recess.cut(shaft).common(base).Volume <= 1e-9:
                raise CadError("Recess " + str(index + 1) + " does not intersect solid material")
    if result.Shape.isNull() or not result.Shape.isValid() or not result.Shape.Solids:
        raise CadError("Hole operation did not leave a valid solid")
    if result.Shape.Volume <= 1e-9 or base.Volume - result.Shape.Volume <= 1e-9:
        raise CadError("Hole operation must remove material and leave a positive-volume solid")


def primitive(engine, doc, type_id, name, placement, expressions):
    obj = engine.add(doc, type_id, name)
    obj.Placement = placement
    for path, expression in expressions.items():
        obj.setExpression(path, expression)
    engine.hide(obj)
    return obj


def build(engine, doc, arguments, positions):
    import FreeCAD as App

    recess_diameter, recess_depth, angle = settings(arguments)
    axis = direction(engine, arguments)
    positions = [engine.vector(position) for position in positions]
    for index, position in enumerate(positions):
        if any((position - earlier).Length < 1e-7 for earlier in positions[:index]):
            raise CadError("Hole positions must be distinct")
    base = engine.obj(doc, arguments["base"])
    shape = engine.shape(doc, base.Name)
    if not shape.Solids or shape.Volume <= 0:
        raise CadError("Hole base must contain positive-volume BREP solids")
    through = arguments["mode"] == "through"
    depth, offset = through_extent(shape, positions, axis) if through else (arguments["depth"], 0)
    name = arguments["name"]
    parameters = engine.add(doc, "App::FeaturePython", name + "Parameters")
    # Proxy is None: dimensions, links and native expressions survive removal of this extension.
    for prop, value in (
        ("Diameter", arguments["diameter"]),
        ("Depth", depth),
        ("EntryOffset", offset),
    ):
        parameters.addProperty("App::PropertyLength", prop, "Hole dimensions")
        setattr(parameters, prop, value)
    for prop, value, type_id in (
        ("Mode", arguments["mode"], "App::PropertyString"),
        ("Style", arguments["style"], "App::PropertyString"),
        ("Positions", positions, "App::PropertyVectorList"),
        ("Direction", axis, "App::PropertyVector"),
    ):
        parameters.addProperty(type_id, prop, "Hole layout")
        setattr(parameters, prop, value)
        parameters.setEditorMode(prop, 1)
    ref = parameters.Name + "."
    if recess_diameter is not None:
        parameters.addProperty("App::PropertyLength", "RecessDiameter", "Hole dimensions")
        parameters.RecessDiameter = recess_diameter
        parameters.addProperty("App::PropertyLength", "RecessDepth", "Hole dimensions")
        parameters.RecessDepth = recess_depth
        if arguments["style"] == "countersink":
            parameters.addProperty("App::PropertyAngle", "CountersinkAngle", "Hole dimensions")
            parameters.CountersinkAngle = angle
            parameters.setExpression(
                "RecessDepth", "(RecessDiameter - Diameter) / (2 * tan(CountersinkAngle / 2))"
            )
    rotation = App.Rotation(App.Vector(0, 0, 1), axis)
    tools = []
    for index, position in enumerate(positions):
        prefix = name + "Bore" + str(index + 1)
        expressions = {"Radius": ref + "Diameter / 2", "Height": ref + "Depth"}
        if through:
            for component in ("x", "y", "z"):
                expressions["Placement.Base." + component] = (
                    f"{getattr(position, component)} mm - {getattr(axis, component)} * "
                    + ref
                    + "EntryOffset"
                )
        tools.append(
            primitive(
                engine,
                doc,
                "Part::Cylinder",
                prefix,
                App.Placement(position, rotation),
                expressions,
            )
        )
        if arguments["style"] == "counterbore":
            tools.append(
                primitive(
                    engine,
                    doc,
                    "Part::Cylinder",
                    prefix + "Recess",
                    App.Placement(position - axis * EPSILON, rotation),
                    {
                        "Radius": ref + "RecessDiameter / 2",
                        "Height": ref + f"RecessDepth + {EPSILON} mm",
                    },
                )
            )
        elif arguments["style"] == "countersink":
            tools.append(
                primitive(
                    engine,
                    doc,
                    "Part::Cone",
                    prefix + "Recess",
                    App.Placement(position, rotation),
                    {
                        "Radius1": ref + "RecessDiameter / 2",
                        "Radius2": ref + "Diameter / 2",
                        "Height": ref + "RecessDepth",
                    },
                )
            )
    tool = tools[0]
    if len(tools) > 1:
        tool = engine.add(doc, "Part::MultiFuse", name + "Tools")
        tool.Shapes = tools
        tool.Refine = True
        engine.hide(tool)
    result = engine.add(doc, "Part::Cut", name)
    result.Base, result.Tool, result.Refine = base, tool, True
    result.addProperty("App::PropertyLink", "HoleParameters", "Hole dimensions")
    result.HoleParameters = parameters
    result.setEditorMode("HoleParameters", 1)
    doc.recompute()
    validate_shape(engine, doc, result, parameters)
    engine.hide(base)
    return describe(result)


def describe(result):
    parameters = result.HoleParameters
    return {
        "name": result.Name,
        "parameters": parameters.Name,
        "base": result.Base.Name,
        "mode": parameters.Mode,
        "style": parameters.Style,
        "positions_mm": encode(parameters.Positions),
        "direction": encode(parameters.Direction),
        "depth_mm": parameters.Depth.Value,
        "removed_volume_mm3": result.Base.Shape.Volume - result.Shape.Volume,
        "through_extent": "measured at creation/refresh; refresh after changing or moving the base",
    }


def drill(engine, doc, arguments):
    return build(engine, doc, arguments, arguments["positions"])


def bolt_circle(engine, doc, arguments):
    axis = direction(engine, arguments)
    rotation = engine.app.Rotation(engine.app.Vector(0, 0, 1), axis)
    center = engine.vector(arguments["center"])
    positions = []
    for index in range(arguments["count"]):
        angle = math.radians(arguments["start_angle"] + 360 * index / arguments["count"])
        local = engine.app.Vector(math.cos(angle), math.sin(angle), 0) * arguments["radius"]
        positions.append(encode(center + rotation.multVec(local)))
    return build(engine, doc, arguments, positions)


def refresh(engine, doc, arguments):
    result = engine.obj(doc, arguments["object"])
    if result.TypeId != "Part::Cut" or "HoleParameters" not in result.PropertiesList:
        raise CadError("Refresh requires a hole feature created by this extension")
    parameters = result.HoleParameters
    if parameters is None:
        raise CadError("Hole parameters are missing")
    if parameters.Mode == "through":
        depth, offset = through_extent(
            engine.shape(doc, result.Base.Name), parameters.Positions, parameters.Direction
        )
        parameters.Depth, parameters.EntryOffset = depth, offset
    doc.recompute()
    validate_shape(engine, doc, result, parameters)
    return describe(result)
