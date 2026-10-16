"""Native numeric properties and a deliberately small FreeCAD expression language."""

import re

from .engine import SCALAR_TYPES, CadError, identifier, number

PARAMETER_TYPES = {
    "length": "App::PropertyLength",
    "angle": "App::PropertyAngle",
    "number": "App::PropertyFloat",
    "integer": "App::PropertyInteger",
}
NUMERIC_TYPES = SCALAR_TYPES - {"App::PropertyBool", "App::PropertyString"}
UNITS = {"mm", "cm", "m", "in", "ft", "deg", "rad"}
TOKEN = re.compile(
    r"\s*(?:(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)"
    r"|([A-Za-z][A-Za-z0-9_]*(?:(?:\.[A-Za-z][A-Za-z0-9_]*)|(?:\[\d+\]))*)"
    r"|([()+*/^\-]))"
)


def create(engine, doc, op):
    items = op["parameters"]
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise CadError("Provide between 1 and 100 named parameters")
    obj = engine.add(doc, "App::FeaturePython", op["name"])
    # This is a native property container: Proxy remains None, with no executable feature code.
    for item in items:
        if not isinstance(item, dict) or set(item) - {"name", "type", "value", "description"}:
            raise CadError("Parameter fields are name, type, value and optional description")
        if not {"name", "type", "value"} <= item.keys():
            raise CadError("Each parameter requires name, type and value")
        prop = identifier(item["name"])
        kind = item["type"]
        if kind not in PARAMETER_TYPES or prop in obj.PropertiesList:
            raise CadError("Parameter type must be length/angle/number/integer and names unique")
        value = item["value"]
        if kind == "integer":
            if type(value) is not int:
                raise CadError("Integer parameters require an integer value")
        elif isinstance(value, str):
            if kind == "number":
                raise CadError("Number parameters require a finite numeric value")
            value = engine.app.Units.Quantity(value)
            number(value.Value)
        else:
            number(value)
        if kind == "length" and (value.Value if hasattr(value, "Value") else value) < 0:
            raise CadError("Length parameters cannot be negative")
        description = item.get("description", "")
        if not isinstance(description, str) or len(description) > 1000:
            raise CadError("Parameter description must be text up to 1000 characters")
        obj.addProperty(PARAMETER_TYPES[kind], prop, "Design parameters", description)
        setattr(obj, prop, value)
    return obj


def numeric_path(obj, path, *, target=False):
    """Resolve only supported numeric property paths, never arbitrary Python attributes."""
    if not isinstance(path, str):
        raise CadError("Expression property path must be text")
    if "CadAssemblyRole" in obj.PropertiesList and target:
        raise CadError("Use dedicated assembly operations for managed assembly properties")
    if "CadPatternKind" in obj.PropertiesList and target:
        raise CadError("Use the dedicated pattern operations for managed pattern parameters")
    match = re.fullmatch(r"Constraints(?:\[(\d+)\]|\.([A-Za-z][A-Za-z0-9_]*))", path)
    if match and obj.isDerivedFrom("Sketcher::SketchObject"):
        if match[1] is not None:
            index = int(match[1])
        else:
            indices = [i for i in range(obj.ConstraintCount) if obj.Constraints[i].Name == match[2]]
            if len(indices) != 1:
                raise CadError("Unknown named sketch constraint: " + path)
            index = indices[0]
        if index >= obj.ConstraintCount:
            raise CadError("Constraint index is outside the sketch")
        try:
            driving = obj.getDriving(index)
        except Exception as exc:
            raise CadError("Expressions require a dimensional sketch constraint") from exc
        if target and not driving:
            raise CadError("Expression target must be a driving dimensional constraint")
        return "Constraints[" + str(index) + "]"
    if re.fullmatch(r"Placement\.Base\.[xyz]", path) and "Placement" in obj.PropertiesList:
        return path
    if (
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", path)
        or path not in obj.PropertiesList
        or obj.getTypeIdOfProperty(path) not in NUMERIC_TYPES
    ):
        raise CadError("Expression path must identify a numeric property or dimensional constraint")
    if target and "ReadOnly" in obj.getPropertyStatus(path):
        raise CadError("Expression target is read-only")
    return path


def validate_expression(engine, doc, obj, expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 1000:
        raise CadError("Expression must contain 1 to 1000 characters")
    expression = expression.strip()
    offset = 0
    while offset < len(expression):
        match = TOKEN.match(expression, offset)
        if not match:
            raise CadError("Expressions support arithmetic, numeric properties, units and pi only")
        offset = match.end()
        name = match[2]
        if name is None or name in UNITS or name == "pi":
            continue
        # Object names are internal document names, never labels or external documents.
        first, _, rest = name.partition(".")
        other = doc.getObject(first) if rest else None
        if other is not None:
            numeric_path(other, rest)
        else:
            numeric_path(obj, name)
    return expression


def apply(engine, doc, op):
    obj = engine.obj(doc, op["object"])
    path = numeric_path(obj, op["property"], target=True)
    if op["op"] == "set_expression":
        expression = validate_expression(engine, doc, obj, op["expression"])
        obj.setExpression(path, expression)
    else:
        if path not in expression_paths(obj):
            raise CadError("No expression is assigned to this property")
        # FreeCAD retains the last evaluated property value when its expression is removed.
        obj.setExpression(path, None)
    return obj


def expression_paths(obj):
    paths = [path.lstrip(".") for path, _ in obj.ExpressionEngine]
    return {numeric_path(obj, path) if path.startswith("Constraints.") else path for path in paths}
