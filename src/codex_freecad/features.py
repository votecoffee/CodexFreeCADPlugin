"""Parametric Part lofts and mirrors with explicit profile/plane validation."""

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
