"""Native sketch geometry helpers. No host-Python dependencies."""

from .engine import CadError, encode, number, positive


def point(engine, values):
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise CadError("Sketch coordinates must be 2D; use sketch Placement for other planes")
    return engine.vector(values)


def add_geometry(engine, sketch, items):
    import Part
    import Sketcher

    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise CadError("Provide between 1 and 1000 sketch geometry items")
    definitions = {
        "line": ({"start", "end"}, set()),
        "circle": ({"center", "radius"}, set()),
        "arc": ({"start", "mid", "end"}, set()),
        "rectangle": ({"origin", "width", "height"}, {"constrained"}),
    }
    records = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") not in definitions:
            raise CadError("Sketch geometry must be line, circle, arc or rectangle")
        kind = item["type"]
        required, optional = definitions[kind]
        if required - item.keys() or item.keys() - required - optional - {"type", "construction"}:
            raise CadError("Missing or unexpected sketch geometry fields")
        construction = item.get("construction", False)
        if type(construction) is not bool:
            raise CadError("construction must be a boolean")
        record = {"type": kind, "construction": construction}
        if kind == "line":
            native = Part.LineSegment(point(engine, item["start"]), point(engine, item["end"]))
        elif kind == "circle":
            native = Part.Circle(
                point(engine, item["center"]), engine.app.Vector(0, 0, 1), positive(item["radius"])
            )
        elif kind == "arc":
            native = Part.ArcOfCircle(
                point(engine, item["start"]), point(engine, item["mid"]), point(engine, item["end"])
            )
        else:
            origin = point(engine, item["origin"])
            width, height = positive(item["width"]), positive(item["height"])
            constrained = item.get("constrained", True)
            if type(constrained) is not bool:
                raise CadError("constrained must be a boolean")
            points = [
                origin,
                origin + engine.app.Vector(width, 0, 0),
                origin + engine.app.Vector(width, height, 0),
                origin + engine.app.Vector(0, height, 0),
            ]
            indices = [
                sketch.addGeometry(Part.LineSegment(points[i], points[(i + 1) % 4]), construction)
                for i in range(4)
            ]
            record["geometry_indices"] = indices
            if constrained:
                for i in range(4):
                    sketch.addConstraint(
                        Sketcher.Constraint("Coincident", indices[i], 2, indices[(i + 1) % 4], 1)
                    )
                    sketch.addConstraint(
                        Sketcher.Constraint("Horizontal" if i % 2 == 0 else "Vertical", indices[i])
                    )
                dimensions = {}
                for label, args in [
                    ("width", ("Distance", indices[0], float(width))),
                    ("height", ("Distance", indices[1], float(height))),
                    ("origin_x", ("DistanceX", indices[0], 1, float(origin.x))),
                    ("origin_y", ("DistanceY", indices[0], 1, float(origin.y))),
                ]:
                    index = sketch.addConstraint(Sketcher.Constraint(*args))
                    sketch.renameConstraint(index, f"Rect{indices[0]}_{label}")
                    dimensions[label] = index
                record["dimension_constraints"] = dimensions
            records.append(record)
            continue
        record["geometry_indices"] = [sketch.addGeometry(native, construction)]
        records.append(record)
    if sketch.solve() != 0:
        raise CadError("Sketch solver rejected the added geometry")
    return records


def inspect(engine, document, object_name):
    doc = engine.document(document)
    sketch = engine.obj(doc, object_name)
    if not sketch.isDerivedFrom("Sketcher::SketchObject"):
        raise CadError("Object must be a sketch")
    geometry = []
    for index, item in enumerate(sketch.Geometry):
        data = {
            "index": index,
            "type": type(item).__name__,
            "construction": sketch.getConstruction(index),
        }
        for attribute, key in (
            ("StartPoint", "start_mm"),
            ("EndPoint", "end_mm"),
            ("Center", "center_mm"),
        ):
            if hasattr(item, attribute):
                value = getattr(item, attribute)
                data[key] = [value.x, value.y]
        if hasattr(item, "Radius"):
            data["radius_mm"] = item.Radius
        if hasattr(item, "FirstParameter"):
            data["parameter_range"] = [item.FirstParameter, item.LastParameter]
        geometry.append(data)
    constraints = []
    for index, constraint in enumerate(sketch.Constraints):
        data = {
            "index": index,
            "name": constraint.Name,
            "type": constraint.Type,
            "value_native": number(constraint.Value),
            "driving": None,
            "active": sketch.getActive(index),
        }
        for field in ("First", "FirstPos", "Second", "SecondPos", "Third", "ThirdPos"):
            data[field] = getattr(constraint, field)
        if constraint.Type in {"Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle"}:
            data["driving"] = sketch.getDriving(index)
            data["datum"] = str(sketch.getDatum(index))
        constraints.append(data)
    return {
        "name": object_name,
        "placement": encode(sketch.Placement),
        "revision": engine.revision(doc),
        "geometry": geometry,
        "constraints": constraints,
        "fully_constrained": sketch.FullyConstrained,
        "coordinates": "sketch-local XY in mm; native arc and Angle constraint parameters are radians",
    }
