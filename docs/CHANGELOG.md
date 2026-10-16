# Changes

## 0.8.0 (GUI acceptance pending) — 2026-10-16

- Added a stable capability catalog, runtime schemas, read-only query dispatch, an extension edit envelope and a reload command. Existing typed operations remain compatible; future extension features do not change MCP tool schemas.
- Added generation-isolated source loading with relative helper snapshots, content fingerprints, atomic publication, stale-catalog guards and failed-load recovery. Configured extension roots are trusted startup configuration; tools accept no code or module paths.
- Moved the native dock and drag controller behind stable facades into a reloadable CAD panel extension. Reload preserves panel settings, pauses playback, removes old callbacks and restores the previous generation if UI rebuilding fails. Actual GUI verification remains user-run.
- Added installed tube creation and mass-property capabilities, native query rollback guards and rejection of generation-owned model/view proxies. A persistent stdio MCP test confirms new-feature discovery, identical tool schemas, unchanged native worker PID, failed-update recovery and preserved native models/Undo.
- Setup generates ReloadExtensions.FCMacro and supports explicit external extension directories for live and headless sessions. Portable native packages now include extension manifests and implementations.
- Native startup reports invalid extension configuration immediately, and repaired initial startup can retry through the same host client. Response queues are isolated per native worker so a retired reader cannot contaminate recovery. All 213 tests, lint/format checks, isolated wheel and portable-runtime native reload checks pass.

## 0.7.0 (GUI acceptance pending) — 2026-10-16

- Added the native Codex CAD dock with source-parameter inspection/editing, coupling controls, joint playback, viewport drag mode, overlap-pair highlighting and sampled-pose navigation. Setup generates a local panel macro and optional workbench folder.
- Added headless native checks of drag projection, forward/inverse coupled movement, half-turn crossing, cancellation, Undo and transaction isolation. Empty transaction cleanup handles clicks without movement and failures before the first change.
- Updated typed MCP/API discovery for 20 tools and 43 operations. Panel UI and physical mouse interaction require the user's manual check; no desktop interaction is used for the new automated controller checks.
- Added stored affine joint couplings with forward/inverse positioning, offsets, unwrapped coordinates, cycle/conflict guards and native save/reopen support.
- Added BREP overlap/contact/clearance checks and discrete motion sampling on a hidden native model copy, preserving source pose and Undo history.
- Revisions now hash mesh-free BREP content for all shapes, avoiding false changes caused by native document-copy caches.
- Added a portable coupled gearbox builder using FreeCADCmd only, with four saved ratios, 18 sampled gear checks, a fresh-process inverse-drive/Undo check and a local panel launcher. Versioned packaging records headless validation separately from pending GUI/mouse acceptance.

## 0.6.0 — 2026-10-16

- Added native Assembly containers, parametric component links, grounding and fixed/revolute/slider joints with explicit local connector frames.
- Added coordinated absolute joint positioning for directed trees, travel limits, native solver/residual checks and assembly inspection. Joint positioning is transactional and undoable; standard FreeCAD workbench proxies survive save/reopen.
- Protected managed assembly fields from generic property, placement and expression writes. Added 21 native assembly tests, stdio MCP dispatch, live GUI checks and signed half-turn travel-limit handling.
- Added a linked rotary-arm/slider example and a jointed planetary demonstration with 15 components, 14 joints, an analytical 4:1 driver, 60 rendered frames and portable native Play/Pause/Reset controls. Fixed Reset callback reentrancy and checked actual model coordinates in an isolated player session.

## Demo additions — 2026-10-16

- Added an editable 26-solid cutaway planetary gearbox using native involute profiles and the existing structured modeling engine, with a colored STEP export and separate exploded presentation.
- Added an isolated native build/render runner and verified saved-file geometry, static gear clearances, STEP preservation and parameter edits/undo after reopen.

## 0.5.0 — 2026-10-16

- Added native cylindrical/conical helices with handedness, taper validation and editable/expression-driven pitch, height and radius. Helical solid sweeps are checked against analytic wire volume and native save/reopen behavior.
- Added native Part solid/surface sweeps with ordered sections, single-wire or topology-selected edge paths, Frenet framing and three native corner transition modes.
- Added sweep profile/path/control updates, dependency-cycle guards, native save/reopen propagation, analytic geometry checks and MCP schema dispatch coverage.
- Added an example combining an expression-driven hollow elbow and helical solid, with FCStd/STEP output from either backend and an explicit 1e-5 relative volume tolerance.

## 0.4.0 — 2026-10-16

- Added native solid/surface lofts through ordered single-wire profiles, including ruled surfaces, profile replacement and closed-wire validation.
- Added parametric native mirrors with explicit document-space planes and plane updates; the result contains reflected geometry only.
- Added native named length, angle, number and integer parameter containers.
- Added arithmetic expressions on numeric feature properties, placement translations and named/indexed dimensional sketch constraints, with dependency propagation and explicit expression removal.
- Exposed expression bindings in object/document inspection and prevented direct datum/placement writes from silently overriding expression-driven values.
- Restricted new expression input to arithmetic, units, pi and numeric references inside the same document; invalid units, cycles and failed recomputes roll back the transaction.
- Added a parameter-driven loft/mirror example for both backends, expanded MCP/native/live validation, and committed the implementation in separate increments. Origin is configured; pushing remains a manual user action.

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
