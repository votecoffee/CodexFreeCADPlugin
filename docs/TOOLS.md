# Tool and modeling reference

Commands below run from the repository root. See [installation and quick start](../README.md) first.

## MCP tools


| Tools | Behavior |
|---|---|
| `list_capabilities`, `describe_capability` | Installed feature catalog, versions and current argument schemas |
| `run_query`, `reload_extensions` | Guarded extension reads and reloads within the existing connection |
| `freecad_status`, `list_documents` | Backend, workspace, version and session discovery |
| `new_document`, `open_document` | Unsaved new models or existing trusted FCStd files |
| `inspect_document`, `inspect_object` | Feature tree, parameters, dependencies, revision, bounds, area and volume |
| `inspect_sketch` | Local geometry, named dimensions, zero-based indices, datum units and constraint state |
| `inspect_assembly` | Linked components, grounding, connector frames, joint positions and travel limits |
| `check_interference` | BREP overlap volume, contact and insufficient clearance for selected solids |
| `sample_motion` | Discrete driven-joint checks on a hidden copy, honoring saved ratios without moving the source |
| `inspect_topology` | Paginated EdgeN/FaceN/VertexN measurements, positions, curve/surface types and radii |
| `measure_distance` | Minimum distance between objects or selected subelements, with nearest points |
| `import_model` | Source-preserving STEP/STP, BREP and STL import into an existing document |
| `apply_operations` | One atomic batch with rollback on failure and one Undo entry |
| `undo_document` | Undo the last FreeCAD transaction |
| `save_document` | Save FCStd; opt-in overwrite with a preserved backup |
| `export_model` | Export named objects to STEP, STL or BREP |
| `get_selection`, `capture_view` | Live selected objects/faces/edges and native viewport PNGs |
| `set_view` | Seven standard live viewport orientations and optional fit-to-view |

The 25 MCP tools expose 44 structured operation kinds (including the stable extension envelope): `create_box`, `create_cylinder`, `create_sphere`, `create_body`, `create_sketch`, `add_sketch_geometry`, `add_constraint`, `set_datum`, `pad`, `pocket`, `revolve`, `linear_pattern`, `circular_pattern`, `set_linear_pattern`, `set_circular_pattern`, `boolean`, `set_property`, `set_placement`, `delete_object`, `import_model`, `mesh_to_solid`, `fillet`, `chamfer`, `set_edge_treatment`, `create_parameters`, `set_expression`, `clear_expression`, `loft`, `set_loft`, `mirror`, `set_mirror`, `sweep`, `set_sweep`, `create_helix`, `create_assembly`, `add_component`, `ground_component`, `create_joint`, `set_joint_limits`, `set_joint_positions`, `solve_assembly`, `set_joint_coupling`, `clear_joint_coupling` and `extension`.

Sketches support lines, circles, three-point arcs and rectangles in local XY, with placement/rotation for other planes. Pads and pockets require a sketch in the specified PartDesign body. Dimensional constraints use FreeCAD's `Sketcher.Constraint` positional argument conventions. Numeric lengths are **millimeters**, placements are absolute, and rotation angles are **degrees**. Raw sketch `Angle` constraint arguments and native arc parameters use **radians**; `set_datum` accepts explicit unit strings such as `30 deg`.

Use internal object names returned by inspection, which can differ from visible labels. A parameter driven by an expression cannot be overwritten directly; edit its driving parameter or explicitly clear the expression first. Deleting an object with dependents is rejected. Every batch recomputes and checks resulting feature/shape validity. A `capture_view` call returns an MCP image and saves a PNG in the workspace.

### Holes and fasteners

Discover `holes.drill`, `holes.bolt_circle`, `holes.refresh`, `fasteners.bolt`, `fasteners.nut` and `fasteners.washer` with the capability tools, then invoke them through the existing `extension` operation. A separate `<name>Parameters` object drives native dimensions, with no extension-owned model proxies. Through extents can be refreshed after base edits; layout/recess entry points remain fixed in world coordinates. See [arguments, examples and editing behavior](HOLES_FASTENERS.md).

> Reload the FreeCAD extensions. Drill six 6.5 mm through-holes on a 28 mm radius bolt circle in my flange, with 11 mm counterbores 6 mm deep. Use the inspected top surface as the entry plane. Add dimensioned socket-cap bolts, then check for overlap and save a new copy.

Run `.venv\Scripts\python.exe scripts\smoke_hardware.py --workspace work\my-hardware-demo` to build and verify a 23-solid flange/fastener and hole-coupon sample headlessly in a new folder. It saves editable FCStd and STEP files. No GUI or desktop input is used by that script. Fasteners are unthreaded and do not automatically mate to holes or claim standard sizes, tolerances or load ratings.

Not yet implemented: sketch splines/ellipses, closed-loop joint driving, nested assemblies, assembly contact/dynamics, sheet metal and arbitrary Python execution. [Engineering extensions](ENGINEERING.md) add BOMs, parameter studies and limited TechDraw/SVG sheets. Existing FCStd features can be inspected, and supported scalar parameters can be edited even when this version cannot create that feature type. This is a growing modeling toolset, not complete FreeCAD workbench coverage.

### Movable assemblies

`create_assembly` creates one native `Assembly::AssemblyObject` and its joint group. `add_component` creates a same-document `App::Link` to a top-level solid/Body, samples its initial placement and hides the source. Native source dimension edits propagate to every linked instance. `ground_component` fixes a component at its current placement. The first version supports one root assembly with identity placement, up to 200 components and 400 joints.

`create_joint` accepts `fixed`, `revolute` or `slider`, two component names and optional `frame_a` / `frame_b`. Each frame has a local `position` (three mm coordinates), rotation `axis` and `angle` (degrees). Frames default to the component origin. Revolute motion rotates about frame +Z; slider motion translates along frame +Z. Joint zero aligns the two frames. Explicit local connectors remain meaningful when face numbering changes, but their positions do not automatically follow a changed hole or feature dimension.

`set_joint_positions` accepts up to 100 distinct `{joint, position}` entries and solves a coordinated absolute pose. Revolute positions are degrees, sliders are mm. Positioning requires directed joint trees: component A is the parent, component B the child, and every tree starts at a grounded component. Unspecified coordinates retain their current values; fixed children follow their parent. The engine seeds the pose, temporarily closes driven DOFs using native fixed joints, runs the native solver and checks connector/ground residuals before restoring the movable joint types. It rejects closed loops and multiple incoming joints when positioning. No extra drive constraints or integration Python proxies remain in the saved model.

`set_joint_limits` replaces both limits for a revolute/slider joint; omitted or null bounds clear that side. Revolute limits lie within -180 to 180 degrees; slider limits are mm. `inspect_assembly` returns actual connector positions, unwrapped commanded coordinates, grounding, connectivity, couplings and limits. The geometric `position` wraps to -180..180; `coordinate` retains turns (450 degrees has the geometric pose of 90 degrees). Pose solving checks joint geometry and limits. Run the separate interference tools to check BREP overlap or clearance; loads and dynamics are outside scope.

Example pose operation:

```json
{"op":"set_joint_positions","assembly":"ArmAssembly","positions":[{"joint":"Shoulder","position":60},{"joint":"Extension","position":12}]}
```

`examples/movable_arm.py` builds a rotary arm and an oblique sliding tool using either backend. To build the jointed gearbox from the earlier corrected static showcase:

```powershell
.venv\Scripts\python.exe scripts\build_movable_demo.py --source models\Demos\PlanetaryGearbox.FCStd --workspace models\MovablePlanetary
```

The builder creates `PlanetaryGearbox-Movable.FCStd`, 60 native animation frames, a STEP pose snapshot, verification reports and `PlayPlanetary.FCMacro`. The macro and adjacent `native` folder provide Play/Pause, Reset and an input-angle slider without host MCP dependencies. Keep them beside the model and execute the macro in FreeCAD. The gearbox has 15 linked components, 14 native joints and 26 solid instances. Its analytical driver uses a fixed ring, carrier speed = sun/4 and absolute planet spin = -sun/2. Gear ratios are coordinated by the demo controller; the file does not contain native gear-ratio constraints. Native joint motion remains editable from either chat backend.

### Saved couplings, native panel and interference

`set_joint_coupling` saves `follower = ratio * driver + offset` for two revolute/slider joints in the same assembly. A negative ratio reverses direction; mixed joint types allow mm/degree mechanisms. Nonzero ratios from 1e-9 through 1e6 in magnitude and offsets up to 1e6 are supported. Chains are resolved in dependency order; driving a follower solves the chain backwards. Duplicate followers are replaced, cycles are rejected, conflicting simultaneous positions fail atomically, and every resolved coordinate respects its joint limits. `clear_joint_coupling` removes the follower's rule and retains the current pose. The data persists through FCStd save/reopen without an integration feature proxy. The native Assembly workbench's own dragging does not enforce this metadata; the panel and both chat backends use the shared coupling engine.

```json
{"op":"set_joint_coupling","assembly":"ArmAssembly","joint":"Extension","driver":"Shoulder","ratio":0.15,"offset":2}
```

The **Codex CAD** dock opens with `StartBridge.FCMacro`. Run the generated `OpenFreeCADPanel.FCMacro` for local tools without a chat connection, or copy the generated `FreeCADMod/CodexFreeCAD` folder into your FreeCAD user Mod folder for an optional workbench entry. Generated paths belong to this installation; regenerate after moving it. Model provides protected parameter editing and a shortcut to a linked source. Motion provides numeric poses, playback, coupling controls and an explicit **Drag parts in viewport** mode. Release commits a drag as one Undo entry; Escape cancels it. Camera singularities and grounded parts produce explanatory status messages. The toolbar reopens a closed dock. An active native edit blocks chat edits, Undo, save/export and motion sampling until it finishes.

`check_interference` takes 2–50 distinct valid solid object names, optional `clearance` in mm and `volume_tolerance` in mm³. It returns positive-volume overlap separately from contact and insufficient clearance. Bounding-box distance rejects clearly separated pairs. Inputs must be top-level solids or links in supported identity-placement root assemblies. `sample_motion` drives one revolute/slider joint over 2–101 positions, applies all stored couplings, and reports flagged pairs plus every resolved joint coordinate. It uses a hidden native copy and leaves source pose, revision and Undo untouched. Sampling is capped at 5,000 pair-pose checks. Discrete samples do not establish continuous collision-free travel.

To create the upgraded portable demo from the v0.6 jointed model, using **FreeCADCmd only**:

```powershell
.venv\Scripts\python.exe scripts\build_coupled_demo.py --source models\Demos\PlanetaryGearbox-Movable.FCStd --workspace models\CoupledPlanetary
```

Choose a fresh output folder. `OpenCoupledGearbox.FCMacro` opens the copied model, the Motion tab and drag mode; `PlanetaryGearbox-Coupled.FCStd` saves the four ratios themselves. The original model is preserved. [Panel instructions and manual checks](PANEL_TESTING.md) explain numeric checks, picking and the isolated test command. See [validation scope](VALIDATION.md) for the distinction between headless controller checks and manual GUI verification.

### Sweeps, pipe paths and helices

`sweep` creates a native `Part::Sweep` from 1–50 distinct `profiles` in section order and a `path`. Profiles must be top-level objects containing exactly one wire and no solid. Position/rotate them relative to the path first; the operation does not choose or align their planes. `solid=true` (default) requires closed profiles and exactly one positive-volume resulting solid; `solid=false` supports surfaces from open or closed sections.

The top-level path must contain exactly one wire, or supply `path_edges` with up to 500 distinct current EdgeN names. Selected edges must form one connected valid wire; explicit selection also permits a path from a top-level solid's edges. Empty `path_edges` uses the complete single-wire path. Native profile/path links remain parametric. Reinspect topology after upstream edits and pass `expected_revision` to guard selections.

`frenet=false` is the default framing; `frenet=true` uses the native Frenet option, useful for helices. `transition` is `transformed` (default), `right_corner` or `round_corner`. Native kernel failures and invalid results roll back the entire batch. `set_sweep` requires the replacement `profiles` and `path`, replaces `path_edges` (default empty), and preserves omitted solid/framing/transition controls. This supports profile/path replacement as well as option changes. Multi-wire sections and nested body/part inputs are outside the supported sweep scope.

`create_helix` creates a native `Part::Helix` along local +Z with positive `pitch`, axial `height` and starting `radius` in mm. `angle=0` is cylindrical; nonzero angles strictly between -90 and 90 degrees taper the radius. Creation rejects nonpositive conical top radii and more than the native limit of 10,000 turns. Right-handed is default; use `left_handed=true` to reverse it. Native `Pitch`, `Height`, `Radius` and `Angle` can subsequently be edited or driven by expressions. Placement positions the entire path. The native computed `Length` is available in property inspection.

For a cylindrical helix beginning at `(R,0,0)`, a circular section centered there can be made normal to its initial tangent by rotating its XY sketch about X by `-atan2(2*pi*R,pitch)` for a right-handed helix, or the positive angle for a left-handed helix. Convert that rotation to degrees for `set_placement`. The example demonstrates this and a hollow elbow made by subtracting two swept solids. Native helical curves/surfaces are approximated; the example checks analytic wire volume within 1e-5 relative tolerance. The generated coil is geometric, without spring-end finishing or spring-performance calculations.

> Create a hollow quarter-circle elbow with a 30 mm centerline bend radius, 6 mm outer radius and 4 mm inner radius. Sweep both circular sections along the path, subtract the bore, verify the analytic volume and save FCStd and STEP.

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
