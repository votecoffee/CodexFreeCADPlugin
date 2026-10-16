"""Bounded JSON Schema subset shared with FreeCAD's dependency-free interpreter."""

import copy
import json
import math
import re

from .engine import CadError

TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
KEYS = {
    "type",
    "description",
    "title",
    "default",
    "enum",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
}


def check_schema(schema, depth=0):
    if (
        depth > 12
        or not isinstance(schema, dict)
        or not isinstance(schema.get("type"), str)
        or schema["type"] not in TYPES
    ):
        raise CadError("Extension schema requires one supported type and at most 12 levels")
    if schema.keys() - KEYS:
        raise CadError(
            "Unsupported extension schema keywords: " + str(sorted(schema.keys() - KEYS))
        )
    kind = schema["type"]
    common = {"type", "description", "title", "default", "enum"}
    allowed = {
        "object": {"properties", "required", "additionalProperties"},
        "array": {"items", "minItems", "maxItems"},
        "string": {"minLength", "maxLength", "pattern"},
        "number": {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"},
        "integer": {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"},
    }.get(kind, set())
    if schema.keys() - common - allowed:
        raise CadError("Extension schema keywords do not match its type")
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if (
            not isinstance(properties, dict)
            or len(properties) > 100
            or any(not isinstance(k, str) for k in properties)
        ):
            raise CadError("Extension objects support at most 100 named properties")
        if (
            not isinstance(required, list)
            or any(not isinstance(x, str) or x not in properties for x in required)
            or len(set(required)) != len(required)
        ):
            raise CadError("Extension schema required fields must be unique property names")
        if schema.get("additionalProperties") is not False:
            raise CadError("Extension object schemas must set additionalProperties=false")
        for value in properties.values():
            check_schema(value, depth + 1)
    if kind == "array":
        check_schema(schema.get("items"), depth + 1)
    for key in ("minItems", "maxItems", "minLength", "maxLength"):
        if key in schema and (type(schema[key]) is not int or not 0 <= schema[key] <= 65536):
            raise CadError("Invalid extension schema length bound")
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if key in schema and (
            type(schema[key]) not in {int, float} or not math.isfinite(schema[key])
        ):
            raise CadError("Invalid extension schema numeric bound")
    for low, high in (("minItems", "maxItems"), ("minLength", "maxLength"), ("minimum", "maximum")):
        if low in schema and high in schema and schema[low] > schema[high]:
            raise CadError("Extension schema has reversed bounds")
    if "pattern" in schema:
        if not isinstance(schema["pattern"], str) or len(schema["pattern"]) > 512:
            raise CadError("Invalid extension schema pattern")
        try:
            re.compile(schema["pattern"])
        except re.error as exc:
            raise CadError("Invalid extension schema pattern") from exc
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise CadError("Extension enum must be a nonempty list")
    if "default" in schema:
        validate(schema, schema["default"])


def validate(schema, value, path="arguments", depth=0):
    if depth > 12:
        raise CadError(path + " exceeds the nesting limit")
    kind = schema["type"]
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in {int, float},
        "null": value is None,
    }[kind]
    if not valid:
        raise CadError(path + " must be " + kind)
    if kind in {"number", "integer"}:
        if not math.isfinite(value):
            raise CadError(path + " must be finite")
        for key, invalid in (
            ("minimum", lambda x: value < x),
            ("maximum", lambda x: value > x),
            ("exclusiveMinimum", lambda x: value <= x),
            ("exclusiveMaximum", lambda x: value >= x),
        ):
            if key in schema and invalid(schema[key]):
                raise CadError(path + " violates " + key)
    if kind in {"string", "array"}:
        low, high = ("minLength", "maxLength") if kind == "string" else ("minItems", "maxItems")
        if len(value) < schema.get(low, 0) or len(value) > schema.get(high, 65536):
            raise CadError(path + " has an invalid length")
    if kind == "string" and "pattern" in schema and re.search(schema["pattern"], value) is None:
        raise CadError(path + " does not match the required pattern")
    if "enum" in schema and value not in schema["enum"]:
        raise CadError(path + " is not an allowed value")
    if kind == "object":
        if any(not isinstance(key, str) for key in value):
            raise CadError(path + " object keys must be strings")
        properties = schema.get("properties", {})
        if value.keys() - properties.keys():
            raise CadError(
                path + " has unexpected fields: " + str(sorted(value.keys() - properties.keys()))
            )
        result = dict(value)
        for name, prop in properties.items():
            if name not in result and "default" in prop:
                result[name] = copy.deepcopy(prop["default"])
        if set(schema.get("required", [])) - result.keys():
            raise CadError(path + " is missing required fields")
        return {
            key: validate(properties[key], item, path + "." + key, depth + 1)
            for key, item in result.items()
        }
    if kind == "array":
        return [
            validate(schema["items"], item, f"{path}[{i}]", depth + 1)
            for i, item in enumerate(value)
        ]
    return value


def bounded_json(value, maximum=65536):
    try:
        raw = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise CadError("Extension data must be finite JSON") from exc
    if len(raw.encode("utf-8")) > maximum:
        raise CadError("Extension data exceeds the size limit")
    return value
