"""Explicit-selection BOMs; persisted metadata and spreadsheets use native properties only."""

import csv
import io
import math

from codex_freecad.engine import CadError, number

FIELDS = {
    "part_number": ("BomPartNumber", "App::PropertyString"),
    "description": ("BomDescription", "App::PropertyString"),
    "material": ("BomMaterial", "App::PropertyString"),
    "density_kg_m3": ("BomDensityKgM3", "App::PropertyFloat"),
}
HEADERS = (
    "Source",
    "Part number",
    "Description",
    "Material",
    "Quantity",
    "Solids per item",
    "Volume each (mm3)",
    "Total volume (mm3)",
    "Density (kg/m3)",
    "Total mass (kg)",
)


def source_of(obj):
    source = obj
    seen = set()
    while source.TypeId == "App::Link":
        if source.Name in seen:
            raise CadError("BOM link source cycle")
        seen.add(source.Name)
        if source.Scale != 1 or list(source.ScaleVector) != [1, 1, 1]:
            raise CadError("BOM does not support scaled link instances")
        source = source.LinkedObject
        if source is None or isinstance(source, tuple):
            raise CadError("BOM requires whole-object links")
    if source is None or source.Document != obj.Document:
        raise CadError("BOM sources must belong to the same document")
    return source


def selected(engine, doc, names):
    if len(set(names)) != len(names):
        raise CadError("BOM selections must be unique")
    items = []
    seen = set()
    for name in names:
        obj = engine.obj(doc, name)
        if obj.TypeId == "Assembly::AssemblyObject":
            from codex_freecad.assemblies import assembly, components

            values = components(assembly(engine, doc, name))
            if not values:
                raise CadError("Assembly has no supported components")
        else:
            values = [obj]
        for item in values:
            if item.Name in seen:
                raise CadError("BOM selection repeats a component through multiple selections")
            parent = item.getParentGeoFeatureGroup()
            if parent is not None and (
                parent.TypeId != "Assembly::AssemblyObject" or not parent.Placement.isIdentity()
            ):
                raise CadError("Select top-level parts or components of a root identity assembly")
            seen.add(item.Name)
            items.append(item)
    if len(items) > 200:
        raise CadError("BOM selection is limited to 200 part objects")
    return items


def literal(value):
    """Neutralize spreadsheet/CSV formulas in model-provided text."""
    value = str(value)
    unsafe = value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    return "'" + value if unsafe else value


def table_values(row):
    return [
        row["source"],
        row["part_number"],
        row["description"],
        row["material"],
        row["quantity"],
        row["solids_per_item"],
        row["volume_each_mm3"],
        row["total_volume_mm3"],
        row["density_kg_m3"],
        row["total_mass_kg"],
    ]


def inspect(engine, doc, arguments):
    rows = {}
    for obj in selected(engine, doc, arguments["objects"]):
        source = source_of(obj)
        shape = engine.shape(doc, obj.Name)
        if not shape.isValid() or not shape.Solids or shape.Volume <= 0:
            raise CadError("BOM items require valid positive-volume BREP solids")
        count = int(obj.ElementCount) if obj.TypeId == "App::Link" and obj.ElementCount else 1
        if len(shape.Solids) % count:
            raise CadError("Link array solid count does not match its instance count")
        if not math.isclose(
            shape.Volume / count, engine.shape(doc, source.Name).Volume, rel_tol=1e-8
        ):
            raise CadError(
                "BOM requires identical unscaled source instances; nested arrays are unsupported"
            )
        density = number(getattr(source, "BomDensityKgM3", 0))
        if not 0 <= density <= 1000000:
            raise CadError("BOM density must be between zero and 1000000 kg/m3")
        if source.Name not in rows:
            rows[source.Name] = {
                "source": source.Name,
                "label": source.Label,
                "part_number": getattr(source, "BomPartNumber", "") or source.Name,
                "description": getattr(source, "BomDescription", ""),
                "material": getattr(source, "BomMaterial", ""),
                "quantity": 0,
                "solids_per_item": len(shape.Solids) // count,
                "volume_each_mm3": shape.Volume / count,
                "total_volume_mm3": 0,
                "density_kg_m3": density or None,
                "total_mass_kg": None,
                "instances": [],
            }
        row = rows[source.Name]
        row["quantity"] += count
        row["total_volume_mm3"] += shape.Volume
        row["instances"].append(obj.Name)
        if density:
            row["total_mass_kg"] = row["total_volume_mm3"] * density * 1e-9
    ordered = [rows[name] for name in sorted(rows)]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(HEADERS)
    for row in ordered:
        writer.writerow([literal(x) if isinstance(x, str) else x for x in table_values(row)])
    numbers = [row["part_number"] for row in ordered]
    unknown = [row["source"] for row in ordered if row["density_kg_m3"] is None]
    return {
        "rows": ordered,
        "quantity": sum(row["quantity"] for row in ordered),
        "total_volume_mm3": sum(row["total_volume_mm3"] for row in ordered),
        "total_mass_kg": None if unknown else sum(row["total_mass_kg"] for row in ordered),
        "unknown_density_sources": unknown,
        "duplicate_part_numbers": sorted({x for x in numbers if numbers.count(x) > 1}),
        "csv": stream.getvalue(),
        "scope": "Explicit selected instances grouped by native source identity. Compound solids count as one part; overlaps are not subtracted. Spreadsheet output is a refreshable snapshot.",
    }


def set_metadata(engine, doc, arguments):
    source = source_of(engine.obj(doc, arguments["object"]))
    fields = arguments.keys() & FIELDS.keys()
    if not fields:
        raise CadError("Provide at least one metadata field")
    for field in sorted(fields):
        name, kind = FIELDS[field]
        if name in source.PropertiesList and source.getTypeIdOfProperty(name) != kind:
            raise CadError("Existing BOM metadata has an incompatible property type: " + name)
        if any(path.lstrip(".") == name for path, _ in source.ExpressionEngine):
            raise CadError("BOM metadata has an expression; edit its driving parameter instead")
        if name not in source.PropertiesList:
            source.addProperty(kind, name, "Bill of materials")
        setattr(source, name, arguments[field])
    return {"source": source.Name, "updated": sorted(fields)}


def fill(sheet, report):
    # clearAll also discards dynamic provenance properties in FreeCAD 1.0.
    for cell in sheet.getNonEmptyCells():
        sheet.clear(cell)
    for index, values in enumerate([HEADERS, *(table_values(row) for row in report["rows"])], 1):
        for column, value in enumerate(values):
            if value is not None:
                # A leading apostrophe forces literal text in native Spreadsheet cells.
                sheet.set(
                    chr(65 + column) + str(index),
                    "'" + value if isinstance(value, str) else str(value),
                )
    sheet.setStyle("A1:J1", "bold", "add")


def create_sheet(engine, doc, arguments):
    report = inspect(engine, doc, arguments)
    sheet = engine.add(doc, "Spreadsheet::Sheet", arguments["name"])
    sheet.addProperty("App::PropertyLinkList", "BomObjects", "Bill of materials")
    sheet.BomObjects = [engine.obj(doc, name) for name in arguments["objects"]]
    sheet.setEditorMode("BomObjects", 1)
    fill(sheet, report)
    return {"name": sheet.Name, "rows": len(report["rows"]), "quantity": report["quantity"]}


def refresh_sheet(engine, doc, arguments):
    sheet = engine.obj(doc, arguments["sheet"])
    if sheet.TypeId != "Spreadsheet::Sheet" or "BomObjects" not in sheet.PropertiesList:
        raise CadError("Select a BOM spreadsheet created by bom.create_sheet")
    names = [obj.Name for obj in sheet.BomObjects if obj is not None]
    if not names:
        raise CadError("BOM source selection is empty")
    report = inspect(engine, doc, {"objects": names})
    fill(sheet, report)
    return {"name": sheet.Name, "rows": len(report["rows"]), "quantity": report["quantity"]}
