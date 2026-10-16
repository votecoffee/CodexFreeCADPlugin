"""Dimensioned, unthreaded fasteners made entirely from persistent native features."""

import math

from codex_freecad.engine import CadError

EPSILON = 0.0001


def parameters(engine, doc, name, dimensions):
    obj = engine.add(doc, "App::FeaturePython", name + "Parameters")
    # A native property container only; no generation-owned model or view proxies.
    for prop, value in dimensions.items():
        obj.addProperty("App::PropertyLength", prop, "Fastener dimensions")
        setattr(obj, prop, value)
    return obj


def primitive(engine, doc, type_id, name, expressions, *, hexagon=False):
    obj = engine.add(doc, type_id, name)
    if hexagon:
        obj.Polygon = 6
    for prop, expression in expressions.items():
        obj.setExpression(prop, expression)
    engine.hide(obj)
    return obj


def finish(engine, doc, obj, params, arguments, kind):
    axis = engine.vector(arguments["axis"])
    if axis.Length < 1e-12:
        raise CadError("Fastener axis must be nonzero")
    rotation = engine.app.Rotation(engine.app.Vector(0, 0, 1), axis)
    rotation = rotation.multiply(
        engine.app.Rotation(engine.app.Vector(0, 0, 1), arguments["rotation"])
    )
    obj.Placement = engine.app.Placement(engine.vector(arguments["position"]), rotation)
    obj.addProperty("App::PropertyLink", "FastenerParameters", "Fastener dimensions")
    obj.FastenerParameters = params
    obj.setEditorMode("FastenerParameters", 1)
    obj.addProperty("App::PropertyString", "FastenerKind", "Fastener dimensions")
    obj.FastenerKind = kind
    obj.setEditorMode("FastenerKind", 1)
    doc.recompute()
    if (
        obj.Shape.isNull()
        or not obj.Shape.isValid()
        or len(obj.Shape.Solids) != 1
        or obj.Shape.Volume <= 0
    ):
        raise CadError("Fastener dimensions did not produce one valid positive-volume solid")
    return {
        "name": obj.Name,
        "parameters": params.Name,
        "kind": kind,
        "threaded": False,
        "dimension_source": "explicit dimensions; no standard or fit certification",
    }


def bolt(engine, doc, arguments):
    name = arguments["name"]
    style = arguments["head_style"]
    dimensions = {
        "Diameter": arguments["diameter"],
        "Length": arguments["length"],
        "HeadHeight": arguments["head_height"],
    }
    if style == "hex":
        if any(
            key in arguments for key in ("head_diameter", "socket_across_flats", "socket_depth")
        ):
            raise CadError(
                "Hex bolts accept across_flats, without socket dimensions or head_diameter"
            )
        if arguments.get("across_flats", 0) <= arguments["diameter"]:
            raise CadError("Hex head across_flats must be greater than shaft diameter")
        dimensions["AcrossFlats"] = arguments["across_flats"]
    else:
        if "across_flats" in arguments:
            raise CadError("Socket cap bolts use head_diameter instead of across_flats")
        if arguments.get("head_diameter", 0) <= arguments["diameter"]:
            raise CadError("Socket cap head_diameter must be greater than shaft diameter")
        if not {"socket_across_flats", "socket_depth"} <= arguments.keys():
            raise CadError("Socket cap bolts require socket_across_flats and socket_depth")
        if 2 * arguments["socket_across_flats"] / math.sqrt(3) >= arguments["head_diameter"]:
            raise CadError("Socket corners must fit inside the head diameter")
        if arguments["socket_depth"] >= arguments["head_height"]:
            raise CadError("Socket depth must be less than head height")
        dimensions.update(
            HeadDiameter=arguments["head_diameter"],
            SocketAcrossFlats=arguments["socket_across_flats"],
            SocketDepth=arguments["socket_depth"],
        )
    params = parameters(engine, doc, name, dimensions)
    ref = params.Name + "."
    shaft = primitive(
        engine,
        doc,
        "Part::Cylinder",
        name + "Shaft",
        {
            "Radius": ref + "Diameter / 2",
            "Height": ref + "Length",
            "Placement.Base.z": "-" + ref + "Length",
        },
    )
    head = primitive(
        engine,
        doc,
        "Part::Prism" if style == "hex" else "Part::Cylinder",
        name + "Head",
        {
            "Circumradius" if style == "hex" else "Radius": ref
            + (f"AcrossFlats / {math.sqrt(3)}" if style == "hex" else "HeadDiameter / 2"),
            "Height": ref + "HeadHeight",
        },
        hexagon=style == "hex",
    )
    result = engine.add(doc, "Part::Fuse", name if style == "hex" else name + "Blank")
    result.Base, result.Tool, result.Refine = shaft, head, True
    if style == "socket_cap":
        socket = primitive(
            engine,
            doc,
            "Part::Prism",
            name + "Socket",
            {
                "Circumradius": ref + f"SocketAcrossFlats / {math.sqrt(3)}",
                "Height": ref + f"SocketDepth + {EPSILON} mm",
                "Placement.Base.z": ref + "HeadHeight - " + ref + "SocketDepth",
            },
            hexagon=True,
        )
        blank = result
        result = engine.add(doc, "Part::Cut", name)
        result.Base, result.Tool, result.Refine = blank, socket, True
        engine.hide(blank)
    return finish(engine, doc, result, params, arguments, style + "_bolt")


def nut(engine, doc, arguments):
    if arguments["across_flats"] <= arguments["bore_diameter"]:
        raise CadError("Nut across_flats must be greater than bore diameter")
    name = arguments["name"]
    params = parameters(
        engine,
        doc,
        name,
        {
            "AcrossFlats": arguments["across_flats"],
            "BoreDiameter": arguments["bore_diameter"],
            "Thickness": arguments["thickness"],
        },
    )
    ref = params.Name + "."
    outer = primitive(
        engine,
        doc,
        "Part::Prism",
        name + "Outer",
        {"Circumradius": ref + f"AcrossFlats / {math.sqrt(3)}", "Height": ref + "Thickness"},
        hexagon=True,
    )
    return ring(engine, doc, arguments, params, outer, "hex_nut")


def washer(engine, doc, arguments):
    if arguments["outer_diameter"] <= arguments["bore_diameter"]:
        raise CadError("Washer outer_diameter must be greater than bore diameter")
    name = arguments["name"]
    params = parameters(
        engine,
        doc,
        name,
        {
            "OuterDiameter": arguments["outer_diameter"],
            "BoreDiameter": arguments["bore_diameter"],
            "Thickness": arguments["thickness"],
        },
    )
    outer = primitive(
        engine,
        doc,
        "Part::Cylinder",
        name + "Outer",
        {"Radius": params.Name + ".OuterDiameter / 2", "Height": params.Name + ".Thickness"},
    )
    return ring(engine, doc, arguments, params, outer, "plain_washer")


def ring(engine, doc, arguments, params, outer, kind):
    name, ref = arguments["name"], params.Name + "."
    bore = primitive(
        engine,
        doc,
        "Part::Cylinder",
        name + "Bore",
        {"Radius": ref + "BoreDiameter / 2", "Height": ref + f"Thickness + {2 * EPSILON} mm"},
    )
    bore.Placement.Base.z = -EPSILON
    result = engine.add(doc, "Part::Cut", name)
    result.Base, result.Tool, result.Refine = outer, bore, True
    return finish(engine, doc, result, params, arguments, kind)
