"""Structured operations shared by FreeCAD's GUI and command-line interpreters.

Do not import MCP or Pydantic here: FreeCAD uses its own Python distribution.
"""

import base64
import hashlib
import json
import math
import re
import shutil
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__


class CadError(ValueError):
    pass


def has_geometry(shape):
    return not shape.isNull() and bool(shape.Vertexes or shape.Edges or shape.Faces)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CadError("Expected a finite number")
    if not math.isfinite(value):
        raise CadError("Expected a finite number")
    return value


def positive(value):
    if number(value) <= 0:
        raise CadError("Dimension must be greater than zero")
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", value):
        raise CadError(
            "Names must start with a letter and contain only letters, digits, underscores"
        )
    return value


class Workspace:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, value, extensions):
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(self.root) or candidate == self.root:
            raise CadError("File path must be inside the configured CAD workspace")
        if candidate.suffix.lower() not in extensions:
            raise CadError("Expected extension: " + ", ".join(sorted(extensions)))
        return candidate

    def prepare_write(self, value, extensions, overwrite=False):
        path = self.path(value, extensions)
        backup = None
        if path.exists():
            if not overwrite:
                raise CadError("File exists; choose another path or explicitly set overwrite=true")
            backup_dir = self.root / "backups"
            if not backup_dir.resolve().is_relative_to(self.root):
                raise CadError("Backup directory escapes the CAD workspace")
            backup_dir.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = backup_dir / (
                path.stem + "." + stamp + "." + uuid.uuid4().hex[:8] + path.suffix
            )
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path, backup


def encode(value):
    """Bounded, JSON-safe property descriptions; never evaluate model-provided text."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if hasattr(value, "Name") and hasattr(value, "Document"):
        return {"object": value.Name, "document": value.Document.Name}
    if hasattr(value, "Base") and hasattr(value, "Rotation"):
        return {"position_mm": encode(value.Base), "quaternion": list(value.Rotation.Q)}
    if all(hasattr(value, k) for k in ("x", "y", "z")):
        return [value.x, value.y, value.z]
    if hasattr(value, "Value") and hasattr(value, "Unit"):
        return {"value": value.Value, "quantity": str(value)}
    # Some native wrappers include a new memory address on every access (Material).
    # Such addresses are not model state and must not invalidate a revision token.
    return re.sub(r"\bat (?:0x)?[0-9A-Fa-f]{6,}", "at <native>", str(value))


class Engine:
    def __init__(self, workspace, gui=False):
        import FreeCAD

        self.app = FreeCAD
        self.workspace = Workspace(workspace)
        self.gui = gui

    def document(self, name):
        doc = self.app.listDocuments().get(name)
        if doc is None:
            raise CadError("Unknown document: " + str(name))
        return doc

    def obj(self, doc, name):
        obj = doc.getObject(name)
        if obj is None:
            raise CadError("Unknown object: " + str(name))
        return obj

    def properties(self, obj):
        result = {}
        for prop in sorted(obj.PropertiesList):
            # Shape is inspected separately; Python proxies and file blobs aren't tool input.
            if prop in {"Shape", "Proxy"} or prop.startswith("_"):
                continue
            try:
                result[prop] = {
                    "type": obj.getTypeIdOfProperty(prop),
                    "value": encode(getattr(obj, prop)),
                }
            except Exception as exc:
                result[prop] = {"unavailable": str(exc)}
        return result

    def revision(self, doc):
        state = []
        for obj in doc.Objects:
            item = [obj.Name, obj.TypeId, self.properties(obj)]
            if hasattr(obj, "Shape") and not obj.Shape.isNull():
                if obj.TypeId == "App::Link":
                    # Link-array Shape getters can allocate a fresh compound per access.
                    # Its native identity hash is therefore not a model-change signal.
                    brep = obj.Shape.copy(False, False).exportBrepToString().encode("utf-8")
                    item.append(hashlib.sha256(brep).hexdigest())
                else:
                    item.append(obj.Shape.hashCode())
            if hasattr(obj, "Mesh"):
                # Wrapper addresses/counts alone do not detect mesh vertex movement.
                mesh_hash = hashlib.sha256()
                points, facets = obj.Mesh.Topology
                for point in points:
                    mesh_hash.update(struct.pack("!3d", point.x, point.y, point.z))
                for facet in facets:
                    mesh_hash.update(struct.pack("!3Q", *facet))
                item.append(mesh_hash.hexdigest())
            state.append(item)
        raw = json.dumps(state, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def check_revision(self, doc, expected_revision):
        if expected_revision is not None and expected_revision != self.revision(doc):
            raise CadError("Document changed since inspection; inspect it again before editing")

    def summary(self, obj):
        result = {
            "name": obj.Name,
            "label": obj.Label,
            "type": obj.TypeId,
            "state": list(obj.State),
            "depends_on": list(dict.fromkeys(x.Name for x in obj.OutList)),
            "expressions": [
                {"property": path, "expression": text} for path, text in obj.ExpressionEngine
            ],
        }
        if hasattr(obj, "Shape"):
            shape = obj.Shape
            result["shape"] = {"null": shape.isNull()}
            result["shape"]["empty"] = not has_geometry(shape)
            if has_geometry(shape):
                box = shape.optimalBoundingBox(False, False)
                result["shape"].update(
                    {
                        "valid": shape.isValid(),
                        "volume_mm3": shape.Volume,
                        "area_mm2": shape.Area,
                        "solids": len(shape.Solids),
                        "faces": len(shape.Faces),
                        "edges": len(shape.Edges),
                        "bounds_mm": {
                            "min": [box.XMin, box.YMin, box.ZMin],
                            "max": [box.XMax, box.YMax, box.ZMax],
                        },
                    }
                )
        if obj.isDerivedFrom("Sketcher::SketchObject"):
            result.update(
                {
                    "geometry_count": obj.GeometryCount,
                    "constraints": [str(c) for c in obj.Constraints],
                    "fully_constrained": obj.FullyConstrained,
                }
            )
        if hasattr(obj, "Mesh"):
            mesh = obj.Mesh
            box = mesh.BoundBox
            solid = mesh.isSolid()
            result["mesh"] = {
                "facets": mesh.CountFacets,
                "points": mesh.CountPoints,
                "closed": solid,
                "area_mm2": mesh.Area,
                "volume_mm3": mesh.Volume if solid else None,
                "bounds_mm": {
                    "min": [box.XMin, box.YMin, box.ZMin],
                    "max": [box.XMax, box.YMax, box.ZMax],
                },
            }
        if "CadPatternKind" in obj.PropertiesList:
            from .patterns import summary

            result["pattern"] = summary(obj)
        return result

    def call(self, method, params):
        methods = {
            "status",
            "list_documents",
            "new_document",
            "open_document",
            "inspect_document",
            "inspect_object",
            "inspect_sketch",
            "inspect_topology",
            "measure_distance",
            "import_model",
            "set_view",
            "apply_operations",
            "undo_document",
            "save_document",
            "export_model",
            "get_selection",
            "capture_view",
        }
        if method not in methods:
            raise CadError("Unsupported method: " + str(method))
        return getattr(self, method)(**params)

    def status(self):
        return {
            "plugin_version": __version__,
            "freecad_version": list(self.app.Version()),
            "mode": "live" if self.gui else "headless",
            "units": "mm, degrees",
            "workspace": str(self.workspace.root),
            "documents": self.list_documents(),
            "operations": sorted(OPERATION_KEYS),
        }

    def list_documents(self):
        return [
            {
                "name": doc.Name,
                "label": doc.Label,
                "file": doc.FileName,
                "objects": len(doc.Objects),
            }
            for doc in self.app.listDocuments().values()
        ]

    def new_document(self, name, label=None):
        identifier(name)
        if name in self.app.listDocuments():
            raise CadError("A document already has that name")
        doc = self.app.newDocument(name)
        doc.UndoMode = 1
        if label is not None:
            doc.Label = label
        return self.inspect_document(doc.Name)

    def open_document(self, path):
        source = self.workspace.path(path, {".fcstd"})
        if not source.is_file():
            raise CadError("FCStd file does not exist")
        for doc in self.app.listDocuments().values():
            if doc.FileName and Path(doc.FileName).resolve() == source:
                return self.inspect_document(doc.Name)
        doc = self.app.openDocument(str(source))
        doc.UndoMode = 1
        return self.inspect_document(doc.Name)

    def inspect_document(self, document):
        doc = self.document(document)
        return {
            "name": doc.Name,
            "label": doc.Label,
            "file": doc.FileName,
            "revision": self.revision(doc),
            "objects": [self.summary(o) for o in doc.Objects],
        }

    def inspect_object(self, document, object_name):
        doc = self.document(document)
        obj = self.obj(doc, object_name)
        return dict(self.summary(obj), properties=self.properties(obj), revision=self.revision(doc))

    def inspect_sketch(self, document, object_name):
        from .sketches import inspect

        return inspect(self, document, object_name)

    def shape(self, doc, object_name):
        obj = self.obj(doc, object_name)
        if not hasattr(obj, "Shape") or not has_geometry(obj.Shape):
            raise CadError("Object has no BREP shape; convert a closed mesh to a solid first")
        return obj.Shape

    def subshape(self, shape, subelement):
        if subelement is None:
            return shape
        match = re.fullmatch(r"(Edge|Face|Vertex)([1-9][0-9]*)", subelement)
        if not match:
            raise CadError("Subelement must be EdgeN, FaceN or VertexN from inspection")
        kind, index = match.group(1), int(match.group(2))
        items = {"Edge": shape.Edges, "Face": shape.Faces, "Vertex": shape.Vertexes}[kind]
        if index > len(items):
            raise CadError("Subelement index is outside the current shape")
        return items[index - 1]

    def inspect_topology(self, document, object_name, kind="edges", offset=0, limit=100):
        doc = self.document(document)
        shape = self.shape(doc, object_name)
        if kind not in {"edges", "faces", "vertices"}:
            raise CadError("Topology kind must be edges, faces or vertices")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 500:
            raise CadError("offset must be nonnegative; limit must be between 1 and 500")
        items = {"edges": shape.Edges, "faces": shape.Faces, "vertices": shape.Vertexes}[kind]
        prefix = {"edges": "Edge", "faces": "Face", "vertices": "Vertex"}[kind]
        result = []
        for index in range(offset, min(offset + limit, len(items))):
            item = items[index]
            entry = {"name": prefix + str(index + 1)}
            if kind == "vertices":
                entry["position_mm"] = encode(item.Point)
            else:
                box = item.optimalBoundingBox(False, False)
                entry.update(
                    {
                        "center_mm": encode(item.CenterOfMass),
                        "bounds_mm": {
                            "min": [box.XMin, box.YMin, box.ZMin],
                            "max": [box.XMax, box.YMax, box.ZMax],
                        },
                    }
                )
                if kind == "edges":
                    entry.update(
                        {
                            "length_mm": item.Length,
                            "endpoints_mm": [encode(v.Point) for v in item.Vertexes],
                        }
                    )
                    try:
                        curve = item.Curve
                    except Exception as exc:
                        entry["curve"] = "Degenerate" if item.Length == 0 else "Unavailable"
                        entry["curve_error"] = str(exc)
                        if item.Length == 0 and item.Vertexes:
                            entry["center_mm"] = encode(item.Vertexes[0].Point)
                    else:
                        entry["curve"] = type(curve).__name__
                        if hasattr(curve, "Radius"):
                            entry["radius_mm"] = curve.Radius
                else:
                    entry.update({"area_mm2": item.Area, "surface": type(item.Surface).__name__})
                    if type(item.Surface).__name__ == "Plane":
                        entry["normal"] = encode(item.normalAt(0, 0))
                    if hasattr(item.Surface, "Radius"):
                        entry["radius_mm"] = item.Surface.Radius
            result.append(entry)
        next_offset = offset + len(result)
        return {
            "object": object_name,
            "revision": self.revision(doc),
            "kind": kind,
            "total": len(items),
            "items": result,
            "next_offset": next_offset if next_offset < len(items) else None,
        }

    def measure_distance(self, document, object_a, object_b, subelement_a=None, subelement_b=None):
        doc = self.document(document)
        first = self.subshape(self.shape(doc, object_a), subelement_a)
        second = self.subshape(self.shape(doc, object_b), subelement_b)
        distance, points, _ = first.distToShape(second)
        return {
            "distance_mm": distance,
            "revision": self.revision(doc),
            "nearest_points_mm": [[encode(a), encode(b)] for a, b in points[:20]],
            "solution_count": len(points),
            "meaning": "minimum distance between the selected BREP shapes; zero does not prove clearance",
        }

    def import_model(self, document, path, name, expected_revision=None):
        return self.apply_operations(
            document, [{"op": "import_model", "path": path, "name": name}], expected_revision
        )

    def apply_operations(self, document, operations, expected_revision=None):
        doc = self.document(document)
        self.check_revision(doc, expected_revision)
        if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
            raise CadError("Provide between 1 and 100 operations")
        for op in operations:
            validate_operation(op)
        if not doc.UndoMode:
            doc.UndoMode = 1
        doc.openTransaction("Codex FreeCAD edit")
        results = []
        try:
            for op in operations:
                results.append(self.operation(doc, op))
                doc.recompute()
            for obj in doc.Objects:
                if "Invalid" in obj.State or "Error" in obj.State:
                    raise CadError("Recompute failed for " + obj.Name + ": " + str(obj.State))
                if hasattr(obj, "Shape") and not obj.Shape.isNull() and not obj.Shape.isValid():
                    raise CadError("Invalid shape: " + obj.Name)
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            doc.recompute()
            raise
        warnings = []
        if self.gui:
            import FreeCADGui

            try:
                view = FreeCADGui.getDocument(doc.Name).activeView()
                view.viewAxonometric()
                view.fitAll()
            except Exception as exc:
                # An optional view refresh cannot turn a committed edit into a failed request.
                warnings.append("Edit committed; viewport refresh failed: " + str(exc))
        return {
            "results": results,
            "document": self.inspect_document(document),
            "warnings": warnings,
        }

    def add(self, doc, type_id, name):
        identifier(name)
        if doc.getObject(name):
            raise CadError("Object already exists: " + name)
        return doc.addObject(type_id, name)

    def operation(self, doc, op):
        kind = op["op"]
        details = {}
        if kind in {"loft", "set_loft"}:
            from .features import loft

            obj = loft(self, doc, op)
        elif kind in {"mirror", "set_mirror"}:
            from .features import mirror

            obj = mirror(self, doc, op)
        elif kind in {"sweep", "set_sweep"}:
            from .features import sweep

            obj = sweep(self, doc, op)
        elif kind == "create_helix":
            from .features import helix

            obj = helix(self, doc, op)
        elif kind == "create_parameters":
            from .parameters import create

            obj = create(self, doc, op)
        elif kind in {"set_expression", "clear_expression"}:
            from .parameters import apply

            obj = apply(self, doc, op)
        elif kind == "import_model":
            source = self.workspace.path(op["path"], {".step", ".stp", ".brep", ".stl"})
            if not source.is_file():
                raise CadError("Import file does not exist")
            source_info = file_result(source, None)
            if source.suffix.lower() == ".stl":
                import Mesh

                mesh = Mesh.Mesh(str(source))
                if not mesh.CountFacets:
                    raise CadError("STL contains no mesh facets")
                obj = self.add(doc, "Mesh::Feature", op["name"])
                obj.Mesh = mesh
            else:
                import Part

                shape = Part.read(str(source))
                if not has_geometry(shape) or not shape.isValid():
                    raise CadError("Import produced an empty or invalid BREP shape")
                obj = self.add(doc, "Part::Feature", op["name"])
                obj.Shape = shape
            if file_result(source, None)["sha256"] != source_info["sha256"]:
                raise CadError("Source file changed during import; the import was rolled back")
            doc.recompute()
            return {
                "name": obj.Name,
                "type": obj.TypeId,
                "source": source_info,
                "note": "Imported geometry snapshot; original feature history and assembly metadata are not reconstructed",
            }
        elif kind == "mesh_to_solid":
            import Part

            source = self.obj(doc, op["mesh"])
            if not hasattr(source, "Mesh") or not source.Mesh.isSolid():
                raise CadError(
                    "Conversion requires a closed mesh; repair open meshes before converting"
                )
            if source.Mesh.CountFacets > 20000:
                raise CadError(
                    "Mesh conversion is limited to 20,000 facets; simplify the mesh first"
                )
            tolerance = positive(op.get("tolerance", 0.01))
            tessellation = Part.Shape()
            tessellation.makeShapeFromMesh(source.Mesh.Topology, tolerance)
            shells = tessellation.Shells
            if len(shells) != 1 or not shells[0].isClosed():
                raise CadError("Conversion must produce exactly one closed shell")
            solid = Part.makeSolid(shells[0]).removeSplitter()
            if not solid.isValid() or solid.Volume <= 0:
                raise CadError("Mesh conversion did not produce a valid positive-volume solid")
            obj = self.add(doc, "Part::Feature", op["name"])
            obj.Shape = solid
            self.hide(source)
        elif kind in {"fillet", "chamfer"}:
            base = self.obj(doc, op["base"])
            base_shape = self.shape(doc, base.Name)
            edges = self.edge_parameters(base_shape, op["edges"], op["size"])
            obj = self.add(doc, "Part::Fillet" if kind == "fillet" else "Part::Chamfer", op["name"])
            obj.Base = base
            obj.Edges = edges
            self.hide(base)
        elif kind == "set_edge_treatment":
            obj = self.obj(doc, op["object"])
            if obj.TypeId not in {"Part::Fillet", "Part::Chamfer"} or obj.Base is None:
                raise CadError("Target must be a native Part fillet or chamfer with a base object")
            obj.Edges = self.edge_parameters(
                self.shape(doc, obj.Base.Name), op["edges"], op["size"]
            )
        elif kind == "create_box":
            obj = self.add(doc, "Part::Box", op["name"])
            obj.Length, obj.Width, obj.Height = [
                positive(op[k]) for k in ("length", "width", "height")
            ]
        elif kind == "create_cylinder":
            obj = self.add(doc, "Part::Cylinder", op["name"])
            obj.Radius, obj.Height = positive(op["radius"]), positive(op["height"])
        elif kind == "create_sphere":
            obj = self.add(doc, "Part::Sphere", op["name"])
            obj.Radius = positive(op["radius"])
        elif kind == "create_body":
            obj = self.add(doc, "PartDesign::Body", op["name"])
        elif kind == "create_sketch":
            from .sketches import add_geometry

            obj = self.add(doc, "Sketcher::SketchObject", op["name"])
            if op.get("body"):
                body = self.obj(doc, op["body"])
                if body.TypeId != "PartDesign::Body":
                    raise CadError("body must identify a PartDesign::Body")
                body.addObject(obj)
            details["geometry"] = add_geometry(self, obj, op["geometry"])
        elif kind == "add_sketch_geometry":
            from .sketches import add_geometry

            obj = self.obj(doc, op["object"])
            if not obj.isDerivedFrom("Sketcher::SketchObject"):
                raise CadError("Geometry target must be a sketch")
            details["geometry"] = add_geometry(self, obj, op["geometry"])
        elif kind == "revolve":
            source = self.obj(doc, op["source"])
            self.shape(doc, source.Name)
            center = self.vector(op.get("center", [0, 0, 0]))
            axis = self.vector(op.get("axis", [0, 0, 1]))
            angle = number(op.get("angle", 360))
            solid = op.get("solid", True)
            if axis.Length == 0 or angle == 0 or abs(angle) > 360 or type(solid) is not bool:
                raise CadError(
                    "Revolution requires a nonzero axis, angle within +/-360 degrees, and boolean solid"
                )
            obj = self.add(doc, "Part::Revolution", op["name"])
            obj.Source, obj.Base, obj.Axis, obj.Angle, obj.Solid = (
                source,
                center,
                axis,
                angle,
                solid,
            )
            self.hide(source)
        elif kind in {
            "linear_pattern",
            "circular_pattern",
            "set_linear_pattern",
            "set_circular_pattern",
        }:
            from .patterns import apply

            obj = apply(self, doc, op)
        elif kind == "add_constraint":
            import Sketcher

            obj = self.obj(doc, op["object"])
            if not obj.isDerivedFrom("Sketcher::SketchObject"):
                raise CadError("Constraint target must be a sketch")
            if op["type"] not in CONSTRAINT_TYPES:
                raise CadError("Unsupported sketch constraint")
            index = obj.addConstraint(Sketcher.Constraint(op["type"], *op["args"]))
            if obj.solve() != 0:
                raise CadError("Sketch constraint solver rejected the constraint")
            return {"name": obj.Name, "constraint_index": index}
        elif kind == "set_datum":
            obj = self.obj(doc, op["object"])
            index = op["constraint_index"]
            if not obj.isDerivedFrom("Sketcher::SketchObject"):
                raise CadError("Datum target must be a sketch")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise CadError("constraint_index must be a nonnegative integer")
            from .parameters import expression_paths, numeric_path

            path = numeric_path(obj, "Constraints[" + str(index) + "]", target=True)
            if path in expression_paths(obj):
                raise CadError("Constraint has an expression; edit its driving parameter instead")
            obj.setDatum(index, self.app.Units.Quantity(op["value"]))
            if obj.solve() != 0:
                raise CadError("Sketch solver rejected the datum")
        elif kind in {"pad", "pocket"}:
            body = self.obj(doc, op["body"])
            sketch = self.obj(doc, op["sketch"])
            if body.TypeId != "PartDesign::Body" or sketch not in body.Group:
                raise CadError("Profile sketch must belong to the specified PartDesign body")
            obj = self.add(
                doc, "PartDesign::Pad" if kind == "pad" else "PartDesign::Pocket", op["name"]
            )
            body.addObject(obj)
            obj.Profile = sketch
            obj.Length = positive(op["length"])
            self.hide(sketch)
        elif kind == "boolean":
            type_id = {"cut": "Part::Cut", "fuse": "Part::Fuse", "common": "Part::Common"}[
                op["kind"]
            ]
            base, tool = self.obj(doc, op["base"]), self.obj(doc, op["tool"])
            if base == tool:
                raise CadError("Boolean operands must be different objects")
            obj = self.add(doc, type_id, op["name"])
            obj.Base, obj.Tool = base, tool
            self.hide(base, tool)
        elif kind == "set_property":
            obj = self.obj(doc, op["object"])
            prop = op["property"]
            if "CadPatternKind" in obj.PropertiesList and prop not in {"Label", "Visibility"}:
                raise CadError(
                    "Use set_linear_pattern or set_circular_pattern for managed pattern parameters"
                )
            if prop not in obj.PropertiesList or obj.getTypeIdOfProperty(prop) not in SCALAR_TYPES:
                raise CadError(
                    "Only scalar dimensional, numeric, boolean and Label properties are editable"
                )
            if obj.getTypeIdOfProperty(prop) == "App::PropertyString" and prop != "Label":
                raise CadError("Only Label is editable as a string")
            value = op["value"]
            prop_type = obj.getTypeIdOfProperty(prop)
            if prop_type == "App::PropertyBool":
                if not isinstance(value, bool):
                    raise CadError("Expected a boolean")
            elif prop_type == "App::PropertyString":
                if not isinstance(value, str):
                    raise CadError("Expected a string label")
            elif prop_type == "App::PropertyInteger":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise CadError("Expected an integer")
            elif isinstance(value, str):
                value = self.app.Units.Quantity(value)
                number(value.Value)
            else:
                number(value)
            if any(path == prop or path.startswith(prop + ".") for path, _ in obj.ExpressionEngine):
                raise CadError("Property has an expression; edit its driving parameter instead")
            setattr(obj, prop, value)
        elif kind == "set_placement":
            obj = self.obj(doc, op["object"])
            if any(path.lstrip(".").startswith("Placement.") for path, _ in obj.ExpressionEngine):
                raise CadError(
                    "Placement has an expression; edit or clear its driving expression first"
                )
            axis = self.vector(op.get("axis", [0, 0, 1]))
            angle = number(op.get("angle", 0))
            if axis.Length == 0:
                raise CadError("Rotation axis cannot be zero")
            obj.Placement = self.app.Placement(
                self.vector(op["position"]), self.app.Rotation(axis, angle)
            )
        elif kind == "delete_object":
            obj = self.obj(doc, op["object"])
            if obj.InList:
                raise CadError("Object has dependents; remove those explicitly first")
            doc.removeObject(obj.Name)
            return {"deleted": op["object"]}
        else:
            raise CadError("Unsupported operation")
        if op.get("label") is not None:
            obj.Label = op["label"]
        doc.recompute()
        # Empty solid features usually mean an invalid profile or impossible boolean.
        if (
            kind
            in {
                "pad",
                "pocket",
                "boolean",
                "fillet",
                "chamfer",
                "set_edge_treatment",
                "mesh_to_solid",
                "revolve",
                "linear_pattern",
                "circular_pattern",
                "set_linear_pattern",
                "set_circular_pattern",
                "loft",
                "set_loft",
                "mirror",
                "set_mirror",
                "sweep",
                "set_sweep",
                "create_helix",
            }
            and obj.Shape.isNull()
        ):
            raise CadError("Operation produced an empty shape: " + obj.Name)
        if kind == "revolve" and obj.Solid and (not obj.Shape.Solids or obj.Shape.Volume <= 0):
            raise CadError(
                "Revolution did not produce a positive-volume solid; check the closed profile and axis"
            )
        if (
            kind in {"loft", "set_loft", "sweep", "set_sweep"}
            and obj.Solid
            and (len(obj.Shape.Solids) != 1 or obj.Shape.Volume <= 0)
        ):
            raise CadError("Feature did not produce exactly one positive-volume solid")
        return {"name": obj.Name, "type": obj.TypeId, **details}

    def edge_parameters(self, shape, edges, size):
        size = positive(size)
        if not isinstance(edges, list) or not 1 <= len(edges) <= 500:
            raise CadError("Select between 1 and 500 edges")
        if any(not isinstance(edge, str) for edge in edges) or len(set(edges)) != len(edges):
            raise CadError("Edge names must be unique strings")
        result = []
        for edge in edges:
            if not re.fullmatch(r"Edge[1-9][0-9]*", edge):
                raise CadError("Use EdgeN names returned by inspect_topology")
            self.subshape(shape, edge)
            result.append((int(edge[4:]), size, size))
        return result

    def hide(self, *objects):
        # Native Visibility is stored in FCStd even when no ViewProvider is loaded.
        for obj in objects:
            if "Visibility" in obj.PropertiesList:
                obj.Visibility = False

    def vector(self, values):
        if not isinstance(values, (list, tuple)) or len(values) not in {2, 3}:
            raise CadError("Expected a 2D or 3D vector")
        return self.app.Vector(*([number(v) for v in values] + ([0] if len(values) == 2 else [])))

    def undo_document(self, document, expected_revision=None):
        doc = self.document(document)
        self.check_revision(doc, expected_revision)
        if not doc.UndoCount:
            raise CadError("No transaction available to undo")
        doc.undo()
        doc.recompute()
        return self.inspect_document(document)

    def save_document(self, document, path, overwrite=False):
        doc = self.document(document)
        target, backup = self.workspace.prepare_write(path, {".fcstd"}, overwrite)
        doc.recompute()
        doc.saveAs(str(target))
        return file_result(target, backup)

    def export_model(self, document, objects, path, overwrite=False):
        doc = self.document(document)
        if not objects:
            raise CadError("Select at least one object to export")
        selected = [self.obj(doc, name) for name in objects]
        target = self.workspace.path(path, {".step", ".stp", ".stl", ".brep"})
        doc.recompute()
        shapes = []
        for obj in selected:
            if hasattr(obj, "Shape") and has_geometry(obj.Shape):
                if not obj.Shape.isValid() or (
                    target.suffix.lower() == ".stl" and not obj.Shape.Faces
                ):
                    raise CadError("Export requires valid shapes and STL requires faces")
                shapes.append(obj.Shape)
            elif hasattr(obj, "Mesh") and obj.Mesh.CountFacets:
                if target.suffix.lower() != ".stl":
                    raise CadError("Convert meshes to BREP solids before STEP/BREP export")
            else:
                raise CadError("Object has no exportable geometry: " + obj.Name)
        target, backup = self.workspace.prepare_write(
            path, {".step", ".stp", ".stl", ".brep"}, overwrite
        )
        if target.suffix.lower() in {".step", ".stp"}:
            import Import

            Import.export(selected, str(target))
        elif target.suffix.lower() == ".stl":
            import Mesh

            Mesh.export(selected, str(target))
        else:
            import Part

            # Part.export silently omits App::Link arrays in FreeCAD 1.0.2.
            # Export their evaluated geometry directly so no instances are lost.
            Part.makeCompound(shapes).exportBrep(str(target))
        return file_result(target, backup)

    def get_selection(self):
        if not self.gui:
            raise CadError("Selection requires the live GUI backend")
        import FreeCADGui

        return [
            {
                "document": s.DocumentName,
                "object": s.ObjectName,
                "subelements": list(s.SubElementNames),
            }
            for s in FreeCADGui.Selection.getSelectionEx()
        ]

    def set_view(self, document, orientation="isometric", fit_all=True):
        if not self.gui:
            raise CadError("View control requires the live GUI backend")
        import FreeCADGui

        self.document(document)
        methods = {
            "isometric": "viewAxonometric",
            "top": "viewTop",
            "bottom": "viewBottom",
            "front": "viewFront",
            "rear": "viewRear",
            "left": "viewLeft",
            "right": "viewRight",
        }
        if orientation not in methods or type(fit_all) is not bool:
            raise CadError("Choose a standard view and a boolean fit_all value")
        view = FreeCADGui.getDocument(document).activeView()
        getattr(view, methods[orientation])()
        if fit_all:
            view.fitAll()
        return {"document": document, "orientation": orientation, "fit_all": fit_all}

    def capture_view(self, document, width=1200, height=900):
        if not self.gui:
            raise CadError("Viewport capture requires the live GUI backend")
        import FreeCADGui

        self.document(document)
        if (
            not isinstance(width, int)
            or not isinstance(height, int)
            or not (64 <= width <= 2048 and 64 <= height <= 2048)
        ):
            raise CadError("Image dimensions must be integers between 64 and 2048")
        target = self.workspace.root / ("view-" + uuid.uuid4().hex + ".png")
        view = FreeCADGui.getDocument(document).activeView()
        view.saveImage(str(target), width, height, "White")
        data = base64.b64encode(target.read_bytes()).decode("ascii")
        return {"path": str(target), "mime_type": "image/png", "data": data}


def file_result(path, backup):
    return {
        "path": str(path),
        "backup": str(backup) if backup else None,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


SCALAR_TYPES = {
    "App::PropertyLength",
    "App::PropertyDistance",
    "App::PropertyAngle",
    "App::PropertyFloat",
    "App::PropertyFloatConstraint",
    "App::PropertyInteger",
    "App::PropertyBool",
    "App::PropertyString",
    "App::PropertyQuantity",
    "App::PropertyArea",
    "App::PropertyVolume",
    "App::PropertyPercent",
}
CONSTRAINT_TYPES = {
    "Coincident",
    "Horizontal",
    "Vertical",
    "Distance",
    "DistanceX",
    "DistanceY",
    "Radius",
    "Diameter",
    "Equal",
    "Parallel",
    "Perpendicular",
    "Tangent",
    "Angle",
}
OPERATION_KEYS = {
    "create_helix": ({"name", "pitch", "height", "radius"}, {"angle", "left_handed", "label"}),
    "sweep": (
        {"name", "profiles", "path"},
        {"path_edges", "solid", "frenet", "transition", "label"},
    ),
    "set_sweep": ({"object", "profiles", "path"}, {"path_edges", "solid", "frenet", "transition"}),
    "loft": ({"name", "profiles"}, {"solid", "ruled", "label"}),
    "set_loft": ({"object", "profiles"}, {"solid", "ruled"}),
    "mirror": ({"name", "source"}, {"point", "normal", "label"}),
    "set_mirror": ({"object"}, {"point", "normal"}),
    "create_parameters": ({"name", "parameters"}, {"label"}),
    "set_expression": ({"object", "property", "expression"}, set()),
    "clear_expression": ({"object", "property"}, set()),
    "add_sketch_geometry": ({"object", "geometry"}, set()),
    "revolve": ({"name", "source"}, {"center", "axis", "angle", "solid", "label"}),
    "linear_pattern": ({"name", "source", "count", "step"}, {"label"}),
    "circular_pattern": ({"name", "source", "count"}, {"center", "axis", "angle", "label"}),
    "set_linear_pattern": ({"object", "count", "step"}, set()),
    "set_circular_pattern": ({"object", "count"}, {"center", "axis", "angle"}),
    "import_model": ({"name", "path"}, set()),
    "mesh_to_solid": ({"name", "mesh"}, {"tolerance", "label"}),
    "fillet": ({"name", "base", "edges", "size"}, {"label"}),
    "chamfer": ({"name", "base", "edges", "size"}, {"label"}),
    "set_edge_treatment": ({"object", "edges", "size"}, set()),
    "create_box": ({"name", "length", "width", "height"}, {"label"}),
    "create_cylinder": ({"name", "radius", "height"}, {"label"}),
    "create_sphere": ({"name", "radius"}, {"label"}),
    "create_body": ({"name"}, {"label"}),
    "create_sketch": ({"name", "geometry"}, {"body", "label"}),
    "add_constraint": ({"object", "type", "args"}, set()),
    "set_datum": ({"object", "constraint_index", "value"}, set()),
    "pad": ({"name", "body", "sketch", "length"}, {"label"}),
    "pocket": ({"name", "body", "sketch", "length"}, {"label"}),
    "boolean": ({"name", "kind", "base", "tool"}, {"label"}),
    "set_property": ({"object", "property", "value"}, set()),
    "set_placement": ({"object", "position"}, {"axis", "angle"}),
    "delete_object": ({"object"}, set()),
}


def validate_operation(op):
    if not isinstance(op, dict) or op.get("op") not in OPERATION_KEYS:
        raise CadError("Unknown operation")
    required, optional = OPERATION_KEYS[op["op"]]
    if required - op.keys() or op.keys() - required - optional - {"op"}:
        raise CadError("Missing or unexpected fields for " + op["op"])
    if op["op"] == "boolean" and op["kind"] not in {"cut", "fuse", "common"}:
        raise CadError("Boolean kind must be cut, fuse or common")
