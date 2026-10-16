# Hole and fastener tools

These installed extension capabilities work through the same engine in live FreeCAD and FreeCADCmd. Discover current arguments with `describe_capability`, then pass an `extension` operation to `apply_operations`. All lengths are mm and angles are degrees. The fixed MCP tool schemas stay unchanged.

## Drill holes

`holes.drill` cuts 1–64 holes into an existing BREP solid. Positions are world entry points and `direction` points into the material; its default is `[0,0,-1]`. Each bore must intersect material. The result must leave a valid positive-volume solid. Duplicate positions, ineffective recesses, invalid dimensions and name collisions reject the entire edit batch.

```json
{
  "op": "extension",
  "capability": "holes.drill",
  "arguments": {
    "name": "MountingHoles",
    "base": "Plate",
    "positions": [[10,15,10], [30,15,10]],
    "diameter": 6,
    "style": "counterbore",
    "recess_diameter": 10,
    "recess_depth": 3
  }
}
```

The default `mode="through"` measures a cutting extent covering the whole base along the selected direction, on both sides of each entry plane. Omit `depth`. Use `mode="blind"` with an explicit `depth` for flat-bottom bores. There is no drill-tip geometry.

The default `style="simple"` takes no recess fields. A `counterbore` needs a larger `recess_diameter` and `recess_depth`. A `countersink` needs a larger `recess_diameter`; optional `countersink_angle` is the included angle, default 90°. Its depth is `(recess_diameter - diameter)/(2*tan(angle/2))`. The recess must be shallower than a blind bore and must remove material outside the shaft.

The result is a native `Part::Cut` referencing native cylinder/cone tools. A separate `<name>Parameters` property container holds dimensions; its Python proxy is empty. For example, edit `MountingHolesParameters.Diameter` with `set_property`. Native expressions recompute the cutter geometry, and countersink depth follows its diameter and angle. Creation/refresh validates the hole-specific dimension relationships; generic parameter edits use the core's native geometry checks.

## Bolt circles and refreshing through holes

`holes.bolt_circle` accepts the same bore/recess fields, replacing `positions` with `center`, `radius`, `count` (2–64) and optional `start_angle`. It places a full circle of holes. Local XY rotates from +Z onto `direction`; `start_angle` is measured from that rotated +X. For a flange from Z=0 to Z=8, use `center=[0,0,8]`, `direction=[0,0,-1]`, `radius=20`, `count=6` and the desired hole diameter.

Layouts are sampled at creation. Entry points and recess entry planes remain in world coordinates; they do not attach to faces or move with the base. Through-hole extents are measured snapshots. After resizing or moving the base, call `holes.refresh` with `{"object":"MountingHoles"}` in an extension edit operation. It measures a fresh through extent and rechecks every bore/recess. It does not relocate entry planes or the circle layout. If an entry plane has moved away from the intended surface, create the layout at the new surface instead.

Every successful batch is one Undo entry. Features save/reopen as native FreeCAD objects and do not require these extension modules to recompute. Source features remain in the document history; input files are preserved unless the caller explicitly saves over them.

## Bolts, nuts and washers

`fasteners.bolt`, `fasteners.nut` and `fasteners.washer` create individual native solids. They use explicit dimensions and simplified **unthreaded** geometry. They do not assign ISO/ANSI sizes, machining tolerances, fit classes, material strength or torque ratings. Nuts have a cylindrical bore; bolt shafts have a cylindrical surface. Bolt length is the under-head length, with no drill/thread-tip or chamfer allowance.

All three capabilities accept `name`, optional world `position=[0,0,0]`, `axis=[0,0,1]` and `rotation=0`. The axis maps local +Z to the chosen direction and rotation spins about that local axis in degrees. A bolt's position is the head seating plane: the shaft extends along local −Z and the head along +Z. A washer/nut position is its bottom plane, extending along +Z.

| Capability | Dimensions |
|---|---|
| `fasteners.bolt`, `head_style="hex"` (default) | `diameter`, `length`, `head_height`, `across_flats` |
| `fasteners.bolt`, `head_style="socket_cap"` | `diameter`, `length`, `head_height`, `head_diameter`, `socket_across_flats`, `socket_depth` |
| `fasteners.nut` | `across_flats`, `bore_diameter`, `thickness` |
| `fasteners.washer` | `outer_diameter`, `bore_diameter`, `thickness` |

Hex head/nut across-flats must exceed the shaft/bore diameter. Socket corners must fit inside the cap diameter, and the socket must be shallower than the head. A washer's outside diameter must exceed its bore. Supplying dimensions belonging to another head style is rejected.

For a counterbore of diameter 10 mm and depth 3 mm in a plate whose top is Z=10, this example seats an 8 mm cap head on the counterbore floor at Z=7:

```json
{
  "op": "extension",
  "capability": "fasteners.bolt",
  "arguments": {
    "name": "CapBolt",
    "head_style": "socket_cap",
    "diameter": 5,
    "length": 16,
    "head_diameter": 8,
    "head_height": 3,
    "socket_across_flats": 4,
    "socket_depth": 2,
    "position": [10,15,7]
  }
}
```

Each result reports its dimension container, e.g. `CapBoltParameters`. Edit `Length`, `HeadHeight`, `AcrossFlats`, `BoreDiameter` or the other available properties through `set_property` or the native property editor. Native expressions keep the primitives linked. Head/socket and nut/washer relationships are validated at creation; generic subsequent scalar edits receive native geometry validation. The result's normal placement remains editable. Use the existing link/pattern/assembly capabilities to reuse fasteners; creation does not automatically insert, mate or couple them to holes.

If v0.8's stable core is already running, install these extension folders in that same package location and call `reload_extensions`, then discover their arguments. No new MCP schemas or model proxies are required. Native process package-version reporting may retain the version imported at startup; the capability catalog reports the active extension versions and content hashes.
