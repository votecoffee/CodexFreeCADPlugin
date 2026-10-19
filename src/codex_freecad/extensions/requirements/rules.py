"""Bounded, explicit design measurements; no executable expressions or implicit units."""

import math
import re

from codex_freecad.engine import CadError, number
from codex_freecad.parameters import NUMERIC_TYPES

FIELDS = {
    "property": {"property"},
    "volume": set(),
    "mass": {"density_kg_m3"},
    "extent": {"axis"},
    "clearance": {"other", "overlap_tolerance_mm3"},
}
COMMON = {"id", "metric", "object", "minimum", "maximum", "absolute_tolerance"}
PROPERTY_UNITS = {
    "App::PropertyLength": "mm",
    "App::PropertyDistance": "mm",
    "App::PropertyAngle": "deg",
    "App::PropertyArea": "mm^2",
    "App::PropertyVolume": "mm^3",
    "App::PropertyPercent": "%",
}


def validate(rules):
    if not isinstance(rules, list) or not 1 <= len(rules) <= 50:
        raise CadError("Provide between 1 and 50 design requirements")
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict) or not {"id", "metric", "object"} <= rule.keys():
            raise CadError("Each requirement needs id, metric and object")
        key, metric = rule["id"], rule["metric"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", key):
            raise CadError("Requirement IDs must be identifiers of at most 80 characters")
        if key in seen:
            raise CadError("Requirement IDs must be unique")
        seen.add(key)
        if not isinstance(metric, str) or metric not in FIELDS:
            raise CadError("Unknown requirement metric")
        if rule.keys() - COMMON - FIELDS[metric]:
            raise CadError("Unexpected fields for requirement metric " + metric)
        for field in ("object", "other"):
            if field in rule and (
                not isinstance(rule[field], str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", rule[field])
            ):
                raise CadError("Requirements must reference internal object names")
        if "minimum" not in rule and "maximum" not in rule:
            raise CadError("A requirement needs a minimum or maximum")
        for field in ("minimum", "maximum"):
            if field in rule:
                value = number(rule[field])
                if abs(value) > 1e12 or (metric != "property" and value < 0):
                    raise CadError("Requirement limit is outside the supported range")
        if rule.get("minimum", -math.inf) > rule.get("maximum", math.inf):
            raise CadError("Requirement minimum must not exceed maximum")
        if not 0 <= number(rule.get("absolute_tolerance", 0)) <= 1e6:
            raise CadError("Absolute tolerance must be between zero and 1000000")
        if metric == "property" and (
            not isinstance(rule.get("property"), str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", rule["property"])
        ):
            raise CadError("Property requirements need a numeric scalar property name")
        if metric == "mass" and not 0 < number(rule.get("density_kg_m3")) <= 1e6:
            raise CadError("Mass requirements need explicit positive density up to 1000000 kg/m3")
        if metric == "extent" and rule.get("axis") not in {"x", "y", "z"}:
            raise CadError("Extent requirements need axis x, y or z")
        if metric == "clearance":
            if "other" not in rule or rule["other"] == rule["object"]:
                raise CadError("Clearance requirements need two distinct object names")
            if not 0 <= number(rule.get("overlap_tolerance_mm3", 1e-6)) <= 1e6:
                raise CadError("Overlap tolerance must be between zero and 1000000 mm3")
    return rules


def targets(rules):
    return sorted({rule[field] for rule in rules for field in ("object", "other") if field in rule})


def solid(engine, doc, name, cache):
    if name not in cache:
        obj = engine.obj(doc, name)
        parent = obj.getParentGeoFeatureGroup()
        if parent is not None and (
            parent.TypeId != "Assembly::AssemblyObject" or not parent.Placement.isIdentity()
        ):
            raise CadError("Select top-level solids or root identity assembly components")
        shape = engine.shape(doc, name)
        if not shape.isValid() or not shape.Solids or shape.Volume <= 0:
            raise CadError("Geometric requirements need valid positive-volume BREP solids")
        if sum(len(item.Edges) for item in cache.values()) + len(shape.Edges) > 5000:
            raise CadError("Requirements support at most 5,000 distinct measured shape edges")
        cache[name] = shape
    return cache[name]


def measurement(engine, doc, rule, cache):
    obj = engine.obj(doc, rule["object"])
    if any(state in obj.State for state in ("Invalid", "Error", "Touched")):
        raise CadError("Recompute the requirement target before evaluating it")
    metric = rule["metric"]
    if metric == "property":
        prop = rule["property"]
        if prop not in obj.PropertiesList or obj.getTypeIdOfProperty(prop) not in NUMERIC_TYPES:
            raise CadError("Property requirements need a supported numeric scalar property")
        prop_type = obj.getTypeIdOfProperty(prop)
        if prop_type == "App::PropertyQuantity":
            raise CadError("Generic quantity properties need a specific dimensional property type")
        value = getattr(obj, prop)
        unit = PROPERTY_UNITS.get(prop_type, "dimensionless")
        return number(value.Value if hasattr(value, "Value") else value), unit, {}
    shape = solid(engine, doc, obj.Name, cache)
    if metric == "volume":
        return shape.Volume, "mm^3", {}
    if metric == "mass":
        return shape.Volume * rule["density_kg_m3"] * 1e-9, "kg", {}
    if metric == "extent":
        box = shape.optimalBoundingBox(False, False)
        return getattr(box, rule["axis"].upper() + "Length"), "mm", {}
    other = engine.obj(doc, rule["other"])
    if any(state in other.State for state in ("Invalid", "Error", "Touched")):
        raise CadError("Recompute the second clearance target before evaluating it")
    other_shape = solid(engine, doc, other.Name, cache)
    common = shape.common(other_shape)
    if not common.isNull() and not common.isValid():
        raise CadError("Native clearance intersection is invalid")
    overlap = 0.0 if common.isNull() or not common.Solids else common.Volume
    distance = shape.distToShape(other_shape)[0]
    if overlap < 0 or distance < 0:
        raise CadError("Native clearance produced a negative distance or overlap volume")
    return (
        distance,
        "mm",
        {
            "overlap_mm3": number(overlap),
            "overlap_tolerance_mm3": rule.get("overlap_tolerance_mm3", 1e-6),
        },
    )


def evaluate(engine, doc, rules, link_error=None):
    rows, cache = [], {}
    for rule in rules:
        row = {"id": rule["id"], "metric": rule["metric"], "object": rule["object"]}
        row.update(
            {
                key: rule[key]
                for key in ("property", "axis", "other", "density_kg_m3")
                if key in rule
            }
        )
        row["limits"] = {key: rule[key] for key in ("minimum", "maximum") if key in rule}
        row["absolute_tolerance"] = rule.get("absolute_tolerance", 0)
        try:
            if link_error:
                raise CadError(link_error)
            value, unit, detail = measurement(engine, doc, rule, cache)
            value = number(value)
            tolerance = row["absolute_tolerance"]
            passed = (
                value >= rule.get("minimum", -math.inf) - tolerance
                and value <= rule.get("maximum", math.inf) + tolerance
                and detail.get("overlap_mm3", 0) <= detail.get("overlap_tolerance_mm3", 0)
            )
            row.update(status="pass" if passed else "fail", value=value, unit=unit, **detail)
        except Exception as exc:
            row.update(status="error", error=str(exc))
        rows.append(row)
    counts = {
        state: sum(row["status"] == state for row in rows) for state in ("pass", "fail", "error")
    }
    return {"all_passed": counts["pass"] == len(rows), "counts": counts, "rules": rows}
