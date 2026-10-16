"""Parametric Part lofts, mirrors and sweeps with explicit geometry validation."""

import re

from .engine import CadError


def top_level(engine, doc, name):
    obj = engine.obj(doc, name)
    if obj.getParentGeoFeatureGroup() is not None:
        raise CadError(
            "Use a top-level profile or source; nested body/part coordinates are not supported"
        )
    engine.shape(doc, name)
    return obj


def check_dependency(source, target):
    pending, seen = [source], set()
    while pending:
        obj = pending.pop()
        if obj == target:
            raise CadError("Feature dependency would create a cycle")
        if obj.Name not in seen:
            seen.add(obj.Name)
            pending.extend(obj.OutList)


def loft(engine, doc, op):
    names = op["profiles"]
    if (
        not isinstance(names, list)
        or not 2 <= len(names) <= 50
        or any(not isinstance(name, str) for name in names)
        or len(set(names)) != len(names)
    ):
        raise CadError("Loft requires 2 to 50 distinct profile names in section order")
    if op["op"] == "set_loft":
        obj = engine.obj(doc, op["object"])
        if obj.TypeId != "Part::Loft":
            raise CadError("Target must be a native Part loft")
    else:
        obj = engine.add(doc, "Part::Loft", op["name"])
    solid = op.get("solid", obj.Solid if op["op"] == "set_loft" else True)
    ruled = op.get("ruled", obj.Ruled if op["op"] == "set_loft" else False)
    if type(solid) is not bool or type(ruled) is not bool:
        raise CadError("Loft solid and ruled controls must be booleans")
    profiles = []
    for name in names:
        profile = top_level(engine, doc, name)
        check_dependency(profile, obj)
        shape = profile.Shape
        if shape.Solids or len(shape.Wires) != 1:
            raise CadError("Each loft profile must contain exactly one wire and no solid")
        if solid and not shape.Wires[0].isClosed():
            raise CadError("Solid lofts require closed profile wires")
        profiles.append(profile)
    obj.Sections, obj.Solid, obj.Ruled = profiles, solid, ruled
    engine.hide(*profiles)
    return obj


def mirror(engine, doc, op):
    if op["op"] == "set_mirror":
        obj = engine.obj(doc, op["object"])
        if obj.TypeId != "Part::Mirroring":
            raise CadError("Target must be a native Part mirror")
        source = obj.Source
    else:
        source = top_level(engine, doc, op["source"])
        obj = engine.add(doc, "Part::Mirroring", op["name"])
    if source is None:
        raise CadError("Mirror requires a source")
    normal = engine.vector(op.get("normal", [1, 0, 0]))
    if normal.Length == 0:
        raise CadError("Mirror plane normal cannot be zero")
    obj.Source = source
    obj.MirrorPlane = None
    obj.Base, obj.Normal = engine.vector(op.get("point", [0, 0, 0])), normal
    engine.hide(source)
    return obj


def sweep(engine, doc, op):
    import Part

    names = op["profiles"]
    if (
        not isinstance(names, list)
        or not 1 <= len(names) <= 50
        or any(not isinstance(name, str) for name in names)
        or len(set(names)) != len(names)
    ):
        raise CadError("Sweep requires 1 to 50 distinct profile names in section order")
    updating = op["op"] == "set_sweep"
    if updating:
        obj = engine.obj(doc, op["object"])
        if obj.TypeId != "Part::Sweep":
            raise CadError("Target must be a native Part sweep")
    else:
        obj = engine.add(doc, "Part::Sweep", op["name"])
    solid = op.get("solid", obj.Solid if updating else True)
    frenet = op.get("frenet", obj.Frenet if updating else False)
    transitions = {
        "transformed": "Transformed",
        "right_corner": "Right corner",
        "round_corner": "Round corner",
    }
    transition = op.get("transition", str(obj.Transition) if updating else "transformed")
    if transition not in transitions and not (updating and transition == str(obj.Transition)):
        raise CadError("Sweep transition must be transformed, right_corner or round_corner")
    if type(solid) is not bool or type(frenet) is not bool:
        raise CadError("Sweep solid and frenet controls must be booleans")
    profiles = []
    for name in names:
        profile = top_level(engine, doc, name)
        check_dependency(profile, obj)
        shape = profile.Shape
        if shape.Solids or len(shape.Wires) != 1:
            raise CadError("Each sweep profile must contain exactly one wire and no solid")
        if solid and not shape.Wires[0].isClosed():
            raise CadError("Solid sweeps require closed profile wires")
        profiles.append(profile)
    path = top_level(engine, doc, op["path"])
    check_dependency(path, obj)
    if path in profiles:
        raise CadError("Sweep path and profiles must be different objects")
    edges = op.get("path_edges", [])
    if (
        not isinstance(edges, list)
        or len(edges) > 500
        or any(not isinstance(edge, str) for edge in edges)
    ):
        raise CadError("path_edges must be a list of up to 500 EdgeN names")
    if len(edges) != len(set(edges)) or any(
        not re.fullmatch(r"Edge[1-9][0-9]*", edge) for edge in edges
    ):
        raise CadError("Sweep path edge names must be distinct EdgeN names from inspection")
    if edges:
        wire = Part.Wire([engine.subshape(path.Shape, edge) for edge in edges])
        # Building a wire can silently discard disconnected edges in native wrappers.
        if len(wire.Edges) != len(edges):
            raise CadError("Selected path edges must form one connected wire")
    else:
        if path.Shape.Solids or len(path.Shape.Wires) != 1:
            raise CadError(
                "Sweep path must contain exactly one wire, or select its path_edges explicitly"
            )
        wire = path.Shape.Wires[0]
    if not wire.isValid() or wire.Length <= 0:
        raise CadError("Sweep path must be a valid connected wire with positive length")
    obj.Sections, obj.Spine = profiles, (path, edges)
    obj.Solid, obj.Frenet = solid, frenet
    obj.Transition = transitions.get(transition, transition)
    engine.hide(*profiles, path)
    return obj
