"""Bounded parameter studies on owned hidden copies; no source transactions are managed here."""

import uuid
from contextlib import contextmanager

from codex_freecad.engine import CadError
from codex_freecad.parameters import NUMERIC_TYPES


def numeric_driver(engine, doc, name, prop):
    driver = engine.obj(doc, name)
    if prop not in driver.PropertiesList or driver.getTypeIdOfProperty(prop) not in NUMERIC_TYPES:
        raise CadError("Study driver must be a supported numeric scalar property")
    if "ReadOnly" in driver.getPropertyStatus(prop):
        raise CadError("Study driver property is read-only")
    return driver


def validate_outputs(engine, doc, names):
    if len(set(names)) != len(names):
        raise CadError("Study output objects must be unique")
    if len(doc.Objects) > 500:
        raise CadError("Parameter studies support documents with at most 500 objects")
    for obj in doc.Objects:
        if any(other.Document != doc for other in obj.OutList):
            raise CadError("Parameter studies require same-document dependencies")
    for name in names:
        obj = engine.obj(doc, name)
        parent = obj.getParentGeoFeatureGroup()
        if parent is not None and (
            parent.TypeId != "Assembly::AssemblyObject" or not parent.Placement.isIdentity()
        ):
            raise CadError("Select top-level output solids or root identity assembly components")
        engine.shape(doc, name)


def validate(engine, doc, arguments):
    numeric_driver(engine, doc, arguments["object"], arguments["property"])
    validate_outputs(engine, doc, arguments["objects"])
    if len(arguments["objects"]) * len(arguments["values"]) > 200:
        raise CadError("Parameter studies are limited to 200 object-configuration measurements")


@contextmanager
def hidden_copy(engine, doc):
    original_active = engine.app.ActiveDocument
    clone = engine.app.newDocument("ParameterStudy" + uuid.uuid4().hex[:12], hidden=True)
    try:
        clone.copyObject(list(doc.Objects), True)
        clone.recompute()
        for obj in clone.Objects:
            if any(other.Document != clone for other in obj.OutList):
                raise CadError("Native copy retained an external dependency")
        yield clone
    finally:
        engine.app.closeDocument(clone.Name)
        if original_active is not None and original_active.Name in engine.app.listDocuments():
            engine.app.setActiveDocument(original_active.Name)


def check_recompute(doc):
    doc.recompute()
    for obj in doc.Objects:
        if "Invalid" in obj.State or "Error" in obj.State:
            raise CadError("Recompute failed for " + obj.Name)


def measure(engine, doc, name, density):
    shape = engine.shape(doc, name)
    if not shape.isValid() or not shape.Solids or shape.Volume <= 0:
        raise CadError("Sweep outputs require valid positive-volume BREP solids: " + name)
    box = shape.optimalBoundingBox(False, False)
    result = {
        "object": name,
        "volume_mm3": shape.Volume,
        "area_mm2": shape.Area,
        "solids": len(shape.Solids),
        "bounds_mm": {
            "min": [box.XMin, box.YMin, box.ZMin],
            "max": [box.XMax, box.YMax, box.ZMax],
        },
    }
    if density is not None:
        result["mass_kg"] = shape.Volume * density * 1e-9
    return result


def evaluate(engine, doc, arguments, snapshots=False):
    validate(engine, doc, arguments)
    frames, shapes = [], []
    with hidden_copy(engine, doc) as clone:
        for index, value in enumerate(arguments["values"]):
            try:
                engine.operation(
                    clone,
                    {
                        "op": "set_property",
                        "object": arguments["object"],
                        "property": arguments["property"],
                        "value": value,
                    },
                )
                check_recompute(clone)
                measurements = [
                    measure(engine, clone, name, arguments.get("density_kg_m3"))
                    for name in arguments["objects"]
                ]
                frames.append(
                    {
                        "index": index,
                        "value": value,
                        "objects": measurements,
                        "total_volume_mm3": sum(row["volume_mm3"] for row in measurements),
                    }
                )
                if snapshots:
                    shapes.append(
                        [engine.shape(clone, name).copy() for name in arguments["objects"]]
                    )
            except Exception as exc:
                raise CadError(f"Parameter sample {index} (value={value}) failed: {exc}") from exc
    driver = engine.obj(doc, arguments["object"])
    return {
        "object": driver.Name,
        "property": arguments["property"],
        "property_type": driver.getTypeIdOfProperty(arguments["property"]),
        "frames": frames,
        "scope": "Discrete native recomputes on a hidden dependency copy; source parameters and Undo are preserved. Numeric quantities use native base units (mm/degrees). No collision, strength or optimization claim.",
    }, shapes


def parameter_sweep(engine, doc, arguments):
    report, _ = evaluate(engine, doc, arguments)
    return report


def preview_changes(engine, doc, arguments):
    from .preview import preview

    return preview(engine, doc, arguments)


def create_variants(engine, doc, arguments):
    report, shapes = evaluate(engine, doc, arguments, snapshots=True)
    group = engine.add(doc, "App::DocumentObjectGroup", arguments["name"])
    group.addProperty("App::PropertyLink", "StudyDriver", "Parameter study")
    group.StudyDriver = engine.obj(doc, arguments["object"])
    group.addProperty("App::PropertyString", "StudyProperty", "Parameter study")
    group.StudyProperty = arguments["property"]
    group.addProperty("App::PropertyFloatList", "StudyValues", "Parameter study")
    group.StudyValues = arguments["values"]
    outputs = []
    for frame, frame_shapes in zip(report["frames"], shapes, strict=True):
        names = []
        for index, (name, shape) in enumerate(zip(arguments["objects"], frame_shapes, strict=True)):
            snapshot = engine.add(
                doc, "Part::Feature", f"{group.Name}_{frame['index'] + 1:03}_{index + 1:02}"
            )
            snapshot.Shape = shape
            snapshot.Label = f"{name} ({arguments['property']}={frame['value']:g})"
            snapshot.addProperty("App::PropertyLink", "StudySource", "Parameter study")
            snapshot.StudySource = engine.obj(doc, name)
            snapshot.addProperty("App::PropertyFloat", "StudyValue", "Parameter study")
            snapshot.StudyValue = frame["value"]
            group.addObject(snapshot)
            names.append(snapshot.Name)
        outputs.append({"index": frame["index"], "value": frame["value"], "objects": names})
    return {
        "name": group.Name,
        "variants": outputs,
        "measurements": report,
        "snapshot_scope": "Frozen evaluated BREP snapshots with provenance links; later source edits do not regenerate variants.",
    }
