# Changes

## Unreleased

- Added native named length, angle, number and integer parameter containers.
- Added arithmetic expressions on numeric feature properties, placement translations and named/indexed dimensional sketch constraints, with dependency propagation and explicit expression removal.
- Exposed expression bindings in object/document inspection and prevented direct datum/placement writes from silently overriding expression-driven values.
- Restricted new expression input to arithmetic, units, pi and numeric references inside the same document; invalid units, cycles and failed recomputes roll back the transaction.

## 0.3.0 — 2026-10-16

- Added three-point sketch arcs and optional fully constrained rectangles with named width, height and origin dimensions.
- Added appending sketch geometry and detailed sketch inspection, including local coordinates, construction flags, constraint indices, units and driving/active state.
- Added native solid/surface revolutions with editable source dimensions and angle.
- Added native compact link-array linear and circular patterns, plus count/spacing/span updates. Source dimensions remain linked; placements are explicitly sampled when creating/updating patterns.
- Protected managed pattern controls and rejected nested body-feature sources in favor of the top-level Body.
- Fixed BREP export silently omitting link arrays. Added export/import roundtrips for STEP, BREP and STL, plus empty-geometry import/export rejection.
- Excluded internal native caches and display triangulations from link-array revision hashes; use geometry-based bounds independent of viewport meshing.
- Added a revolved, drilled and repeated flange example. Expanded validation to 61 automated tests and the combined native GUI workflow.

## 0.2.0 — 2026-10-16

- Added STEP/STP, BREP and STL imports into existing documents, including atomic import-plus-edit batches. Imported source hashes are checked before and after parsing.
- Added closed-mesh conversion to a native solid, preserving placement. Conversion is limited to 20,000 facets and requires exactly one closed shell.
- Added paginated edge, face and vertex inspection with lengths, areas, coordinates, surface/curve types and available radii. Degenerate edges remain inspectable.
- Added minimum-distance measurements between whole shapes or individual faces, edges and vertices.
- Added native, editable Part fillets and equal-distance chamfers, plus updates to their base-edge selections and sizes. Dependencies and editability survive native FCStd save/reopen.
- Added seven standard live view orientations.
- Hid consumed input features in background saves as well as live sessions; deduplicated native dependency references in inspection.
- Included mesh vertices/connectivity in revision hashing.
- Updated the generated start macro to reload code and rotate bridge credentials without closing open documents.
- Added a finishing example and expanded native, MCP and GUI checks. The suite now contains 35 passing tests.

## 0.1.0 — 2026-10-16

Initial live/background MCP integration, primitives, scalar parameter edits, placements, booleans, line/circle sketches, constraints/datums, pads/pockets, transactions/undo, FCStd save/open, STEP/STL/BREP export, live selection/capture, workspace confinement, source backups and an optional Responses API example. Validated by 19 automated tests and a native GUI smoke test.
