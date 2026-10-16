# Validation record — v0.9.0 — 2026-10-16

After relocating the checkout to `CodexFreeCADPlugin`, **33 configuration/registry tests pass**. Environment launchers and local FreeCAD macros use the new absolute path, all 37 dependency versions are unchanged, and fresh native hardware checks again save/reopen 23 valid solids, match the analytic volume, pass all 253 static part-pair checks with zero positive-volume overlaps, and roundtrip STEP. The earlier full 248-test run below predates the directory rename; it was not repeated for this path-only change. GitHub remote verification returned 404 with current access; the requested origin URL is configured locally.

**248 automated tests pass**, with zero failures, errors or skipped cases (520.66 seconds). Ruff lint/format and pip dependency checks pass. The new hardware extension suite contributes **35 passing native tests** on FreeCAD 1.0.2. It covers through/blind bores, counterbores, countersinks, circle layouts, normalized arbitrary directions, native parameter expressions, refreshing after base resizing, countersink angle edits, rollback, Undo, name conflicts, no-hit/empty results, head/socket/nut/washer dimension checks, placement and save/reopen. Lengths are mm; blind bottoms are flat and fastener geometry is unthreaded. All 24 fixed MCP tools and 44 structured operation kinds remain unchanged; six capabilities are discovered at runtime.

A persistent stdio MCP connection installs the actual hardware packages under separate test IDs after connection. It loads their schemas and creates native geometry without changing the tool schemas, backend PID, existing source revision or Undo. A malformed subsequent extension update is rejected while the prior generation still creates washers. Fresh native workers reopen and edit the saved native features without those external packages configured.

A separate isolated compatibility run uses the previously packaged **v0.8.0 core**, initially without hardware extensions. Installing the two new packages and calling reload adds their original capability IDs to the same native worker. Source revision and previous Undo entries survive. The old core creates a counterbored plate and socket bolt, saves them, then reopens/recomputes them in another v0.8 worker with no hardware extension installed. This directly checks the existing-core update path; the native core's cached version string remains 0.8.0.

The new **HardwareDemo** has 23 selected valid solid instances: a center-bored/counterbored flange with six socket bolts, washers and nuts, plus a hole coupon with blind/countersunk/clearance bores and hex hardware. Independent formulas give **91266.21977712106 mm³**; native STEP roundtrip volume is **91266.21977712058 mm³** (1e-6 relative roundtrip tolerance). All **253** BREP part-pair checks find **zero positive-volume overlaps**, with 21 seating contacts and 232 clear pairs. This is static geometric evidence, without thread contact, fit, torque or load claims. No source CAD inputs are overwritten.

The demonstration caught a small native volume/extent discrepancy when nearly coincident cutter caps crossed chained cylindrical features. Cutter end-plane padding now clears the boolean edge tolerance; a dedicated regression checks the expected analytic volume at 1e-10 relative tolerance and unchanged outer bounds at 1e-7 mm. Hex native expressions use `sqrt(3)` directly to retain their formulas across serialization.

The built v0.9.0 wheel and a copied portable native runtime each pass isolated `-I -S` host checks: installed schema discovery, native counterbored circle and bolt/nut/washer construction, analytic flange volume, same-size/same-timestamp helper reload, unchanged worker/source revision, FCStd reopen without the external helper and native dimension editing. Source/wheel Python and JSON file sets and bytes are verified during packaging.

Native Undo restores the reopened demonstration's dimensions and geometry. Recomputed BREP serialization can change the conservative revision token after Undo; callers should inspect the current token before a further guarded edit. No-op reloads and extension publication themselves preserve the source revision, as explicitly tested.

**GUI display, real dock reload and physical dragging remain pending the user's manual checks.** All new native runs use FreeCADCmd; this agent does not launch a GUI or send desktop input. [Hole/fastener arguments and limitations](HOLES_FASTENERS.md) and [extension reload instructions](EXTENSIONS.md) describe the supported workflows.

## Historical validation — v0.8.0 — 2026-10-16

**213 automated tests pass**, with zero failures, errors or skipped cases, on native FreeCAD 1.0.2, host Python 3.13 and MCP SDK 2.3.0. Ruff lint/format checks and pip dependency checks pass. The interface has **24 fixed MCP tools and 44 structured operation kinds**, including the stable extension envelope. The optional Responses adapter discovers 23 text-result tools without paid API execution. Installed API v1 extensions provide the dock/controller plus tube creation and mass-property capabilities.

The persistent stdio MCP test uses one client connection and confirms identical tool-schema JSON before/after an update. It changes same-size/same-timestamp helper source, adds a new edit capability and arguments, reloads, discovers its schema and creates native geometry. The original FreeCAD worker PID stays the same. Model revisions and prior Undo survive successful and failed reloads; a syntax error retains working code, and a stale catalog token is rejected. A fresh native process reopens extension-created native geometry without the external extension installed.

Additional cases cover late relative imports bound to the old snapshot after a rejected update, package removal, multi-package atomic staging, strict runtime argument validation/defaults, query/edit role separation, query-mutation rollback, mixed-batch rollback, active-edit exclusion and rejection of generation-owned feature proxies. The initial-startup repair case found a retired-reader queue leak; response queues now belong to individual native workers, and repair/retry passes without replacing the host client. Timeouts with an unknown outcome retain the existing disabled-session behavior.

The native sample is a parametric sleeve constructed through `parts.create_tube`, using two ordinary native cylinders and a cut. Outer radius 10 mm, inner radius 6 mm and height 20 mm give analytic volume `pi*(10^2-6^2)*20` = approximately **4021.238596595 mm³**. Native volume agrees within 1e-9 relative tolerance. Its volume-weighted center is `[0,0,10]` mm, and the density query uses 7800 kg/m³. The one-solid STEP roundtrip agrees within 1e-6 relative tolerance; FCStd reopens valid native features in a fresh worker. A query and unchanged reload preserve model revision, and the no-op reload keeps the same native process.

The built v0.8.0 wheel and a separately copied portable native package were each imported through isolated host interpreters (`-I -S`). Both packaged workers create the sleeve, read mass properties, reload same-size/same-timestamp helper changes without changing worker PID or source revision, then reopen FCStd without the external test extension. Installed extension Python files and JSON manifests are part of source/wheel package verification.

**Actual GUI reload, Qt panel reconstruction and physical dragging remain pending the user's manual check.** UI lifecycle publication and restoration-failure recovery have explicit test doubles without a native GUI. The user-run isolated harness additionally contains checks for real dock reconstruction, paused playback, selector/pose preservation and unchanged live bridge/token before holding its arm for mouse testing. Those GUI checks were not run by this agent; no GUI instance or desktop interaction was used for this continuation. [Extension workflow and scope](EXTENSIONS.md) describes the one-time v0.8 core migration and subsequent command-driven reloads.

## Historical validation — v0.7.0

**180 automated tests pass**, with zero failures, errors or skipped cases, on native FreeCAD 1.0.2, host Python 3.13 and MCP SDK 2.3.0. Ruff lint and formatting checks pass, and pip reports no broken requirements. The v0.7.0 wheel was installed into a fresh target and imported with an isolated host interpreter (`-I -S`); its own packaged native worker created a coupled arm, sampled it without changing the revision, saved FCStd and reopened the saved ratio/pose in a fresh worker.

The engine exposes **20 MCP tools and 43 structured edit operations**. New native checks cover persistent affine coupling, forward/inverse mixed-unit positioning, unwrapped turns, dependency chains, cycle/conflict guards, limits, rollback, Undo, and FCStd save/reopen. Typed stdio MCP exercises both coupling operations and both interference tools. The optional Responses adapter discovers 19 text-result tool schemas without a paid API call.

Native BREP tests distinguish a known 500 mm³ box overlap, zero-volume contact, a 2 mm gap and insufficient clearance. Motion sampling detects a collision between clear endpoints while preserving the source revision, pose and preceding Undo, and closes its hidden copy after failure. A three-joint dependency chain confirms inverse sampling coordinates and rejection of a cycle without changing the source revision.

The native drag-controller test runs through **FreeCADCmd without FreeCADGui or desktop input**. It checks revolute-plane and slider-axis projection, camera singularities, component/source picks, movable-parent lookup, forward/inverse coupled movement, signed half-turn crossing, cancellation, one-gesture Undo, clicks without movement and active-edit isolation. Early validation and empty-transaction cleanup are tested on the installed FreeCAD 1.0.2. These tests do not establish physical mouse picking or Coin event delivery.

The upgraded portable gearbox retains **15 linked components, 14 joints and 26 valid solids**, with native volume **204502.9106778577 mm³**. Four saved affine rules give carrier = sun/4 and planet-relative-to-carrier = -3*sun/4. The STEP roundtrip retains 26 valid solids within 1e-6 relative volume tolerance. Eighteen discrete input angles from 0 through 360 degrees have zero positive-volume overlaps among the sun and three planet gears. This new sample set excludes housing/full-ring intersection checks and continuous travel; earlier full-ring checks are recorded below. A hidden-copy sample leaves source pose and revision unchanged. A fresh native process reopens the saved FCStd, drives the carrier to 300 degrees (sun 1200, planet relative coordinates -900), then Undo restores the zero pose. Original input bytes and saved model bytes remain unchanged by verification.

**New dock GUI validation and physical dragging remain pending the user's manual check.** A user-run isolated panel harness checks the Qt controls, source-dimension edit/Undo, connection controls, sampling/navigation and callback registration before holding a simple arm model for manual dragging. See [PANEL_TESTING.md](PANEL_TESTING.md). No GUI instance, desktop input or existing user FreeCAD session was used for this continuation. Packaging supports an explicitly labeled headless report and does not reuse historical GUI checks as v0.7 evidence.

## Historical validation — v0.6.0

**156 automated tests pass**, with zero failures, errors or skipped cases, on native FreeCAD 1.0.2, host Python 3.13 and MCP SDK 2.3.0. The integration now exposes **18 MCP tools and 41 structured edit operations**. The 21 added native assembly cases cover linked geometry, native grounding and fixed/revolute/slider joints, coordinated poses, arbitrary connector orientations, fixed children, whole-turn angle wrapping, signed half-turn limit boundaries, travel-limit rejection/removal, malformed/self/outside references, protected managed properties, duplicate/invalid coordinates, disconnected components, revision guards, atomic rollback, Undo and moving assemblies after FCStd reopen. Stdio MCP dispatches the seven assembly operations and inspection through the typed schemas. The optional API adapter retains the new inspection tool in its 17 text-tool schemas without a paid API call.

The isolated native GUI workflow passes **30 recorded checks**, including native assemblies with an oblique slider, coordinated joint motion through the authenticated live bridge, travel-limit rollback, Undo, FCStd save and a three-solid STEP roundtrip. MCP edits and reads actual joint coordinates in that same GUI session. Floating-point placement comparisons use a tolerance, including equivalent quaternion signs. The GUI exits cleanly and removes its bridge credentials. Existing user FreeCAD windows and documents were not used.

The jointed planetary demonstration reopens with **15 linked components, 14 native joints, one grounded base and 26 valid positive-volume solid instances**. Total native volume is **204502.9106778577 mm³**. All components connect to ground. Its 18/18/54-tooth fixed-ring analytical driver uses carrier angle = input/4 and absolute planet spin = -input/2. At 13 sampled input angles from 0 through 1440 degrees in 120-degree increments, joint coordinates agree with the driver, all solids remain valid, volume is conserved within 1e-9 relative tolerance, and all measured sun/planet and planet/full-ring intersections are **0.0 mm³**. Native Undo restores the prior coordinated pose. STEP export at a moved pose retains 26 valid solids and volume within 1e-6 relative tolerance. The original static input is preserved, and verification does not resave the jointed input.

Sixty native viewport frames show motion over 480 input degrees, one third of a carrier revolution; the geometry repeats by threefold symmetry. A 900×750, 60-frame looping GIF was encoded from those CAD captures. The portable Play/Pause/Reset/slider player was exercised as an actual FCMacro in a fresh isolated GUI using only its adjacent native modules. Reset was verified against model coordinates, and closing the panel stops its timer. The test found and fixed event-loop reentrancy caused by forcing a viewport update inside a motion callback.

Five additional nonperiodic input angles (5, 11, 23, 47 and 89 degrees) also give zero measured gear intersections. The combined sample covers 18 poses and 108 sun/planet or ring/planet Boolean intersection checks. A separate native check confirms the saved joints use installed `JointObject` proxies and leaves the model SHA-256 unchanged. The v0.6.0 wheel was installed into a fresh target, imported with an isolated host interpreter and exercised through its packaged FreeCADCmd worker: 41 operations, coordinated joint motion, FCStd reopen/move, linked volumes and a three-solid BREP roundtrip pass. Dependency, lint and formatting checks pass.

Position commands support directed trees rooted at grounded components. Native workbench `JointObject` proxies persist in the file; integration proxies and extra drive joints do not. The demo controller coordinates gear ratios analytically; native gear-ratio constraints, closed-loop driving, nested assemblies, continuous collision/contact, loads and dynamics are outside this validation. Paid API execution and plugin-browser installation remain untested. Local commits are retained; the user performs origin pushes.

## Historical validation — v0.5.0

**135 automated tests pass**, with zero failures, errors or skipped cases, on native FreeCAD 1.0.2, host Python 3.13 and MCP SDK 2.3.0. The integration exposes 17 MCP tools and 34 structured edit operations. The installed native engine reports revision `39319`, source commit `256fc7eff3379911ab5daf88e10182c509aa8052` and bundled Python 3.11.13.

The 33 added native cases cover straight and curved sweeps, full-circle torus paths, multiple sections, open-profile surfaces, closed-section guards, profile/path replacement, Frenet and sharp-corner transition modes, invalid selections/controls, disconnected edges, dependency cycles and atomic rollback. Helix checks cover native length, both handedness directions, conical endpoint radius, invalid dimensions/taper/turn limits, helical solid volume and expression-driven save/reopen propagation. Stdio MCP dispatches all three new operations through the typed schemas. The earlier 102 checks remain passing.

The isolated native GUI workflow passes **27 recorded checks**, including all earlier coverage. New checks create the hollow elbow and helical solid, update named coil height and section radius through native dependencies, undo those edits, update a topology-selected spine and framing/corner options, roll back invalid path selection after an earlier parameter edit, and preserve both solids through STEP and BREP roundtrips. The MCP path updates/undoes a native sweep. The GUI exits cleanly and removes bridge credentials. No existing user FreeCAD session/model was used.

The sample elbow has 30 mm centerline radius, 6 mm outer section radius and 4 mm inner section radius over a quarter-circle path. Its analytic volume is `pi*(6^2-4^2)*30*pi/2` = **2960.8813203268073 mm³**. The coil has a 15 mm centerline radius, 10 mm pitch, 40 mm axial height and 2 mm wire radius; analytic volume is `pi*2^2*sqrt((2*pi*15*40/10)^2+40^2)` = **4764.00214598 mm³**. The combined analytic volume is **7724.883466306807 mm³**; native measurement is **7724.8849421043815 mm³**, a relative difference of approximately **1.91045e-7**, within the declared **1e-5** tolerance. Native helical curves/surfaces are approximated; exact numerical equality is not claimed.

The final disconnected union contains two valid solids, seven faces and nine edges. Its bounds are approximately `[0,-17,-6]` through `[97,36,41.988836]` mm. The native screenshot was visually inspected and shows the elbow bore and four-turn coil. This is geometric validation, without spring-end finishing or engineering spring-performance calculations.

The v0.5.0 wheel was installed without dependencies into a fresh target and imported with an isolated host interpreter. Its packaged worker reported 34 operations and passed native helix/sweep volume checks, BREP export/reimport and height-driven recomputation after FCStd save/reopen. Lint, formatting and dependency checks pass. Release packaging uses the clean committed source tree, records its Git commit, verifies source-archive hashes, compares wheel Python files with the archive and records native/analytic sample volumes and tolerance in the manifest.

Both backends are validated on this installed native version. Paid OpenAI API execution, plugin-browser installation, other FreeCAD versions/platforms and broad assembly/workbench coverage remain unverified. No push was performed by this agent; origin pushing remains the user's step.

## Planetary gearbox demonstration — 2026-10-16

The additional native example builds an 18/18/54-tooth cutaway gearbox with three planet gears, a 152 mm base plate, a three-arm carrier, shafts, washers and socket-head fasteners. FreeCAD's built-in PartDesign involute utility creates the editable profiles; the integration engine constructs downstream solid features. Two native external profiles use a -0.01 profile-shift coefficient to provide clearance in this arrangement. The colored presentation and exploded snapshots were rendered and visually inspected in an isolated FreeCAD GUI.

After native FCStd reopen, all **26 solid instances** across 13 visible component groups are valid and positive-volume. Native total volume is **204502.91067785767 mm³**. The colored STEP roundtrip retains 26 valid solids with volume **204502.91067778438 mm³**, within 1e-6 relative tolerance. All three sun/planet and planet/full-ring Boolean intersections measure **0.0 mm³** in this static arrangement. This is a geometry/layout check, not a motion or load validation.

Using the shared engine after reopen, changing `Design.GearWidth` from 12 to 11 mm changes sun-gear volume by the expected 11/12 factor; Undo restores the original. Changing `Design.CutawayAngle` to 110 degrees produces a valid housing; Undo restores it. Verification leaves the source file bytes unchanged. The separate exploded document also reopens with 26 valid solids; it contains independent presentation snapshots. Lint and formatting checks pass for the additional builder/renderer. No MCP operation or release version changed for this example.

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
