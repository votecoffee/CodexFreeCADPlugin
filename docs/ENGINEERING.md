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
