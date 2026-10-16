"""Native FreeCAD demo: a cutaway 18/18/54-tooth planetary gearbox.

Run inside FreeCAD's Python interpreter, not the host virtual environment.
The built-in PartDesign gear utility supplies editable involute profiles;
the integration's shared engine builds the downstream solid features.
"""

import json
import math
from pathlib import Path


def build(workspace):
    import FreeCAD as App
    import InvoluteGearFeature

    from codex_freecad.engine import Engine

    workspace = Path(workspace).resolve()
    engine = Engine(workspace, gui=bool(App.GuiUp))
    document = "PlanetaryGearbox"
    engine.new_document(document, "CODEX — Cutaway Planetary Gearbox")
    doc = App.getDocument(document)
    pending = []

    def flush():
        if pending:
            engine.apply_operations(document, list(pending))
            pending.clear()

    def edit(*operations):
        if len(pending) + len(operations) > 100:
            flush()
        pending.extend(operations)

    def cylinder(name, radius, height, x=0, y=0, z=0):
        edit(
            {"op": "create_cylinder", "name": name, "radius": radius, "height": height},
            {"op": "set_placement", "object": name, "position": [x, y, z]},
        )
        return name

    def boolean(name, kind, base, tool):
        edit({"op": "boolean", "name": name, "kind": kind, "base": base, "tool": tool})
        return name

    def ring(name, outer, inner, height, z=0):
        cylinder(name + "Outer", outer, height, z=z)
        cylinder(name + "Bore", inner, height + 2, z=z - 1)
        return boolean(name, "cut", name + "Outer", name + "Bore")

    def pattern(name, source, count, angle=360):
        edit(
            {
                "op": "circular_pattern",
                "name": name,
                "source": source,
                "count": count,
                "angle": angle,
            }
        )
        return name

    def straight_path(name, start, length):
        edit(
            {
                "op": "create_sketch",
                "name": name,
                "geometry": [{"type": "line", "start": [0, 0], "end": [0, length]}],
            },
            {
                "op": "set_placement",
                "object": name,
                "position": [0, 0, start],
                "axis": [1, 0, 0],
                "angle": 90,
            },
            {
                "op": "add_constraint",
                "object": name,
                "type": "Distance",
                "args": [0, float(length)],
            },
        )

    edit(
        {
            "op": "create_parameters",
            "name": "Design",
            "parameters": [
                {
                    "name": "GearWidth",
                    "type": "length",
                    "value": "12 mm",
                    "description": "Editable axial gear face width",
                },
                {"name": "HousingHeight", "type": "length", "value": "22 mm"},
                {"name": "CutawayAngle", "type": "angle", "value": "90 deg"},
            ],
        }
    )
    straight_path("GearExtrusionPath", 8, 12)
    straight_path("RingExtrusionPath", 5, 22)
    edit(
        {
            "op": "set_expression",
            "object": "GearExtrusionPath",
            "property": "Constraints[0]",
            "expression": "Design.GearWidth",
        },
        {
            "op": "set_expression",
            "object": "RingExtrusionPath",
            "property": "Constraints[0]",
            "expression": "Design.HousingHeight",
        },
    )

    flush()
    for name, teeth, internal, z in [
        ("SunProfile", 18, False, 8),
        ("PlanetProfile", 18, False, 8),
        ("InternalRingProfile", 54, True, 5),
    ]:
        profile = InvoluteGearFeature.makeInvoluteGear(name)
        profile.NumberOfTeeth = teeth
        profile.Modules = 2.0
        profile.PressureAngle = 20.0
        profile.ExternalGear = not internal
        profile.AddendumCoefficient = 0.6 if internal else 1.0
        profile.ProfileShiftCoefficient = 0.0 if internal else -0.01
        profile.Placement.Base.z = z
        profile.Label = (
            "Internal ring" if internal else name.replace("Profile", "")
        ) + f" — {teeth} teeth, module 2"
        doc.recompute()
        if not profile.Shape.isValid() or not profile.Shape.isClosed():
            raise RuntimeError("Native gear profile is invalid: " + name)

    edit(
        {
            "op": "sweep",
            "name": "SunBlank",
            "profiles": ["SunProfile"],
            "path": "GearExtrusionPath",
        },
        {
            "op": "sweep",
            "name": "PlanetBlank",
            "profiles": ["PlanetProfile"],
            "path": "GearExtrusionPath",
        },
        {
            "op": "sweep",
            "name": "RingCavity",
            "profiles": ["InternalRingProfile"],
            "path": "RingExtrusionPath",
        },
    )
    cylinder("SunBore", 5.15, 14, z=7)
    boolean("SunGear", "cut", "SunBlank", "SunBore")
    cylinder("PlanetBore", 3.65, 14, z=7)
    boolean("PlanetGear", "cut", "PlanetBlank", "PlanetBore")
    orbit = 36
    px, py = orbit * math.cos(math.radians(30)), orbit * math.sin(math.radians(30))
    edit(
        {
            "op": "set_placement",
            "object": "PlanetGear",
            "position": [px, py, 0],
            "axis": [0, 0, 1],
            "angle": 10,
        }
    )
    pattern("PlanetGears", "PlanetGear", 3)

    cylinder("RingOuter", 66, 22, z=5)
    edit(
        {
            "op": "set_expression",
            "object": "RingOuter",
            "property": "Height",
            "expression": "Design.HousingHeight",
        }
    )
    boolean("FullRingGear", "cut", "RingOuter", "RingCavity")
    # A native partial cylinder provides an editable angular cutaway.
    cylinder("CutawayTool", 90, 34, z=4.5)
    edit(
        {"op": "set_property", "object": "CutawayTool", "property": "Angle", "value": 90},
        {
            "op": "set_expression",
            "object": "CutawayTool",
            "property": "Angle",
            "expression": "Design.CutawayAngle",
        },
        {
            "op": "set_placement",
            "object": "CutawayTool",
            "position": [0, 0, 4.5],
            "axis": [0, 0, 1],
            "angle": 225,
        },
    )
    boolean("CutawayRing", "cut", "FullRingGear", "CutawayTool")
    cylinder("RingScrewHole", 2.2, 26, x=61, z=4)
    pattern("RingScrewHoles", "RingScrewHole", 6, 200)
    boolean("RingHousing", "cut", "CutawayRing", "RingScrewHoles")

    cylinder("BaseBlank", 76, 5)
    cylinder("FloorRecess", 57, 3, z=3.5)
    boolean("RecessedBase", "cut", "BaseBlank", "FloorRecess")
    cylinder("MountingHole", 3.2, 7, x=70, z=-1)
    pattern("MountingHoles", "MountingHole", 6)
    boolean("DrilledBase", "cut", "RecessedBase", "MountingHoles")
    cylinder("InputClearance", 7, 8, z=-1)
    boolean("BasePlate", "cut", "DrilledBase", "InputClearance")
    flush()
    edges = engine.inspect_topology(document, "BasePlate")["items"]
    top_edge = next(
        e["name"]
        for e in edges
        if e.get("curve") == "Circle"
        and abs(e.get("radius_mm", 0) - 76) < 1e-6
        and abs(e["center_mm"][2] - 5) < 1e-5
    )
    edit(
        {
            "op": "chamfer",
            "name": "FinishedBase",
            "base": "BasePlate",
            "edges": [top_edge],
            "size": 0.8,
        }
    )

    # Rounded three-arm carrier, with separately modeled pins and fasteners.
    cylinder("CarrierHub", 11, 4, z=23)
    carrier_base = "CarrierHub"
    for index in range(3):
        degrees = 30 + index * 120
        angle = math.radians(degrees)
        name = "CarrierArm" + str(index + 1)
        edit(
            {"op": "create_box", "name": name, "length": 30, "width": 8, "height": 4},
            {
                "op": "set_placement",
                "object": name,
                "position": [
                    6 * math.cos(angle) + 4 * math.sin(angle),
                    6 * math.sin(angle) - 4 * math.cos(angle),
                    23,
                ],
                "axis": [0, 0, 1],
                "angle": degrees,
            },
        )
        carrier_base = boolean("CarrierArmUnion" + str(index + 1), "fuse", carrier_base, name)
        boss = cylinder(
            "CarrierBoss" + str(index + 1),
            7.5,
            4,
            x=36 * math.cos(angle),
            y=36 * math.sin(angle),
            z=23,
        )
        carrier_base = boolean(
            "CarrierSolid" if index == 2 else "CarrierBossUnion" + str(index + 1),
            "fuse",
            carrier_base,
            boss,
        )
    cylinder("OutputBore", 5.6, 7, z=22)
    boolean("Carrier", "cut", "CarrierSolid", "OutputBore")
    cylinder("Pin", 3.5, 23, x=px, y=py, z=4)
    pattern("PlanetPins", "Pin", 3)
    ring("Washer", 6.2, 3.7, 1.2, z=21)
    edit({"op": "set_placement", "object": "Washer", "position": [px, py, 0]})
    pattern("PlanetWashers", "Washer", 3)

    cylinder("InputShaft", 5, 31, z=-9)
    cylinder("OutputShaft", 5.5, 25, z=25)
    ring("OutputCollar", 9, 5.6, 5, z=27)
    ring("InputCollar", 7.7, 5.15, 2.5, z=20.5)

    def socket_head(name, radius, height, z, socket_radius):
        cylinder(name + "Blank", radius, height, z=z)
        corners = [
            [socket_radius * math.cos(i * math.pi / 3), socket_radius * math.sin(i * math.pi / 3)]
            for i in range(6)
        ]
        edit(
            {
                "op": "create_sketch",
                "name": name + "Socket",
                "geometry": [
                    {"type": "line", "start": corners[i], "end": corners[(i + 1) % 6]}
                    for i in range(6)
                ],
            },
            {
                "op": "set_placement",
                "object": name + "Socket",
                "position": [0, 0, z + height - 1.4],
            },
        )
        straight_path(name + "SocketPath", z + height - 1.4, 2)
        edit(
            {
                "op": "sweep",
                "name": name + "SocketTool",
                "profiles": [name + "Socket"],
                "path": name + "SocketPath",
            }
        )
        return boolean(name, "cut", name + "Blank", name + "SocketTool")

    socket_head("PinHead", 4.8, 3.2, 27, 2.5)
    edit({"op": "set_placement", "object": "PinHead", "position": [px, py, 0]})
    pattern("CarrierBolts", "PinHead", 3)
    socket_head("HousingScrew", 3.8, 2.6, 27, 2)
    edit({"op": "set_placement", "object": "HousingScrew", "position": [61, 0, 0]})
    pattern("HousingBolts", "HousingScrew", 6, 200)
    flush()

    visible = [
        "FinishedBase",
        "RingHousing",
        "SunGear",
        "PlanetGears",
        "Carrier",
        "PlanetPins",
        "PlanetWashers",
        "InputShaft",
        "OutputShaft",
        "OutputCollar",
        "InputCollar",
        "CarrierBolts",
        "HousingBolts",
    ]
    for obj in doc.Objects:
        if "Visibility" in obj.PropertiesList:
            obj.Visibility = obj.Name in visible
    doc.recompute()
    for name in visible:
        shape = doc.getObject(name).Shape
        if shape.isNull() or not shape.isValid() or not shape.Solids or shape.Volume <= 0:
            raise RuntimeError("Invalid final part: " + name)

    # Measure the actual solid intersections in this static gear arrangement.
    sun = doc.getObject("SunGear").Shape
    planets = doc.getObject("PlanetGears").Shape.Solids
    full_ring = doc.getObject("FullRingGear").Shape
    intersections = []
    for index, planet in enumerate(planets):
        intersections.append(
            {
                "planet": index + 1,
                "sun_overlap_mm3": sun.common(planet).Volume,
                "ring_overlap_mm3": full_ring.common(planet).Volume,
            }
        )
    saved = engine.save_document(document, "PlanetaryGearbox.FCStd")
    exported = engine.export_model(document, visible, "PlanetaryGearbox.step")
    report = {
        "document": document,
        "components": visible,
        "solid_count": sum(len(doc.getObject(name).Shape.Solids) for name in visible),
        "tooth_counts": {"sun": 18, "planet": 18, "ring": 54},
        "module_mm": 2,
        "planet_orbit_radius_mm": orbit,
        "gear_intersections": intersections,
        "saved": saved,
        "exported": exported,
    }
    (workspace / "geometry-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def present(workspace):
    """Style, capture and save assembled/exploded views in an isolated native GUI."""
    import FreeCAD as App
    import FreeCADGui as Gui
    import ImportGui
    from pivy import coin

    from codex_freecad.engine import Engine

    workspace = Path(workspace).resolve()
    report = json.loads((workspace / "geometry-report.json").read_text(encoding="utf-8"))
    doc = App.openDocument(str(workspace / "PlanetaryGearbox.FCStd"))
    # Reapply the declared clearance to an existing build when using --render-only.
    Engine(workspace, gui=True).apply_operations(
        doc.Name,
        [
            {
                "op": "set_property",
                "object": "SunProfile",
                "property": "ProfileShiftCoefficient",
                "value": -0.01,
            },
            {
                "op": "set_property",
                "object": "PlanetProfile",
                "property": "ProfileShiftCoefficient",
                "value": -0.01,
            },
        ],
    )
    doc.recompute()
    palette = {
        "FinishedBase": (0.16, 0.21, 0.28),
        "RingHousing": (0.12, 0.30, 0.47),
        "SunGear": (0.96, 0.64, 0.18),
        "PlanetGear": (0.68, 0.78, 0.86),
        "PlanetGears": (0.68, 0.78, 0.86),
        "Carrier": (0.10, 0.56, 0.59),
        "Pin": (0.66, 0.70, 0.76),
        "PlanetPins": (0.66, 0.70, 0.76),
        "Washer": (0.76, 0.79, 0.82),
        "PlanetWashers": (0.76, 0.79, 0.82),
        "InputShaft": (0.72, 0.75, 0.80),
        "OutputShaft": (0.72, 0.75, 0.80),
        "OutputCollar": (0.24, 0.28, 0.34),
        "InputCollar": (0.24, 0.28, 0.34),
        "PinHead": (0.20, 0.23, 0.28),
        "CarrierBolts": (0.20, 0.23, 0.28),
        "HousingScrew": (0.20, 0.23, 0.28),
        "HousingBolts": (0.20, 0.23, 0.28),
    }
    for name, color in palette.items():
        provider = doc.getObject(name).ViewObject
        if hasattr(provider, "ShapeColor"):
            provider.ShapeColor = color
        for prop, value in {
            "LineColor": (0.08, 0.10, 0.13),
            "LineWidth": 1.0,
            "Deviation": 0.05,
            "AngularDeflection": 12.0,
            "Shininess": 45.0,
            "SpecularColor": (0.65, 0.65, 0.65),
        }.items():
            if hasattr(provider, prop):
                setattr(provider, prop, value)
        if "Flat Lines" in provider.listDisplayModes():
            provider.DisplayMode = "Flat Lines"
    # Plain groups organize the native history without adding coordinate transforms.
    groups = [
        (
            "BaseHousing",
            "01 · Base and cutaway housing",
            ["FinishedBase", "RingHousing", "HousingBolts"],
        ),
        ("GearTrain", "02 · Sun and three planet gears", ["SunGear", "PlanetGears"]),
        (
            "CarrierAssembly",
            "03 · Carrier, pins and socket screws",
            ["Carrier", "PlanetPins", "PlanetWashers", "CarrierBolts"],
        ),
        (
            "Shafts",
            "04 · Coaxial shafts and collars",
            ["InputShaft", "OutputShaft", "InputCollar", "OutputCollar"],
        ),
    ]
    construction = [
        obj for obj in doc.Objects if obj.Name not in report["components"] and obj.Name != "Design"
    ]
    for name, label, names in groups:
        group = doc.addObject("App::DocumentObjectGroup", name)
        group.Label = label
        group.addObjects([doc.getObject(name) for name in names])
    history = doc.addObject("App::DocumentObjectGroup", "FeatureHistory")
    history.Label = "05 · Editable profiles and feature history"
    history.addObjects(construction)
    for obj in construction:
        if "Visibility" in obj.PropertiesList:
            obj.Visibility = False
    for name in report["components"]:
        doc.getObject(name).Visibility = True
    doc.getObject("Design").Label = "Design controls · gear width, housing height, cutaway"
    Gui.activeDocument().activeView().setCameraType("Orthographic")
    view = Gui.activeDocument().activeView()

    def hero_camera():
        towards_camera = App.Vector(0.8, -1.2, 1.7)
        right = App.Vector(0, 0, 1).cross(towards_camera)
        up = towards_camera.cross(right)
        view.setCameraOrientation(App.Rotation(right, up, towards_camera, "ZXY").Q)
        view.fitAll()
        camera = view.getCameraNode()
        if not isinstance(camera, coin.SoOrthographicCamera):
            raise RuntimeError("Expected an orthographic native camera")
        camera.height.setValue(175)
        camera.nearDistance.setValue(1)
        camera.farDistance.setValue(2000)
        camera.position.setValue(*(App.Vector(0, 0, 18) + towards_camera.normalize() * 400))
        Gui.updateGui()

    hero_camera()
    view.saveImage(str(workspace / "PlanetaryGearbox.png"), 1920, 1440, "White")
    doc.saveAs(str(workspace / "PlanetaryGearbox-Showcase.FCStd"))
    ImportGui.export(
        [doc.getObject(name) for name in report["components"]],
        str(workspace / "PlanetaryGearbox-Colored.step"),
    )
    view.viewTop()
    view.fitAll()
    view.getCameraNode().height.setValue(175)
    view.getCameraNode().nearDistance.setValue(1)
    view.getCameraNode().farDistance.setValue(2000)
    view.getCameraNode().position.setValue(0, 0, 400)
    Gui.updateGui()
    view.saveImage(str(workspace / "PlanetaryGearbox-Top.png"), 1600, 1600, "White")

    displacements = {
        "RingHousing": (110, 40, 18),
        "HousingBolts": (110, 40, 40),
        "SunGear": (0, 0, 12),
        "PlanetGears": (0, 0, 12),
        "Carrier": (0, 0, 54),
        "PlanetPins": (0, 0, 38),
        "PlanetWashers": (0, 0, 40),
        "CarrierBolts": (0, 0, 56),
        "OutputShaft": (0, 0, 70),
        "OutputCollar": (0, 0, 54),
        "InputCollar": (0, 0, 12),
    }
    exploded = App.newDocument("PlanetaryExploded")
    for name in report["components"]:
        source = doc.getObject(name)
        obj = exploded.addObject("Part::Feature", name)
        obj.Label = source.Label
        obj.Shape = source.Shape.copy()
        placement = obj.Placement
        placement.Base += App.Vector(*displacements.get(name, (0, 0, 0)))
        obj.Placement = placement
        obj.ViewObject.ShapeColor = palette[name]
        obj.ViewObject.LineColor = (0.08, 0.10, 0.13)
        obj.ViewObject.DisplayMode = "Flat Lines"
    exploded.recompute()
    exploded.Label = "CODEX — Planetary Gearbox · Exploded Layout"
    view = Gui.activeDocument().activeView()
    towards_camera = App.Vector(0.8, -1.2, 1.7)
    right = App.Vector(0, 0, 1).cross(towards_camera)
    view.setCameraType("Orthographic")
    view.setCameraOrientation(
        App.Rotation(right, towards_camera.cross(right), towards_camera, "ZXY").Q
    )
    view.fitAll()
    view.getCameraNode().height.setValue(245)
    view.getCameraNode().nearDistance.setValue(1)
    view.getCameraNode().farDistance.setValue(2000)
    view.getCameraNode().position.setValue(
        *(App.Vector(42, 12, 50) + towards_camera.normalize() * 500)
    )
    Gui.updateGui()
    view.saveImage(str(workspace / "PlanetaryGearbox-Exploded.png"), 1920, 1600, "White")
    exploded.saveAs(str(workspace / "PlanetaryGearbox-Exploded.FCStd"))
    (workspace / "presentation-report.json").write_text(
        json.dumps(
            {
                "rendered": True,
                "components": report["components"],
                "views": ["assembled", "top", "exploded"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    App.closeDocument(exploded.Name)
    App.closeDocument(doc.Name)
