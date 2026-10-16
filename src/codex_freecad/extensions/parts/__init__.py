"""Installed extension API v1. Imports must not change models or start callbacks."""

from codex_freecad.engine import CadError, encode


def create_tube(engine, doc, arguments):
    name = arguments["name"]
    if arguments["inner_radius"] >= arguments["outer_radius"]:
        raise CadError("Tube inner radius must be smaller than its outer radius")
    for suffix, radius in (("Outer", "outer_radius"), ("Inner", "inner_radius")):
        engine.operation(
            doc,
            {
                "op": "create_cylinder",
                "name": name + suffix,
                "radius": arguments[radius],
                "height": arguments["height"],
            },
        )
    engine.operation(
        doc,
        {
            "op": "boolean",
            "kind": "cut",
            "name": name,
            "base": name + "Outer",
            "tool": name + "Inner",
        },
    )
    return {"name": name, "type": doc.getObject(name).TypeId}


def mass_properties(engine, doc, arguments):
    shape = engine.shape(doc, arguments["object"])
    solids = shape.Solids
    volume = sum(solid.Volume for solid in solids)
    if not solids or volume <= 0:
        raise CadError("Mass properties require positive-volume BREP solids")
    center = engine.app.Vector()
    for solid in solids:
        center += solid.CenterOfMass * (solid.Volume / volume)
    result = {
        "volume_mm3": shape.Volume,
        "area_mm2": shape.Area,
        "center_of_mass_mm": encode(center),
        "solids": len(shape.Solids),
    }
    if "density_kg_m3" in arguments:
        result["mass_kg"] = shape.Volume * arguments["density_kg_m3"] * 1e-9
    return result
