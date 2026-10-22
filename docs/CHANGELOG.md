# Changes

## Unreleased

- Fenced proxy auto-start across explicit idle-host activation, preventing an idle chat from relaunching the old framework runtime between shutdown and replacement startup. Doctor must pass before that startup fence is released. Existing native-work preservation and disabled tray restart remain separate boundaries.
- Updated the app-owned host to framework 0.18.0 while retaining MCP 2.3.0. Added cached tray status, exact standalone plugin association, distinct process identities, component versions and CAD-facing operation counts. A background collector reads only local metadata/journals and the cached catalog. Tray restart remains disabled with an app-specific supervision/state-preservation reason; the installer never installs a duplicate manager or changes the selected connection. Private fixtures cover reporting, concurrency, cancellation, denial, duplicate receipts, lost replies and process-restart barriers without native CAD effects.
- Aligned the app-owned runtime with verified framework 0.17.0 while retaining MCP 2.3.0 and the standalone plugin. Added explicit `-Upgrade` staging, read-only idle/journal checks and a host doctor. Runtime upgrades retain old environments, publication/plugin backups, workspace and original journals; retained or ambiguous work blocks shutdown without automatic acknowledgment or effect replay. Optional notification, relay, UI, OAuth and Redis deployment adapters remain unselected.
- Fixed immediate reconnect during shutdown: startup waits for the old host's OS-owned state lock to be released after its network port closes, preventing a premature replacement process.
- Added an explicit app-owned framework installer with trusted artifact hashes, application wheel/source audits, installed-byte readback, dedicated runtimes, local backups and preservation of the standalone plugin identity. App-host `start`/`connect` commands coordinate concurrent startup and reconnect without a universal daemon or native CAD calls. Normal setup and the root launcher preserve an explicitly installed host selection; invalid selections fail without route fallback. Existing host state and publications require deliberate update/release rather than installer overwrite.
- Removed the broker route, automatic Universal Tools detection, broker registration manifests and broker-specific server option. Windows setup and the root launcher install FreeCAD's own standalone Codex plugin; `-Integration none` skips client changes. Removed installer options fail before changing configuration. Direct MCP endpoints remain available independently.
- Aligned the experimental app-owned host with `universal-codex-tools==0.17.0` and its MCP 2.3 runtime lock. Publications retain legacy protocol by default, explicit modern candidate options, exact write allowlists and immutable application/extension closures. Structural argument budgets reject oversized inputs before schema validation, write claims or CAD dispatch. Disposable-provider profiles cover legacy/modern frontends, ownership, publication, result/media preservation and durable recovery. Optional Tasks/Skills adapters are not enabled; native jobs and host skill activation remain separate integration work. Installation requires explicit selection.
- Windows setup now creates a per-user Start menu shortcut with the supplied F-and-gear application icon in eight sizes from 16 to 256 pixels. The shortcut preserves the selected backend/workspace/executable and skips dependency installation on launch. Both installers offer `-NoStartMenuShortcut` for unattended or portable setup.
- Added a root `Install-and-Run.cmd` launcher that reuses setup, supports live/headless modes and custom workspaces, offers install-only/existing-install options, and preserves MCP stdout by routing setup/status output to stderr.
- Added reloadable saved design requirement sets for numeric properties, volume, known-density mass, axis extents and BREP clearance/overlap. Native source links, explicit tolerances, pass/fail/error reports and a final enforcement operation support opt-in batch rollback. Change previews evaluate selected sets on the hidden copy and append revision/catalog-guarded checks to the apply plan. Added a shaft/sleeve example and a public feature roadmap.
- Added multi-property numeric change previews on hidden native dependency copies. Reports include before/after geometry, optional mass, BREP added/removed material and revision-bound arguments for a separate atomic apply. Native tests cover equal-volume reshaping, expression propagation, source/Undo preservation, stale edits, failure cleanup and same-connection helper reload recovery.
- Extension staging now compiles every Python helper before publication, including lazy imports, so syntax failures retain the working generation. The engineering plate example verifies preview material differences across three native linked instances.
- Added reloadable native TechDraw sheets, orthographic projection snapshots, numerically checked extent dimensions, explicit refresh and GUI-independent SVG rendering. Stale source geometry is rejected until refresh; native Qt core dispatch completes headless projections without a GUI window.
- Added reloadable parameter sweeps on hidden native dependency copies, optional density-based mass and frozen native configuration snapshots. Queries preserve source revision/Undo, clean up failed samples and reject expression-driven or unsupported inputs.
- Added a reloadable BOM extension with explicit part/assembly selection, source-aware link quantities, native part metadata, known-density mass, escaped CSV and refreshable native spreadsheet snapshots. Native tests cover Undo, failure rollback and save/reopen.
- Reorganized the root README around installation, usage, API and contribution guidance, with detailed tool and example reference pages.
- Added public-repository hygiene guidance and an ignored `local/` directory for private notes. Removed workstation-specific paths and session logs from public documentation and generated release guides.

## Project rename — 2026-10-17

- Renamed the project and repository to `FreeCADMCPServer`, including generated display names and source archives. The Python distribution/CLI (`codex-freecad`), module (`codex_freecad`) and plugin ID (`freecad-modeling`) remain compatible.

## 0.9.0 (GUI acceptance pending) — 2026-10-16

- Added installed `holes` and `fasteners` extensions through the existing stable capability interface. Fixed MCP schemas and native modeling core remain compatible with v0.8 feature reloads.
- Added simple through/blind holes, counterbores, countersinks, full bolt-circle layouts and through-extent refresh. Every bore/recess must remove material, and invalid/no-hit/empty-result edits roll back the complete batch. Native cylinders/cones, expressions and booleans preserve editable dimensions without saved extension proxies.
- Added explicitly dimensioned hex and socket-cap bolts, hex nuts and plain washers with position/axis/spin controls. Geometry is simplified and unthreaded; no standard size, fit, load or automatic mating claims are made.
- Added native geometry, parameter, transaction, reopen and persistent-MCP reload coverage, including a chained cylindrical-cut regression. Cutter end planes extend clear of the native boolean edge tolerance. Native expression functions retain exact hex dimension formulas across serialization.
- Added a headless 23-solid hardware demo, independent analytic volume formulas, 253 BREP pair checks with zero positive-volume overlaps and FCStd/STEP persistence checks. Added isolated wheel/portable and v0.8-core compatibility checks. GUI interaction requires separate manual validation.

## 0.8.0 (GUI acceptance pending) — 2026-10-16

- Added a stable capability catalog, runtime schemas, read-only query dispatch, an extension edit envelope and a reload command. Existing typed operations remain compatible; future extension features do not change MCP tool schemas.
- Added generation-isolated source loading with relative helper snapshots, content fingerprints, atomic publication, stale-catalog guards and failed-load recovery. Configured extension roots are trusted startup configuration; tools accept no code or module paths.
- Moved the native dock and drag controller behind stable facades into a reloadable CAD panel extension. Reload preserves panel settings, pauses playback, removes old callbacks and restores the previous generation if UI rebuilding fails. Actual GUI verification requires separate manual validation.
- Added installed tube creation and mass-property capabilities, native query rollback guards and rejection of generation-owned model/view proxies. A persistent stdio MCP test confirms new-feature discovery, identical tool schemas, unchanged native worker PID, failed-update recovery and preserved native models/Undo.
- Setup generates ReloadExtensions.FCMacro and supports explicit external extension directories for live and headless sessions. Portable native packages now include extension manifests and implementations.
- Native startup reports invalid extension configuration immediately, and repaired initial startup can retry through the same host client. Response queues are isolated per native worker so a retired reader cannot contaminate recovery. All 213 tests, lint/format checks, isolated wheel and portable-runtime native reload checks pass.

## 0.7.0 (GUI acceptance pending) — 2026-10-16

- Added the native Codex CAD dock with source-parameter inspection/editing, coupling controls, joint playback, viewport drag mode, overlap-pair highlighting and sampled-pose navigation. Setup generates a local panel macro and optional workbench folder.
- Added headless native checks of drag projection, forward/inverse coupled movement, half-turn crossing, cancellation, Undo and transaction isolation. Empty transaction cleanup handles clicks without movement and failures before the first change.
- Updated typed MCP/API discovery for 20 tools and 43 operations. Panel UI and physical mouse interaction require manual validation; no desktop interaction is used for the new automated controller checks.
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
- Added a parameter-driven loft/mirror example for both backends, expanded MCP/native/live validation, with dependency, rollback and persistence checks.

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
