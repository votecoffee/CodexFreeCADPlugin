# Validation

This document describes reproducible checks and their limits. Per-run logs, workstation details and reports belong in ignored `work/` or `local/`, not in public source documentation. Record observed results against the exact commit being checked.

## Reference environment

The reference native runtime is **FreeCAD 1.0.2** with its bundled Python 3.11. Host tooling uses **Python 3.13 on Windows** and MCP Python SDK **2.3.0**. The package declares Python 3.11 or later; other host/runtime/platform combinations require their own validation. `requirements-windows-py313.lock` records a development environment snapshot.

Host dependencies must not be imported into FreeCAD's bundled interpreter. Native code uses installed FreeCAD modules and the standard library. Configure `FREECAD_CMD` or a script's `--freecad-cmd` option when auto-discovery does not find the intended installation.

## Automated checks

From the repository root after setup:

```powershell
New-Item -ItemType Directory -Force work\validation | Out-Null
.\.venv\Scripts\pytest.exe -q --junitxml=work\validation\tests.xml
.\.venv\Scripts\ruff.exe check src tests examples scripts
.\.venv\Scripts\ruff.exe format --check src tests examples scripts
.\.venv\Scripts\python.exe -m pip check
```

For host-only checks, use `.venv\Scripts\pytest.exe -q -m 'not native'`. Native tests skip if FreeCADCmd is unavailable; a host-only pass is not native geometry validation. Check the summary for failures, errors and skipped cases.

Coverage includes:

- Workspace confinement, explicit overwrites/backups, typed schemas, revision guards, setup generation and API schema conversion.
- Native primitives, sketches, constraints, pads/pockets, revolutions, patterns, sweeps, helices, lofts, mirrors, expressions, imports, mesh conversion and edge finishing.
- Recompute, feature validity, analytic geometry, transaction rollback, Undo, native save/reopen and export roundtrips.
- Assemblies, connector frames, grounding, joint limits, coordinated poses, saved couplings, overlap/contact/clearance and discrete motion sampling without source mutation.
- Headless drag-controller math, wrap crossings, inverse coupled movement, cancellation, one-gesture Undo and active-edit isolation.
- Extension schema guards, helper snapshots, generation publication/rollback, stale catalogs and persistent MCP reloads with unchanged tool schemas, native worker PID, model revision and Undo history.
- Holes, counterbores, countersinks, bolt circles, refreshed through extents and dimensioned bolts/nuts/washers, including failed-cut rollback and editing after reopen.
- BOM source identity, link-array quantities, explicit density, formula-safe CSV/spreadsheet cells, snapshot refresh and native persistence.
- Parameter-study expression propagation on hidden copies, failure cleanup, source revision/Undo preservation and frozen configuration snapshots.
- Numeric multi-property previews, equal-volume reshaping, disjoint translation, curved material differences, stale-apply rejection and matching native apply/Undo/save/reopen results.
- Saved design requirements for numeric properties, known-density mass, volume, axis extents and BREP clearance/overlap, including contact, numerical tolerance, source revision preservation, failing-batch rollback, explicit updates and native save/reopen. Previews include before/after rule reports and enforcement in returned apply arguments.
- Native TechDraw extent values against projected BREP bounds, curved/translated/link-array sources, refresh/stale-source guards, SVG XML and native save/reopen. A persistent MCP regression loads the engineering packages into the original connection and tests drawing, preview-helper and requirement-helper updates plus failed-update recovery.

Tests using UI lifecycle doubles check controller contracts. They do not establish Qt behavior, Coin event delivery or physical mouse picking.

## App-owned framework host

The experimental app-owned framework pins framework 0.15.0 and MCP 2.3 throughout. It does not require the Universal Tools plugin or a universal daemon. After installing the verified framework wheel and host package, include its disposable-provider protocol profiles:

```powershell
$env:FREECAD_FRAMEWORK_PYTHON = 'C:\Apps\FreeCADHost\python.exe'
.\.venv\Scripts\pytest.exe -q -m 'not native'
```

The framework cases start only isolated app hosts and published SDK 2 workers with fixture providers below the original MCP handlers. The matrix covers legacy backends/frontends, auto-negotiated modern backends with modern frontends, and required-modern backends with legacy frontends. Each case checks the actual backend protocol, complete selected results/media, separate frontend ownership, model revision/Undo across deferred publication, same-session frontend schema stability, failed-candidate recovery, one recorded effect after a lost reply and a durable no-replay barrier across host restart. Direct and hosted references use the same backend protocol, retaining SDK metadata such as modern `serverInfo` rather than stripping it for comparison. Each records five warm direct/host inspection samples locally. Those samples do not establish native latency criteria, large-payload performance or Codex UI acceptance. See [framework package and lifecycle boundaries](FRAMEWORK.md). Without the environment variable these profiles skip; no current installed route is changed.

The host suite checks standalone installation previews, preservation of existing direct configuration, rejection of removed installer/server options, exclusive app-owned backend definitions, exact write allowlists, unchanged direct MCP schemas and installation metadata discovery without executing extension code. Normal setup generates no broker manifests. Live GUI editing and Codex UI activation remain separate manual checks.

## Headless smoke checks

Each command needs a fresh output folder and uses FreeCADCmd without desktop interaction:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_hardware.py --workspace work\hardware-check
.\.venv\Scripts\python.exe scripts\smoke_extensions.py --workspace work\extension-check
```

The hardware sample contains 23 selected solid instances: a flange, six socket bolts with washers/nuts, and a hole coupon with hex hardware. Its report checks native shape validity, independent analytic volume, 253 static BREP part pairs, FCStd reopen, Undo and STEP persistence. Read the generated report for actual outcomes and tolerances.

The extension smoke check exercises capability discovery, reload and persisted geometry. The persistent-connection regressions in `tests/` provide additional checks for stable transport schemas and failed-update recovery.

`examples/engineering_plate.py --workspace work/engineering-demo` combines holes, linked instances, BOMs, thickness studies, numeric change previews, frozen variants and dimensioned native/SVG sheets. Run with the project's Python; it verifies analytic volumes and added/removed material, then writes local hash evidence. Use a fresh output name for repeat runs. SVG rendering can be inspected independently of the native FreeCAD GUI; native GUI page layout and physical printing still need manual checks.

`examples/design_requirements.py --workspace work/requirements-demo` creates a shaft/sleeve fit example with saved limits. It verifies an oversized proposal is rejected without source mutation, applies a passing proposal, checks radial clearance and mass against analytic formulas, and saves FCStd/STEP plus local hash/rule evidence.

## Manual GUI checks

These commands explicitly open isolated FreeCAD GUI processes and must be run when GUI testing is intended:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_live.py
.\.venv\Scripts\python.exe scripts\smoke_panel.py --interactive
```

The live smoke test creates its own configuration and documents under `work/live-smoke`. The panel harness tests native controls and dock reload, then holds an arm/slider model for manual dragging. See [PANEL_TESTING.md](PANEL_TESTING.md) for expected coordinates, cancellation and Undo behavior.

Native panel reload and physical viewport dragging require manual verification on the target installation. Headless controller results do not substitute for those checks. Record GUI and physical gesture results separately. Do not attach automation to an existing production FreeCAD session for testing.

## Release packaging

Build a wheel and package only from a clean committed tree. Supply a completed JUnit report and either a matching headless report or live report:

```powershell
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
.\.venv\Scripts\python.exe scripts\package_release.py --output dist\release --headless-report work\hardware-check\result.json --tests work\validation\tests.xml
```

Use the actual report path printed by the smoke runner. For live evidence, replace `--headless-report` with `--live-report` and the matching report. The packager verifies sample hashes, package version, passing test counts, source archive hashes, and exact wheel/source Python and JSON contents. It labels headless and GUI evidence separately and writes an artifact manifest with the source commit and hashes.

Keep raw packaging outputs ignored until reviewed. Native JSON, JUnit XML, screenshots and CAD metadata may include local paths or private information; inspect them before publishing release assets. Source ignore rules do not sanitize reports. Preserve the original local evidence when preparing a public copy.

## Interpretation limits

- Revision tokens are conservative, session-local change detectors. Reinspect after edits or Undo; they are not persistent CAD identifiers or file hashes.
- Topology names such as `EdgeN` describe the current inspected shape and can change after upstream edits.
- Discrete interference samples do not establish continuous collision-free motion, contact dynamics, gear strength or load capacity.
- Fasteners are simplified unthreaded geometry. Explicit dimensions do not certify standard sizes, tolerances, torque or fits.
- Native saved geometry is checked separately from GUI appearance, physical dragging, plugin-browser installation and paid Responses API execution.
- Trusted native FCStd loading can use installed FreeCAD workbenches/add-ons. The integration is not an untrusted-file sandbox.
