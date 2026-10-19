"""Native TechDraw objects and deterministic SVG sheets without GUI export functions."""

import hashlib
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from codex_freecad.engine import CadError, number

PAPERS = {"A4": (297, 210), "A3": (420, 297)}
# Rows map world coordinates to view-plane X/Y/Z, with Z pointing toward the viewer.
VIEWS = {
    "front": ((1, 0, 0), (0, 0, 1), (0, -1, 0), (0.28, 0.34)),
    "top": ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0.28, 0.72)),
    "right": ((0, 1, 0), (0, 0, 1), (1, 0, 0), (0.73, 0.34)),
}
SCALES = (100, 50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)
SVG = "http://www.w3.org/2000/svg"


def core_application(engine):
    from PySide import QtCore

    if QtCore.QCoreApplication.instance() is None:
        # A core event dispatcher has no windows or desktop input. Native HLR watchers need it.
        # Keep ownership in the stable FreeCAD module across extension generation reloads.
        engine.app._cad_drawing_core_application = QtCore.QCoreApplication(["FreeCADMCPServer"])


def sources(engine, doc, names):
    import Part

    if not names or len(names) > 20 or len(set(names)) != len(names):
        raise CadError("Select 1 to 20 distinct drawing source solids")
    shapes = []
    digest = hashlib.sha256()
    for name in names:
        obj = engine.obj(doc, name)
        parent = obj.getParentGeoFeatureGroup()
        if parent is not None and (
            parent.TypeId != "Assembly::AssemblyObject" or not parent.Placement.isIdentity()
        ):
            raise CadError("Drawing sources must be top-level solids or root identity components")
        if any(other.Document != doc for other in obj.OutList):
            raise CadError("Drawing sources require same-document dependencies")
        shape = engine.shape(doc, name)
        if not shape.isValid() or not shape.Solids or shape.Volume <= 0:
            raise CadError("Drawing sources require valid positive-volume solids")
        shapes.append(shape.copy(False, False))
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(shapes[-1].exportBrepToString().encode("utf-8"))
    if sum(len(shape.Edges) for shape in shapes) > 5000:
        raise CadError("Drawings are limited to 5000 source edges")
    return Part.makeCompound(shapes), digest.hexdigest()


def projection(engine, shape, orientation):
    matrix = engine.app.Matrix()
    for row, values in enumerate(VIEWS[orientation][:3], 1):
        for column, value in enumerate(values, 1):
            setattr(matrix, f"A{row}{column}", value)
    result = shape.copy(False, False)
    result.transformShape(matrix)
    return result, result.optimalBoundingBox(False, False)


def layout(engine, shape, paper, orientations, requested):
    if paper not in PAPERS or not orientations or len(set(orientations)) != len(orientations):
        raise CadError("Invalid drawing paper or repeated view orientations")
    if any(name not in VIEWS for name in orientations):
        raise CadError("Drawing orientations are front, top and right")
    width, height = PAPERS[paper]
    boxes = {name: projection(engine, shape, name)[1] for name in orientations}
    fit = min(
        min((width * 0.40 - 24) / box.XLength, (height * 0.34 - 24) / box.YLength)
        for box in boxes.values()
    )
    if requested:
        scale = number(requested)
        if not 0.01 <= scale <= 100 or scale > fit + 1e-9:
            raise CadError("Requested drawing scale does not fit the sheet")
    else:
        scale = next((value for value in SCALES if value <= fit), None)
        if scale is None:
            raise CadError("Drawing cannot fit at the minimum supported scale of 0.01")
    return width, height, scale, boxes


def page_object(engine, doc, name):
    page = engine.obj(doc, name)
    if page.TypeId != "TechDraw::DrawPage" or getattr(page, "DrawingVersion", None) != 1:
        raise CadError("Select a drawing created by drawings.create_sheet")
    return page


def property_value(obj, kind, name, value):
    obj.addProperty(kind, name, "CAD drawing")
    setattr(obj, name, value)


def build_dimensions(engine, doc, page, view, box, width, height, scale):
    from PySide import QtCore

    for name in getattr(view, "DrawingDimensions", []):
        dim = doc.getObject(name)
        if dim is not None:
            if dim.TypeId != "TechDraw::DrawViewDimExtent" or dim not in page.Views:
                raise CadError("Drawing dimension ownership no longer matches the sheet")
            doc.removeObject(name)
    dimensions = []
    for axis in (0, 1):
        # Native HLR/face finding completes through Qt queued signals, including in FreeCADCmd.
        view.enforceRecompute()
        doc.recompute()
        dim = engine.add(
            doc, "TechDraw::DrawViewDimExtent", view.Name + ("Height" if axis else "Width")
        )
        dim.Type = "DistanceY" if axis else "DistanceX"
        dim.DirExtent = axis
        dim.Source = (view, [""])
        dim.References2D = [(view, [""])]
        page.addView(dim)
        dim.FormatSpec = "%.3f"
        dim.Visibility = True
        dim.X = view.X.Value + (box.XLength * scale / 2 + 8 if axis else 0)
        dim.Y = view.Y.Value + (0 if axis else -box.YLength * scale / 2 - 8)
        dim.enforceRecompute()
        doc.recompute()
        expected = box.YLength if axis else box.XLength
        deadline = time.monotonic() + 10
        while not math.isclose(dim.getRawValue(), expected, rel_tol=1e-7, abs_tol=1e-6):
            if time.monotonic() >= deadline:
                raise CadError(
                    f"Native extent {dim.Name} is {dim.getRawValue()} mm; expected {expected} mm after projection timeout"
                )
            # Process projection completion, without consuming pointer/keyboard events.
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
            time.sleep(0.005)
        dimensions.append(dim.Name)
    view.DrawingDimensions = dimensions


def refresh_sheet(engine, doc, arguments):
    core_application(engine)
    page = page_object(engine, doc, arguments["page"])
    names = list(page.DrawingSourceNames)
    if [obj.Name for obj in page.DrawingSources] != names:
        raise CadError("Drawing source links changed or were removed; create a new sheet")
    shape, fingerprint = sources(engine, doc, names)
    # Evaluate compact link arrays and compounds explicitly: native TechDraw 1.0
    # does not consistently expand them when they are used directly as Source.
    page.DrawingProjectionSource.Shape = shape
    views = [engine.obj(doc, name) for name in page.DrawingViews]
    orientations = [view.DrawingOrientation for view in views]
    width, height, scale, boxes = layout(
        engine, shape, page.DrawingPaper, orientations, page.DrawingRequestedScale
    )
    page.Scale = scale
    page.KeepUpdated = True
    page.Visibility = True
    for view in views:
        orientation = view.DrawingOrientation
        view.Source = [page.DrawingProjectionSource]
        view.Direction = engine.app.Vector(*VIEWS[orientation][2])
        view.XDirection = engine.app.Vector(*VIEWS[orientation][0])
        view.ScaleType = "Custom"
        view.Scale = scale
        view.Visibility = True
        view.X = width * VIEWS[orientation][3][0]
        view.Y = height * VIEWS[orientation][3][1]
        build_dimensions(engine, doc, page, view, boxes[orientation], width, height, scale)
    doc.recompute()
    measurements = []
    for view in views:
        box = boxes[view.DrawingOrientation]
        values = []
        for name, expected in zip(view.DrawingDimensions, [box.XLength, box.YLength], strict=True):
            value = engine.obj(doc, name).getRawValue()
            value = number(getattr(value, "Value", value))
            if not math.isclose(value, expected, rel_tol=1e-7, abs_tol=1e-6):
                raise CadError(
                    f"Native drawing extent {name} is {value} mm; expected {expected} mm"
                )
            values.append(value)
        measurements.append({"view": view.Name, "width_mm": values[0], "height_mm": values[1]})
    page.DrawingFingerprint = fingerprint
    return {
        "page": page.Name,
        "paper": page.DrawingPaper,
        "scale": scale,
        "views": [view.Name for view in views],
        "dimensions": [name for view in views for name in view.DrawingDimensions],
        "measurements": measurements,
    }


def create_sheet(engine, doc, arguments):
    core_application(engine)
    import TechDraw  # noqa: F401 -- load persistent native object types

    shape, _ = sources(engine, doc, arguments["objects"])
    layout(engine, shape, arguments["paper"], arguments["views"], arguments.get("scale", 0))
    template_path = (
        Path(engine.app.getResourceDir())
        / "Mod/TechDraw/Templates"
        / (arguments["paper"] + "_Landscape_blank.svg")
    )
    if not template_path.is_file():
        raise CadError("FreeCAD's landscape blank TechDraw template is unavailable")
    page = engine.add(doc, "TechDraw::DrawPage", arguments["name"])
    template = engine.add(doc, "TechDraw::DrawSVGTemplate", arguments["name"] + "Template")
    template.Template = str(template_path)
    page.Template = template
    projected_source = engine.add(doc, "Part::Feature", page.Name + "Source")
    projected_source.Shape = shape
    engine.hide(projected_source)
    for kind, name, value in [
        ("App::PropertyInteger", "DrawingVersion", 1),
        ("App::PropertyLink", "DrawingProjectionSource", projected_source),
        (
            "App::PropertyLinkList",
            "DrawingSources",
            [engine.obj(doc, name) for name in arguments["objects"]],
        ),
        ("App::PropertyStringList", "DrawingSourceNames", arguments["objects"]),
        ("App::PropertyStringList", "DrawingViews", []),
        ("App::PropertyString", "DrawingPaper", arguments["paper"]),
        ("App::PropertyFloat", "DrawingRequestedScale", arguments.get("scale", 0)),
        ("App::PropertyString", "DrawingTitle", arguments["title"]),
        ("App::PropertyString", "DrawingPartNumber", arguments["part_number"]),
        ("App::PropertyString", "DrawingRevision", arguments["revision"]),
        ("App::PropertyString", "DrawingFingerprint", ""),
    ]:
        property_value(page, kind, name, value)
    created = []
    for orientation in arguments["views"]:
        view = engine.add(doc, "TechDraw::DrawViewPart", page.Name + orientation.title())
        property_value(view, "App::PropertyString", "DrawingOrientation", orientation)
        property_value(view, "App::PropertyStringList", "DrawingDimensions", [])
        page.addView(view)
        created.append(view.Name)
    page.DrawingViews = created
    return refresh_sheet(engine, doc, {"page": page.Name})


def node(parent, tag, text=None, **attributes):
    child = ET.SubElement(
        parent,
        "{" + SVG + "}" + tag,
        {key.replace("_", "-"): str(value) for key, value in attributes.items()},
    )
    child.text = text
    return child


def dimensions_svg(parent, cx, cy, width, height, values):
    left, right, top, bottom = cx - width / 2, cx + width / 2, cy - height / 2, cy + height / 2
    for x in (left, right):
        node(parent, "line", x1=x, x2=x, y1=bottom + 2, y2=bottom + 10)
        node(parent, "line", x1=x - 1, x2=x + 1, y1=bottom + 9, y2=bottom + 7)
    node(parent, "line", x1=left, x2=right, y1=bottom + 8, y2=bottom + 8)
    for y in (top, bottom):
        node(parent, "line", x1=right + 2, x2=right + 10, y1=y, y2=y)
        node(parent, "line", x1=right + 7, x2=right + 9, y1=y + 1, y2=y - 1)
    node(parent, "line", x1=right + 8, x2=right + 8, y1=top, y2=bottom)
    for value, x, y, rotation in [
        (values[0], cx, bottom + 7, None),
        (values[1], right + 7, cy, f"rotate(-90 {right + 7} {cy})"),
    ]:
        attrs = {
            "x": x,
            "y": y,
            "fill": "#111",
            "stroke": "none",
            "font_size": 3,
            "text_anchor": "middle",
        }
        if rotation:
            attrs["transform"] = rotation
        node(parent, "text", f"{value:.3f}", **attrs)


def render_svg(engine, doc, arguments):
    import TechDraw

    page = page_object(engine, doc, arguments["page"])
    shape, fingerprint = sources(engine, doc, list(page.DrawingSourceNames))
    if fingerprint != page.DrawingFingerprint:
        raise CadError("Drawing source changed; run drawings.refresh_sheet before rendering")
    views = [engine.obj(doc, name) for name in page.DrawingViews]
    orientations = [view.DrawingOrientation for view in views]
    width, height, scale, boxes = layout(
        engine, shape, page.DrawingPaper, orientations, page.DrawingRequestedScale
    )
    ET.register_namespace("", SVG)
    root = ET.Element(
        "{" + SVG + "}svg",
        {"width": f"{width}mm", "height": f"{height}mm", "viewBox": f"0 0 {width} {height}"},
    )
    root.set("font-family", "sans-serif")
    node(root, "rect", x=0, y=0, width=width, height=height, fill="white")
    node(
        root,
        "rect",
        x=8,
        y=8,
        width=width - 16,
        height=height - 16,
        fill="none",
        stroke="#111",
        stroke_width=0.3,
    )
    node(root, "text", page.DrawingTitle, x=12, y=18, font_size=5)
    node(
        root,
        "text",
        f"Part: {page.DrawingPartNumber}    Revision: {page.DrawingRevision}",
        x=12,
        y=height - 17,
        font_size=3.5,
    )
    node(
        root,
        "text",
        f"Scale {scale:g}:1 | mm | Overall extents | No tolerances specified",
        x=12,
        y=height - 11,
        font_size=3,
    )
    measurements = []
    for view, orientation in zip(views, orientations, strict=True):
        planar, box = projection(engine, shape, orientation)
        cx, cy = width * VIEWS[orientation][3][0], height * (1 - VIEWS[orientation][3][1])
        group = node(
            root,
            "g",
            transform=f"translate({cx} {cy}) scale({scale}) translate({-(box.XMin + box.XMax) / 2} {(box.YMin + box.YMax) / 2})",
        )
        fragment = ET.fromstring(TechDraw.projectToSVG(planar, engine.app.Vector(0, 0, 1)))
        fragment.set("stroke-width", str(0.25 / scale))
        for element in fragment.iter():
            if "id" in element.attrib:
                element.set("id", view.Name + "_" + element.get("id"))
        group.append(fragment)
        lines = node(root, "g", stroke="#333", stroke_width=0.18, fill="none")
        dimensions_svg(
            lines, cx, cy, box.XLength * scale, box.YLength * scale, [box.XLength, box.YLength]
        )
        node(
            root,
            "text",
            orientation.title(),
            x=cx,
            y=cy - box.YLength * scale / 2 - 4,
            font_size=3.5,
            text_anchor="middle",
        )
        measurements.append(
            {
                "view": view.Name,
                "orientation": orientation,
                "width_mm": box.XLength,
                "height_mm": box.YLength,
            }
        )
    svg = ET.tostring(root, encoding="unicode")
    if len(svg.encode("utf-8")) > 4 * 1024 * 1024:
        raise CadError("Rendered SVG exceeds 4 MiB")
    return {
        "page": page.Name,
        "media_type": "image/svg+xml",
        "svg": svg,
        "paper_mm": [width, height],
        "scale": scale,
        "views": measurements,
        "sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        "scope": "Orthographic visible-edge SVG with overall extent dimensions in mm. No hidden lines, GD&T, fits or manufacturing tolerances. PDF export is not included.",
    }
