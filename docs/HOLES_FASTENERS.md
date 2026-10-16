# Hole tools

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
