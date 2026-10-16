# Validation record — v0.5.0 — 2026-10-16

**135 automated tests pass**, with zero failures, errors or skipped cases, on native FreeCAD 1.0.2, host Python 3.13 and MCP SDK 2.3.0. The integration exposes 17 MCP tools and 34 structured edit operations. The installed native engine reports revision `39319`, source commit `256fc7eff3379911ab5daf88e10182c509aa8052` and bundled Python 3.11.13.

The 33 added native cases cover straight and curved sweeps, full-circle torus paths, multiple sections, open-profile surfaces, closed-section guards, profile/path replacement, Frenet and sharp-corner transition modes, invalid selections/controls, disconnected edges, dependency cycles and atomic rollback. Helix checks cover native length, both handedness directions, conical endpoint radius, invalid dimensions/taper/turn limits, helical solid volume and expression-driven save/reopen propagation. Stdio MCP dispatches all three new operations through the typed schemas. The earlier 102 checks remain passing.

The isolated native GUI workflow passes **27 recorded checks**, including all earlier coverage. New checks create the hollow elbow and helical solid, update named coil height and section radius through native dependencies, undo those edits, update a topology-selected spine and framing/corner options, roll back invalid path selection after an earlier parameter edit, and preserve both solids through STEP and BREP roundtrips. The MCP path updates/undoes a native sweep. The GUI exits cleanly and removes bridge credentials. No existing user FreeCAD session/model was used.

The sample elbow has 30 mm centerline radius, 6 mm outer section radius and 4 mm inner section radius over a quarter-circle path. Its analytic volume is `pi*(6^2-4^2)*30*pi/2` = **2960.8813203268073 mm³**. The coil has a 15 mm centerline radius, 10 mm pitch, 40 mm axial height and 2 mm wire radius; analytic volume is `pi*2^2*sqrt((2*pi*15*40/10)^2+40^2)` = **4764.00214598 mm³**. The combined analytic volume is **7724.883466306807 mm³**; native measurement is **7724.8849421043815 mm³**, a relative difference of approximately **1.91045e-7**, within the declared **1e-5** tolerance. Native helical curves/surfaces are approximated; exact numerical equality is not claimed.

The final disconnected union contains two valid solids, seven faces and nine edges. Its bounds are approximately `[0,-17,-6]` through `[97,36,41.988836]` mm. The native screenshot was visually inspected and shows the elbow bore and four-turn coil. This is geometric validation, without spring-end finishing or engineering spring-performance calculations.

The v0.5.0 wheel was installed without dependencies into a fresh target and imported with an isolated host interpreter. Its packaged worker reported 34 operations and passed native helix/sweep volume checks, BREP export/reimport and height-driven recomputation after FCStd save/reopen. Lint, formatting and dependency checks pass. Release packaging uses the clean committed source tree, records its Git commit, verifies source-archive hashes, compares wheel Python files with the archive and records native/analytic sample volumes and tolerance in the manifest.

Both backends are validated on this installed native version. Paid OpenAI API execution, plugin-browser installation, other FreeCAD versions/platforms and broad assembly/workbench coverage remain unverified. No push was performed by this agent; origin pushing remains the user's step.

## Historical validation — v0.4.0

**102 automated tests pass**, with zero failures, errors or skipped cases, on native FreeCAD 1.0.2, host Python 3.13 and MCP SDK 2.3.0. FreeCAD reports revision `39319` and source commit `256fc7eff3379911ab5daf88e10182c509aa8052`; its embedded Python is 3.11.13. The integration exposes 17 MCP tools and 31 structured edit operations.

The 41 additional native cases cover named parameter types, dimensional expression propagation/removal, units/local references/pi, placement expressions, named/indexed sketch constraint expressions, invalid syntax/paths/units/nonfinite input, dependency cycles, whole-batch rollback, invalid parameter definitions, expression guards and FCStd save/reopen. Loft/mirror coverage includes ruled/smooth solid loft volumes, multi-section/profile updates, open-wire surfaces, closed/multiple-wire guards, nested-source guards, rotated/oblique plane geometry, plane updates, dependency changes/undo, link-array mirrors and save/reopen propagation. Stdio MCP exercises all seven new operations through the typed server schemas. All earlier tests remain passing.

The isolated native GUI smoke test passes **22 recorded checks**. In addition to the earlier 17-check scope, it exercises parameter-driven fully constrained profiles, native loft/mirror dependencies, height changes and native undo, stale revisions, incompatible expression units with earlier edits rolled back, expression removal followed by direct placement, loft/plane updates and undo, and two-solid STEP preservation. Its MCP path edits and undoes a design parameter before capturing the restored model. The GUI exits cleanly and deletes its bridge credentials. The log's unit-mismatch exceptions are expected output from the rejected-expression negative control.

The included sample has two circular-section frusta. Each has a 20 mm base radius, 10 mm top radius and 45 mm height; the second is mirrored across the X=40 mm plane. The disconnected boolean union retains two solids without bridging the gap. Analytic total volume is `2*pi*45*(20^2+20*10+10^2)/3` = **65973.44572538565 mm³**; native volume matches that value. The final shape is valid with two solids, six faces and six edges. Bounds are approximately `[-20,-20,0]` through `[100,20,45]`, including native 1e-7 mm tolerance. The native screenshot was visually inspected and shows both tapered solids.

The v0.4.0 wheel was installed without dependencies into a fresh target, then imported with an isolated host interpreter. Its packaged worker reported 31 operations and passed native parameter/expression/loft/mirror volume checks, two-solid BREP export/reimport and expression-driven recomputation after FCStd save/reopen. Lint, formatting and dependency checks pass. Release packaging requires a clean committed source tree, records its current Git commit, verifies source-archive hashes and compares wheel Python files byte-for-byte with that archive.

Both native backends are validated on this installed FreeCAD version. Paid OpenAI API execution, plugin-browser installation, other FreeCAD versions/platforms and broad workbench/assembly support remain unverified. No existing user FreeCAD session/model was used for testing. No push was performed by this agent; origin pushing remains the user's step.

## Historical validation — v0.3.0

The current release has **61 passing automated tests**, with no failures or skipped cases, on native FreeCAD 1.0.2, host Python 3.13 and MCP SDK 2.3.0. Earlier 35-test coverage remains; the 26 added native cases cover dimensioned/offset/construction rectangles, named datum edits, arc-based solids, sketch append/rollback, 2D validation, solid/surface and positive/negative/partial revolutions, rotated-source linear arrays, full/partial/negative circular spans, source-dimension propagation, sampled placement semantics, pattern count updates/undo, managed-field/dependency guards, native save/reopen, root-Body handling, all-instance exports and empty-geometry negative controls. Stdio MCP also exercises rectangle/revolution/pattern schemas and the new sketch inspection tool.

The live workflow passes 17 recorded checks, including previous import/fillet/chamfer/view/reload checks and an arc-profile pad, constrained profile/native revolution, six-hole circular tool pattern, and three-instance row of finished flanges. It checks source-dimension and count propagation with undo, verifies a display/STL export does not invalidate revision guards, and reimports the exported STEP to verify all three solids remain present. The native PNG was visually inspected and shows the three flanges with their bores and six-hole patterns.

Each flange has outer radius 30 mm, bore radius 10 mm and thickness 8 mm, with six radius-2 mm through-holes on a radius-22 mm bolt circle. Three instances are spaced 75 mm along X. Analytic volume is `3*pi*((30^2-10^2)*8 - 6*2^2*8)` = **58509.021580456305 mm³**. Native measurement is **58509.02158045633 mm³**, three valid solids, thirty faces and seventy-two edges. Native bounds are `[-30,-30,0]` through `[180,30,8]` within floating-point precision.

Native link arrays have separate instances and sampled source placements, not fused material or general assembly constraints. These checks establish specific CAD behavior on FreeCAD 1.0.2, not manufacturing or physical-part acceptance. Paid OpenAI API execution, plugin-browser installation, other FreeCAD versions/platforms and broad workbench/assembly support remain unverified. Versioned XML, native reports, source/wheel packages and sample files are supplied alongside the chat handoff.

The v0.3.0 wheel was installed into a fresh target and imported by an isolated host interpreter. Its packaged native worker reported 24 operations, created a fully constrained rectangle, native revolution and three-instance link array, returned detailed sketch data, and preserved all three solids through BREP export/reimport. Lint, formatting and dependency checks passed. The release packager checks the native report version and compares wheel Python files byte-for-byte with the source archive.

## Historical validation — v0.2.0

Validated on Windows with host Python 3.13, MCP SDK 2.3.0, and installed FreeCAD 1.0.2 (`39319`, commit `256fc7eff3379911ab5daf88e10182c509aa8052`). FreeCAD's embedded interpreter reports Python 3.11.13. No existing user model was edited.

## Automated suite

**35 tests pass.** The original 19 checks remain, covering dimensions, volume, undo/rollback, revision guards, booleans, sketch constraints/datums, pad/pocket recomputation, FCStd save/reopen, exports/backups, workspace/schema boundaries, stdio MCP and the local API adapter.

The 16 added native checks cover topology pagination and measurements, sphere degenerate edges, circular radii, object/face/vertex distances, fillet/chamfer analytic volumes, native dependency propagation, edge-size updates and undo, invalid/duplicate/oversized edge selections with whole-batch rollback, STEP/BREP/STL source-preserving import and undo, placed STL-to-solid conversion followed by a boolean cut, open-mesh and malformed-import rejection, stale-import/path guards, and imported fillet editability after FCStd save/reopen. The stdio MCP test also exercises new import/topology/distance/fillet tools and rejects GUI-only view control in background mode.

The finished sample starts as an 80 × 50 × 8 mm plate with a radius-5 mm through-hole centered at X=15, Y=15. Four outer vertical corners receive radius-3 mm fillets, and the top hole edge receives a 0.8 mm equal-distance chamfer.

Expected volume in mm³: `80*50*8 - pi*5^2*8 - (4-pi)*3^2*8 - pi*(5*0.8^2 + 0.8^3/3)`.

Native measured volume is **31299.2868787028 mm³**, one valid solid, twelve faces and twenty-nine edges. Bounds match `[0,0,0]` through `[80,50,8]` within native floating-point precision. The live STEP reimport retains the measured volume. That observation and a zero minimum-distance query do not establish whole-file or complete geometric identity.

## Native GUI smoke test

An isolated FreeCAD GUI process passed these checks:

1. Bridge startup and authenticated native status.
2. Missing/wrong tokens rejected with HTTP 401; browser Origin rejected with 403; malformed JSON rejected with 400.
3. Model creation through the GUI thread.
4. Generated start macro reloading code, rotating credentials and preserving the open native model.
5. Topology-selected fillets/chamfers matching the analytic volume above.
6. All seven standard live view orientations.
7. Live selection query and native 1200 × 900 PNG capture.
8. Native FCStd saving and STEP export.
9. STEP reimport, volume comparison and minimum-distance query.
10. STL import and placed closed-mesh conversion to a valid solid.
11. Live stdio MCP discovery, topology/view tools and 800 × 600 image response.
12. Clean GUI process exit and removal of the bridge credential file.

The native PNG was visually inspected and shows the rounded outer corners and chamfered hole. The test process closed its own documents and exited. Raw XML test results, GUI logs and JSON results are under ignored `work`; versioned user-facing samples are provided separately in the chat outputs. The original v0.1.0 source ZIP and samples remain there.

## Package checks

The v0.2.0 wheel was installed into a fresh target directory and imported by an isolated host Python process. Its packaged FreeCAD worker reported version 0.2.0 and 18 operations, created a valid native fillet matching analytic volume, and returned the expected face topology. Ruff lint/format and `pip check` passed. Versioned source/wheel files are compared byte-for-byte against a manifest; bundles exclude virtual environments, credential/state files, test workspaces and machine-specific plugin configuration.

## Verification boundaries

Actual native geometry, editability/recomputation, local stdio MCP, the loopback GUI bridge, source preservation, undo/rollback and model save/reopen are exercised. The optional API example has local schema/result tests; no paid OpenAI API run has been performed. Plugin-browser installation, remote/cloud access, other FreeCAD versions, non-Windows platforms, general workbench compatibility and untrusted CAD-file isolation remain unverified. This work does not modify global Codex registration or attach new tools to an already-running chat.

FreeCAD shape validity and measured dimensions are CAD evidence. They do not establish manufacturing tolerances, design adequacy, assembly fit or physical part correctness.
