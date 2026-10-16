# FreeCAD Modeling for Codex

A working local MCP integration for editing FreeCAD models from a Codex chat, with equal modeling support for an open FreeCAD window and a background FreeCADCmd session. Project directory: `C:\~LocalWork\Repos\Programming\~Github\CodexFeeCADPlugin`.

Version **0.4.0** adds named design parameters, native arithmetic expressions, solid/surface lofts and parametric mirrors. Earlier sketch, revolution, pattern, import and finishing tools remain available. Native validation used **FreeCAD 1.0.2** and host **Python 3.13** on Windows. The project uses the official MCP Python SDK **2.3.0**, independently of FreeCAD's bundled Python 3.11. No OpenAI key is needed for the Codex MCP integration.

Already using an earlier version? Restart the FreeCAD MCP servers in Codex (or restart Codex), then rerun the regenerated `.local\StartBridge.FCMacro` in FreeCAD. The macro stops the old bridge, reloads the integration modules and reconnects while preserving open native documents. The project environment and generated macros have already been updated on this computer. [Changes in 0.4.0](docs/CHANGELOG.md).

## Start using it

From PowerShell in the project directory:

```powershell
.\scripts\Setup.ps1
.\scripts\Register-Codex.ps1
```

Setup creates the project virtual environment, installs dependencies, and generates machine-specific configuration in `.local`. Registration adds **freecad-live** and **freecad-headless** to your user Codex MCP configuration. Choose this direct registration route OR the local plugin route below to avoid duplicate tools. Setup and native validation have already run on this computer; global Codex registration has deliberately been left for installation.

Start a new Codex chat after registering the servers. The background server starts its own FreeCADCmd when its first modeling tool is called. For live editing, open FreeCAD and run `.local\StartBridge.FCMacro` using **Macro → Macros → Execute**. Keep that FreeCAD window open. Run `.local\StopBridge.FCMacro` to disconnect it. No FreeCAD add-on installation or administrator rights are needed.

The default CAD workspace is the project's `models` directory. Put FCStd input files there, or run setup and registration with the same `-Workspace 'C:\your\CAD folder'` argument. File reads, saves, exports and backups stay inside that workspace. Live tools can inspect and edit an already-open unsaved document; saving it still requires a workspace path.

Try these prompts:

> Use freecad-headless to create an 80 × 50 × 8 mm mounting plate with a 10 mm diameter through-hole centered at X=15, Y=15. Verify the solid and save Plate.FCStd and Plate.step.

> Use freecad-live to inspect my selected object. Change its pad length to 25 mm, verify its volume, and show the updated view. Leave the file unsaved.

> Open Plate.FCStd in the background server, inspect its parameters, change the plate thickness to 12 mm, and save Plate-thicker.FCStd.

### Install as a local Codex plugin

Setup also generates `.local\plugin\.codex-plugin\plugin.json` and `.local\plugin\.mcp.json`. The repository marketplace at `.agents\plugins\marketplace.json` points at this generated package. The supported compatibility manifest bundles both MCP servers. To register the marketplace explicitly and install the package:

```powershell
codex plugin marketplace add 'C:\~LocalWork\Repos\Programming\~Github\CodexFeeCADPlugin'
codex plugin add freecad-modeling@freecad-development
```

This machine's CLI did not discover the project marketplace automatically; explicit marketplace registration is required for that route. The commands above were checked against the installed CLI's help, but not executed. The direct MCP registration script is the shorter installation route.

This is a machine-local development package. Its commands point to this project's virtual environment. Regenerate it after moving the project. Public-directory publishing and a portable installer are separate follow-up work. Native MCP transport was tested; installation through the Codex plugin browser was not tested.

## What this version supports

| Tools | Behavior |
|---|---|
| `freecad_status`, `list_documents` | Backend, workspace, version and session discovery |
| `new_document`, `open_document` | Unsaved new models or existing trusted FCStd files |
| `inspect_document`, `inspect_object` | Feature tree, parameters, dependencies, revision, bounds, area and volume |
| `inspect_sketch` | Local geometry, named dimensions, zero-based indices, datum units and constraint state |
| `inspect_topology` | Paginated EdgeN/FaceN/VertexN measurements, positions, curve/surface types and radii |
| `measure_distance` | Minimum distance between objects or selected subelements, with nearest points |
| `import_model` | Source-preserving STEP/STP, BREP and STL import into an existing document |
| `apply_operations` | One atomic batch with rollback on failure and one Undo entry |
| `undo_document` | Undo the last FreeCAD transaction |
| `save_document` | Save FCStd; opt-in overwrite with a preserved backup |
| `export_model` | Export named objects to STEP, STL or BREP |
| `get_selection`, `capture_view` | Live selected objects/faces/edges and native viewport PNGs |
| `set_view` | Seven standard live viewport orientations and optional fit-to-view |

The 17 MCP tools expose 31 edit operations: `create_box`, `create_cylinder`, `create_sphere`, `create_body`, `create_sketch`, `add_sketch_geometry`, `add_constraint`, `set_datum`, `pad`, `pocket`, `revolve`, `linear_pattern`, `circular_pattern`, `set_linear_pattern`, `set_circular_pattern`, `boolean`, `set_property`, `set_placement`, `delete_object`, `import_model`, `mesh_to_solid`, `fillet`, `chamfer`, `set_edge_treatment`, `create_parameters`, `set_expression`, `clear_expression`, `loft`, `set_loft`, `mirror` and `set_mirror`.

Sketches support lines, circles, three-point arcs and rectangles in local XY, with placement/rotation for other planes. Pads and pockets require a sketch in the specified PartDesign body. Dimensional constraints use FreeCAD's `Sketcher.Constraint` positional argument conventions. Numeric lengths are **millimeters**, placements are absolute, and rotation angles are **degrees**. Raw sketch `Angle` constraint arguments and native arc parameters use **radians**; `set_datum` accepts explicit unit strings such as `30 deg`.

Use internal object names returned by inspection, which can differ from visible labels. A parameter driven by an expression cannot be overwritten directly; edit its driving parameter or explicitly clear the expression first. Deleting an object with dependents is rejected. Every batch recomputes and checks resulting feature/shape validity. A `capture_view` call returns an MCP image and saves a PNG in the workspace.

Not yet implemented: sketch splines/ellipses, assemblies, sheet metal, TechDraw and arbitrary Python execution. Existing FCStd features can be inspected, and supported scalar parameters can be edited even when this version cannot create that feature type. This is a growing modeling toolset, not complete FreeCAD workbench coverage.

### Parameters, expressions, lofts and mirrors

`create_parameters` adds a native property container with up to 100 uniquely named `length`, `angle`, `number` or `integer` parameters. Length/angle values accept numbers in mm/degrees or unit-bearing strings; lengths cannot be negative. The container is `App::FeaturePython` with its Proxy left unset, so no custom feature code executes. Use `set_property` to edit these parameters after creation.

`set_expression` drives a numeric property, a placement translation (`Placement.Base.x/y/z`) or a driving dimensional sketch constraint (`Constraints[8]` or `Constraints.Rect0_width`). For example, assign `Design.Thickness * 2` to a pad's `Length`, or `Design.Height` to an upper loft profile's `Placement.Base.z`. Inspection returns explicit `expressions` bindings and native dependencies. FreeCAD may report named constraint paths with a leading dot; use the documented target forms when editing. `clear_expression` removes the binding and retains its last evaluated value.

The supported formula language is arithmetic (`+ - * / ^`), parentheses, finite numeric literals, `pi`, the units `mm/cm/m/in/ft/deg/rad`, and same-document numeric references using internal object names. Local numeric references such as `Length / 2` and named sketch references such as `Profile.Constraints.Rect0_width` are supported. Functions, strings, label-based/external-document references, arbitrary attributes and Python execution are excluded. FreeCAD performs dimensional analysis and native dependency/cycle checks; failed expressions roll back the complete edit batch. Managed pattern controls remain protected from expression assignment. A placement with an existing expression must have that expression edited or cleared before `set_placement` can replace the placement.

`loft` creates a native `Part::Loft` through 2–50 distinct `profiles` in section order. Each must be a top-level object containing exactly one wire and no solid. `solid=true` (default) additionally requires closed wires and one positive-volume resulting solid. `solid=false` allows open-wire surfaces; `ruled=true` uses ruled spans. Use `set_loft` to replace/reorder profiles and optionally change those controls. Nested body/part profiles, point sections, multi-wire profiles and closed-loop lofts are outside this operation's supported scope. Profile dimensions and placements remain native dependencies.

`mirror` creates a native `Part::Mirroring` from a top-level `source` and document-space plane `point`/nonzero `normal` (defaults: origin, X normal). The result contains reflected geometry only; it hides the source, which can be shown explicitly if wanted. A top-level Body or native array is supported; nested body features should be mirrored through their Body. `set_mirror` replaces the plane, with the same defaults. The result follows source dimensions and placement. Loft/mirror updates are undoable and preserve native dependencies through FCStd save/reopen.

> Create a design parameter container with BaseRadius=20 mm, TopRadius=10 mm and Height=45 mm. Drive two circular profiles from those radii, loft between Z=0 and Height, mirror the result across X=40 mm, and save both solids. Then change Height to 60 mm and verify both volumes.

### Sketches, turned parts and patterns

The rectangle geometry item takes `origin`, positive `width` and `height`, and defaults to `constrained=true`. It creates four lines with closure, horizontal/vertical constraints and named width, height and origin dimensions. Creation results report the geometry indices and dimensional constraint indices. `inspect_sketch` reads these, their names and unit-bearing datum strings. Use `set_datum` with those zero-based constraint indices to change dimensions. Set `constrained=false` when you want an unconstrained rectangle, or `construction=true` for reference geometry. `add_sketch_geometry` appends items without renumbering existing geometry. Arcs take local `start`, `mid` and `end` points; collinear or otherwise invalid arcs roll back the edit batch. Three-dimensional sketch coordinates are rejected rather than silently projected.

`revolve` creates a native `Part::Revolution` with a source profile, document-space `center` and `axis`, nonzero `angle` within +/-360 degrees, and `solid=true` by default. A solid needs a suitable closed profile and axis; use `solid=false` for surfaces. For a washer about Z, create a radial/height rectangle in XY, rotate its sketch 90 degrees about X into XZ, then revolve about Z. Profile dimensions and the revolution's scalar `Angle` remain editable and recompute through native dependencies.

`linear_pattern` and `circular_pattern` create native compact `App::Link` arrays. Counts are integers from 2 through 200 and include the original instance. A linear `step` is a translation per instance in document mm. Circular `center` and `axis` are document coordinates; a full +/-360-degree span excludes the repeated endpoint, while partial spans include both endpoints. Sources must be top-level solids or a top-level PartDesign Body; target the Body instead of a nested Pad or other body feature.

Pattern source dimensions remain linked. **Source placement is sampled on creation/update**; the matching `set_linear_pattern` or `set_circular_pattern` operation recalculates placements from the current source and parameters. The pattern object's own Placement adds a rigid transform and is preserved across those updates. Pattern controls are read-only in the GUI and protected from generic `set_property`; use the dedicated operations. Copies remain separate solids, with no automatic fusion or collision test. Reported compound volume includes all instances, including any overlaps.

Sketches, revolutions and patterns use native FreeCAD objects and constraints, with no custom Python feature proxies. Their geometry/dependencies persist after FCStd save/reopen. BREP export explicitly evaluates link-array shapes so every instance is written. Empty geometry imports/exports are rejected. Bounds use native geometry without display triangulation; link-array revision hashing similarly excludes display meshes and internal caches.

### Import and finish existing geometry

`import_model(document, path, name)` imports STEP/STP or BREP into one native Part feature. Multiple solids may form one compound. It preserves geometry without reconstructing source feature history, assembly structure, colors or other metadata. Source files remain unchanged; hashes are checked before and after native parsing and included in the result. STEP follows native unit conversion. STL and BREP coordinates are interpreted in millimeters.

STL initially becomes a native mesh. `inspect_object` reports its facet/point counts, closedness, area, bounds and volume when closed. `mesh_to_solid` explicitly converts a closed mesh with at most 20,000 facets and exactly one resulting closed shell; the default sewing tolerance is 0.01 mm. Open meshes are rejected. The result is a static BREP snapshot of the triangulated mesh, with its current placement preserved; it does not recover original smooth CAD surfaces or follow later mesh edits. Mesh revisions hash vertex coordinates and connectivity to detect changes.

Inspect the base object's current edges using `inspect_topology` before creating a `fillet` or `chamfer`. Supply their EdgeN names and a positive `size` in mm: radius for fillets, equal distances for chamfers. These are native parametric Part features linked to their base, including after FCStd save/reopen. `set_edge_treatment` changes an existing Part fillet/chamfer's selected **base** edges and size. Invalid radii, invalid selections and kernel failures roll back the batch. Upstream objects are hidden in both backends so background-saved models open with their final feature visible.

EdgeN/FaceN/VertexN names describe the inspected shape. Reinspect after geometry changes and pass `expected_revision` into edits; these labels are not persistent model-wide identifiers. Topology pages are limited to 500 entries. Zero-length edges without a native curve are reported as degenerate instead of aborting inspection. Distance queries measure a minimum separation and return nearest points; they are not collision, wall-thickness or assembly-clearance tests.

Example prompts:

> Import housing.step into my document as Housing. Inspect its edges, add a 1 mm fillet to the four outer vertical corner edges, verify the result and save Housing-rounded.FCStd.

> Inspect the selected face and measure its minimum distance to the top face of Spacer. Then show the top view.

> Import scan.stl as Scan. Report whether it is closed, and if it qualifies, convert it into a solid and save a separate FCStd copy.

## Session and file behavior

Live and background servers own **separate documents and undo histories**. They do not synchronize open documents through memory. Save an FCStd file explicitly to exchange a model between sessions. A background worker persists across calls within its MCP server session; unsaved changes disappear when that server closes. Avoid editing the same file concurrently in both sessions.

Inspect before editing and pass the returned `revision` as `expected_revision`. A changed feature parameter or shape makes the stale edit fail before mutation. Revisions are session-local change-detection tokens, not file hashes or persistent CAD identifiers. Edits without `expected_revision` are allowed.

Overwriting an existing file requires `overwrite=true`. Before writing, the original bytes are copied to `models\backups` with a unique name. Save/export results include a SHA-256 digest, byte count and backup path. Saving is not a filesystem-wide transaction: if native disk writing fails, inspect the backup and output file. Geometry transactions only cover a single `apply_operations` call; saving/exporting are separate actions.

The live bridge binds only to `127.0.0.1` on a random port, authenticates each call with a generated bearer token, rejects browser origins, checks Host, bounds request size and queues work onto the GUI thread. It exposes a fixed method/operation set and no Python evaluation endpoint. The token is in the ignored workspace state file; Windows file access follows that folder's ACLs. FCStd loading uses native FreeCAD; use trusted models and installed add-ons. This integration is not a sandbox for untrusted CAD files or local users.

A queued live request that expires before execution is cancelled. An already-running operation can outlive an HTTP timeout. Background timeouts terminate and disable that worker session. Inspect the model or saved files before retrying an ambiguous write.

## Run without Codex

```powershell
.\.venv\Scripts\python.exe examples\direct_client.py
```

This creates `models\PlateDemo.FCStd` and `models\PlateDemo.step`. It refuses to overwrite existing output files; use a new `--name` on subsequent runs. Add `--mode live` to run the same example in the connected FreeCAD window.

`python examples\finish_plate.py --workspace models --name FinishedDemo` demonstrates topology-selected corner fillets, a chamfered hole, FCStd/STEP output and STEP reimport. Use the project's `.venv\Scripts\python.exe`; add `--mode live` to use the open FreeCAD window.

`python examples\turned_flange.py --workspace models --name TurnedDemo` creates a constrained profile, revolved flange, six patterned bolt holes and a three-instance row, with native volume checks and FCStd/STEP output. It also supports `--mode live`.

`python examples\parametric_transition.py --workspace models --name ParametricDemo` creates two fully constrained circular profiles driven by named parameters, a native loft and its mirror. It verifies the two-solid analytic volume, saves FCStd/STEP and supports `--mode live`. Its disconnected boolean union keeps both solids in one final feature without joining material across the gap.

`codex_freecad.client.HeadlessClient` and `LiveClient` are also application APIs for your own code. See `examples\direct_client.py` and `examples\mounting_plate.json`.

### Optional OpenAI Responses API example

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api]'
# Set OPENAI_API_KEY in this process using your normal local secret-management workflow.
.\.venv\Scripts\python.exe examples\api_agent.py --model YOUR_MODEL --prompt 'Create a 40 mm cube and save Cube.FCStd'
```

The app-managed tool loop passes schemas obtained from the same MCP server to the Responses API and routes model requests back through the same validation. It includes the 16 text-result tools; viewport images are available through MCP directly. It uses the model you name, makes paid API calls when run, and has a bounded tool loop. API schema/result conversion has a local test; **no paid OpenAI API run has been performed**.

## Verify the project

```powershell
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check src tests examples scripts
.\.venv\Scripts\ruff.exe format --check src tests examples scripts
.\.venv\Scripts\python.exe scripts\smoke_live.py
```

The live smoke test starts and closes its own isolated GUI instance, creates only test models, and writes results under `work\live-smoke`. It does not attach to an existing FreeCAD process. Unit-only checks can use `pytest -m 'not native'`. Native tests skip if FreeCADCmd cannot be found. `FREECAD_CMD` or `--freecad-cmd` can select another installation; setup accepts `-FreeCADCmd`.

See `docs\VALIDATION.md` for observed results and `docs\ARCHITECTURE.md` for implementation boundaries. `requirements-windows-py313.lock` records the validated development environment.

## References

The local MCP registration follows [OpenAI's MCP configuration guidance](https://learn.chatgpt.com/docs/extend/mcp?surface=cli). The generated plugin uses the supported compatibility manifest described in [Package your plugin](https://developers.openai.com/plugins/build/plugins). The optional API example follows [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling). Native modeling is implemented through FreeCAD's Python objects and the installed 1.0.2 engine; see [FreeCAD source](https://github.com/FreeCAD/FreeCAD/tree/1.0.2) and the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
