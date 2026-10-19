# Engineering extensions

These capabilities use the existing discovery, query and extension edit tools. Reload the backend and describe each capability to obtain its current arguments and catalog revision. Both backends use the same implementation; manual GUI checks remain separate from FreeCADCmd validation.

## Bill of materials

`bom.inspect` is a read-only query with required `objects`, a list of 1–200 distinct internal object names. Select top-level solid parts, native link arrays, assembly components or a supported root assembly. Selecting an assembly expands its direct component links and excludes hidden modeling sources. Explicit selections do not depend on viewport visibility. Repeated components through overlapping selections are rejected.

Rows group by the same-document native source identity. Different sources remain separate even when their labels or part numbers match; repeated part numbers are reported. A compound source is one part containing multiple solids. Native link-array quantities count instances. Scaled links, nested arrays, external-document links and nested part containers are unsupported. Volumes include all selected material, without subtracting overlap.

The result includes source names, selected instance names, quantity, solids per item, individual/total volume, metadata, CSV text and optional mass. Unknown density remains unknown, and total mass is returned only when every row has an explicit positive density. Units are mm³, kg/m³ and kg. Model-provided CSV text that could be interpreted as a spreadsheet formula is escaped.

Use these edit capabilities through `apply_operations`:

- `bom.set_metadata`: required `object`, plus at least one of `part_number`, `description`, `material`, `density_kg_m3`. Metadata is stored on the linked source as native properties. Density zero clears known density; a material name alone does not infer a density. Expression-driven metadata must be edited through its driving parameter.
- `bom.create_sheet`: required `name` and `objects`. Creates a native `Spreadsheet::Sheet` snapshot with saved source links and literal text cells.
- `bom.refresh_sheet`: required `sheet`. Refreshes an integration-created spreadsheet after geometry, metadata or instance-count changes. It is an explicit, undoable snapshot refresh, not an automatic feature proxy.

Example query arguments:

```json
{"document":"Gearbox","capability":"bom.inspect","arguments":{"objects":["GearboxAssembly"]}}
```

Example metadata and sheet operations in one batch:

```json
[
  {"op":"extension","capability":"bom.set_metadata","arguments":{"object":"Bolt","part_number":"BOLT-001","material":"Steel","density_kg_m3":7850}},
  {"op":"extension","capability":"bom.create_sheet","arguments":{"name":"PartsList","objects":["GearboxAssembly"]}}
]
```

Use the document revision guard on edits. A failed operation rolls back the complete native batch; metadata and spreadsheets persist through FCStd save/reopen without extension-owned executable proxies.

## Parameter studies

`studies.parameter_sweep` is a query that evaluates a numeric scalar property over explicitly supplied values. Required arguments are `object` (driver internal name), `property`, `values` and `objects` (selected output solids). An optional `density_kg_m3` adds mass to each output measurement. Numeric quantities use native base units: lengths in mm and angles in degrees; integer properties require integer values.

The engine copies the same-document dependency graph into an owned hidden document, changes the copied driver, recomputes and returns per-configuration solid counts, bounds, area and volume. Source parameters, revision and Undo are preserved. The hidden document is closed on success or failure, and the previous active document is restored. A bad sample rejects the complete query rather than silently skipping a configuration. Expression-driven, read-only and managed fields must be edited through their driving inputs.

Limits are 50 values, 20 distinct output objects, 200 object-configuration measurements, 500 source document objects and numeric values between -1,000,000 and 1,000,000. Outputs must be top-level positive-volume solids or components in a supported identity-placement root assembly. External-document dependencies are unsupported. Volume totals sum selected objects without subtracting overlap; these are discrete design samples, not collision, strength or optimization results.

```json
{"document":"Model","capability":"studies.parameter_sweep","arguments":{"object":"Design","property":"Thickness","values":[4,6,8],"objects":["Plate"],"density_kg_m3":2700}}
```

To retain geometry, use the `studies.create_variants` edit capability with the same arguments plus `name`. It evaluates every sample before creating a native group of `Part::Feature` snapshots, with source links, driver property and sampled values recorded as provenance. The result returns the created names and measurements.

```json
{"op":"extension","capability":"studies.create_variants","arguments":{"name":"ThicknessVariants","object":"Design","property":"Thickness","values":[4,6,8],"objects":["Plate"]}}
```

Variants are frozen evaluated BREP snapshots. They do not retain the source feature history and do not regenerate when the source changes. They remain usable after save/reopen without executable extension proxies. Creating all variants is one undoable model edit; saving/exporting the group members is a separate action.

## Saved design requirements

The `requirements` extension stores explicit limits as native model metadata. It supplies four capabilities:

- `requirements.create_set` (edit): required `name` and `rules`.
- `requirements.update_set` (edit): required `set` and a complete replacement `rules` list.
- `requirements.evaluate` (query): required `set`; reports `pass`, `fail` or `error` for every rule and `all_passed` for the complete set.
- `requirements.enforce` (edit): required `set`; raises when any rule fails or cannot be measured, rolling back the entire enclosing `apply_operations` batch. Put enforcement after all edits to be checked.

Each set contains 1–50 rules with distinct identifier `id`, `metric`, internal `object` name and at least one inclusive `minimum` or `maximum`. Optional `absolute_tolerance` defaults to zero and expands the numeric bounds in the measurement's units. Supported metrics are:

| Metric | Additional fields | Measurement |
| --- | --- | --- |
| `property` | `property` | Supported numeric scalar in native base units: mm, degrees, mm², mm³, percent or dimensionless. Generic `App::PropertyQuantity` properties are rejected because their dimensions are unspecified. |
| `volume` | None | Selected solid volume in mm³. |
| `mass` | Positive `density_kg_m3` | Volume × explicitly supplied density, in kg. Density is stored in the rule and is not inferred from material metadata. |
| `extent` | `axis`: `x`, `y` or `z` | Axis-aligned bounding-box size in model coordinates, in mm. |
| `clearance` | Distinct `other` object; optional `overlap_tolerance_mm3` | Minimum BREP distance in mm, plus positive-volume overlap. Overlap above the tolerance fails even when minimum distance zero would meet the numeric bounds. |

Clearance overlap tolerance defaults to 0.000001 mm³; contact is allowed when the requested minimum is zero. Absolute tolerance affects distance/other numeric limits, not overlap tolerance. These are nominal geometry measurements at the current pose, not manufacturing tolerance or load assessments. Geometry targets must be top-level positive-volume solids or components of a supported root identity assembly, with at most 5,000 distinct measured shape edges per set evaluation. Internal names identify targets; labels do not. Native source links detect missing or replaced targets; a broken link set reports errors until explicitly updated.

```json
{"op":"extension","capability":"requirements.create_set","arguments":{"name":"FitLimits","rules":[{"id":"MinimumGap","metric":"clearance","object":"Shaft","other":"Sleeve","minimum":0.5,"absolute_tolerance":0.000001},{"id":"MaximumMass","metric":"mass","object":"Shaft","density_kg_m3":7850,"maximum":0.055}]}}
```

To check arbitrary supported model edits as one transaction, append enforcement:

```json
[
  {"op":"set_property","object":"Design","property":"ShaftRadius","value":7.25},
  {"op":"extension","capability":"requirements.enforce","arguments":{"set":"FitLimits"}}
]
```

Use `expected_revision` on the enclosing edit. Enforcement checks the state at its position in the batch; later operations, direct FreeCAD edits, saving and exporting are not automatically guarded. Sets are opt-in checks, not a global document policy. A query reporting failure does not itself mutate or reject the source design. Rule creation and updates are undoable, and rules/source links survive native FCStd save/reopen without executable extension proxies. The set is a native property container with `Proxy=None`; definition hashes identify the exact saved rules.

## Change previews

`studies.preview_changes` is a query that evaluates several numeric scalar edits together on an owned hidden dependency copy. Required arguments are `changes` (1–20 distinct object/property/value entries) and `objects` (1–20 distinct selected output solids). Optional `density_kg_m3` adds mass measurements. The same units, driver protections, output selection rules and 500-object document limit as parameter studies apply. Each state is limited to 5,000 edges across the selected shapes. Values must be between -1,000,000 and 1,000,000; integer properties require integer JSON values.

```json
{"document":"Model","capability":"studies.preview_changes","arguments":{"changes":[{"object":"Design","property":"Length","value":80},{"object":"Plate","property":"Width","value":40}],"objects":["Plate"],"density_kg_m3":2700}}
```

The result reports each parameter's original, requested and evaluated value, and each output's before/after bounds, area, volume and optional mass. Native BREP differences report added and removed material in model coordinates, with a volume consistency check. This detects equal-volume reshaping and translation that a net-volume comparison misses. Reports cover only the selected solids; sums across overlapping selections do not represent a material union. Dimensions driven by expressions must be changed through their input parameters. Generic edits to managed assembly/pattern properties remain blocked.

`apply_arguments` contains `document`, the source `expected_revision`, and the exact ordered `set_property` operations used for the preview. Pass this object to `apply_operations` to apply the proposed edits as one undoable transaction. A source change since preview causes the revision guard to reject the edit. Previewing does not apply edits, save files or create persistent model objects. This is a numeric geometry comparison, not a collision, strength or manufacturing assessment.

Optional `requirement_sets` selects 1–5 distinct saved sets to evaluate before and after the proposed changes on the hidden copy. The returned `requirements` section reports both states, checked set count and `all_passed_after`. With no selected sets, zero checks are performed. A failing proposal still returns measurements for review; its generated `apply_arguments` append catalog-guarded enforcement operations, which reject application until the proposed design satisfies all selected sets. A catalog change also rejects the generated enforcement plan; describe/re-preview with the current capabilities.

Python workflow using an existing client:

```python
report = cad.call(
    "run_query", document="Model", capability="studies.preview_changes",
    arguments={
        "changes": [{"object": "Design", "property": "Thickness", "value": 6}],
        "objects": ["Plate"],
    },
)["result"]
print(report["objects"])
cad.call("apply_operations", **report["apply_arguments"])
```

The hidden copy closes after either success or failure. Source parameters, active document and Undo are preserved. Applying and saving remain separate actions. The capability and its relative helper module reload through the existing stable tools without changing MCP schemas.

## Dimensioned drawings

`drawings.create_sheet` is an edit capability with required `name` and `objects`. It creates a native `TechDraw::DrawPage`, an embedded FreeCAD blank landscape template, front/top/right views and native overall width/height extent dimensions. Optional arguments are `paper` (`A4` or `A3`), `views` (a distinct subset of `front`, `top`, `right`), `scale` (0.01–100), `title`, `part_number` and `revision`. Omit scale for a fitted standard scale; an explicit scale that cannot fit is rejected.

```json
{"op":"extension","capability":"drawings.create_sheet","arguments":{"name":"PlateDrawing","objects":["Plate"],"paper":"A4","title":"Mounting plate","part_number":"PLATE-001","revision":"A"}}
```

Sources must be 1–20 distinct top-level positive-volume solids or components in a supported root identity assembly, with at most 5,000 edges. A hidden native `Part::Feature` projection snapshot evaluates the selected sources, including all compact link-array instances. Native extent dimensions associate with this snapshot. The drawing stores original source links for explicit refresh; it does not add executable feature proxies.

After source edits, invoke `drawings.refresh_sheet` with `page`. This updates the projection snapshot, refits the sheet and rebuilds owned native dimensions. Source fingerprints prevent rendering a sheet whose original geometry changed without a refresh. Native dimension values are checked against independent projected BREP bounds. Creation and refresh are undoable model edits and survive save/reopen.

`drawings.render_svg` is a read-only query with `page`. It returns `media_type`, SVG text in `svg`, its SHA-256 hash, paper dimensions, scale and view measurements. It uses the native BREP projector and standard XML serialization, without `TechDrawGui` export functions. Client code can save the returned text to an SVG file; the query itself does not write files. The SVG presents orthographic geometry and overall extent dimensions in mm. It does not specify hole locations, diameter dimensions, hidden-line options, tolerances, GD&T, fits or PDF output.

```json
{"document":"Model","capability":"drawings.render_svg","arguments":{"page":"PlateDrawing"}}
```

FreeCAD 1.0.2 completes exact TechDraw projection through Qt queued signals. Headless drawing creation uses a core event dispatcher with no windows, processes projection completion with keyboard/pointer events excluded, and bounds dimension-completion waits. The dispatcher remains owned by the stable FreeCAD runtime across extension reloads. No host MCP/Pydantic package is imported into FreeCAD.

FreeCADCmd checks cover native dimensions, curves, translated parts, link arrays, refresh, stale-source rejection, Undo, save/reopen and SVG XML. Actual GUI page layout and physical printing require separate manual inspection. SVG output uses a fixed layout and overall extents; it is not a complete manufacturing drawing specification.
