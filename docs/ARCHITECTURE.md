# Architecture

The normal Windows connection uses the [stable standalone launcher](STABLE_LAUNCHER.md):
app-owned entry/cwd, retained wheel closure, atomic selection and the same surviving
windowless supervisor. Source checkout endpoints and the optional framework host
remain separate development/experimental workflows.

FreeCAD owns its standalone MCP server, Codex plugin and native skills. The shared library comes
from [CodexMCPBroker](https://github.com/votecoffee/CodexMCPBroker), which also provides a separate
Windows management app. No universal plugin, broker hop or central CAD session is required. The
experimental app-owned host has its own [publication and acceptance boundary](FRAMEWORK.md).

The standalone native entry uses a real windowless interpreter, an immutable runtime closure and
one shared state/registry. Sixteen memory-budgeted metadata frontends may initialize without a native worker. A lazy
single-worker lease precedes native dispatch and remains held until successful backend cleanup;
failed cleanup preserves the lease/uncertainty. The host maps only its known pre-dispatch native
capacity error to MCP 2.3 `ToolError`, retaining SDK redaction for other exceptions. Native worker
bootstrap files and bytecode stay in private generation directories. See [native recovery](NATIVE.md).

Generated TOML uses `toml_io.encode_toml` and byte writes. It validates TOML, rejects malformed CR,
normalizes valid LF/CRLF once and emits explicit CRLF on Windows. Text-mode newline translation
must not be applied to already-CRLF text. Codex integration reads configuration bytes for strict
preflight and delegates normal registration to the Codex CLI; it does not hand-edit user TOML.

`assemblies.py` creates native Assembly containers and single component links. Joint and grounding proxies come from the installed FreeCAD `JointObject` module. Explicit detached local connector frames avoid transient topology indices. Position commands require directed trees rooted at grounded components, seed a coordinated forward pose, temporarily close selected coordinates with native fixed joints, run the solver and verify ground/connector residuals before restoring revolute/slider types. The transaction captures the complete pose; failures roll back. Native solver success is checked against geometry rather than trusted alone. Angular readback wraps at half a turn; limit checks account for the equivalent signed boundary. Inspection traverses references itself so native connectivity helpers cannot delete malformed joints during a read. Integration markers protect joint controls from generic scalar, placement and expression writes. The planetary driver coordinates gear ratios analytically; no general gear-contact or dynamics solver is claimed.

```mermaid
flowchart LR
    Chat[Codex chat] --> MCP[MCP stdio server]
    API[Optional API tool loop] --> MCP
    MCP --> Live[Authenticated loopback bridge]
    MCP --> Worker[FreeCADCmd child process]
    Live --> Queue[Qt main-thread queue]
    Queue --> Engine[Shared structured modeling engine]
    Worker --> Engine
    Engine --> Registry[Versioned capability registry]
    Registry --> Extensions[Reloadable CAD and panel extensions]
    Extensions --> FC
    Engine --> FC[Native FreeCAD documents and geometry]
```

`server.py` owns the model-facing tools and typed Pydantic operation schemas. A backend is chosen when the server starts. Synchronous SDK tool handlers run outside the MCP event loop. `client.py` implements serialized background RPC and authenticated live HTTP requests. It explicitly bypasses environment HTTP proxies for loopback requests.

The v0.8 extension boundary keeps the MCP tool contracts fixed. Discovery returns capability metadata and runtime argument schemas; queries use a guarded read dispatcher, and extension edits use an `extension` variant within the existing atomic batch. New capability names/parameters therefore require a registry reload rather than a changed MCP schema. Legacy typed modeling remains in the core. Live and headless native interpreters each own their registry, and every Engine instance in that interpreter shares it.

`extension_runtime.py` scans the installed package plus explicitly configured trusted roots, validates API v1 manifests/schemas, and stages a candidate generation. Unique package namespaces and a source-snapshot import loader bind both initial and late relative helper imports to captured Python bytes, bypassing timestamp-based bytecode caches. A second scan rejects source changes during staging. Content hashes drive catalog revisions; caller-provided catalog guards reject stale feature contracts independently of model revision guards. A load failure disposes only staged modules and leaves the working generation intact. No tool accepts source code or an import path.

The bundled `parts` extension demonstrates native persistent tube construction and mass-property queries. Edit handlers participate in the core's transaction/geometry checks; a query transaction guard aborts changes to its document. Extensions are trusted local executable code and must honor nonmutating imports, query/edit roles and core-owned transaction lifetimes. They are not sandboxed. Generation-owned feature/view proxies are rejected because their transient namespaces cannot be restored from an FCStd file.

`engine.py` uses only standard-library modules plus FreeCAD modules imported inside the native interpreter. Host Python never imports FreeCAD's binary modules. `worker.py` is imported as a script by FreeCADCmd and stays in a request loop on its main thread. A unique response prefix separates RPC JSON from native console messages. The host drains stdout/stderr separately and correlates response IDs. Native configuration files and user settings are isolated per background worker.

`bridge.py` starts a loopback HTTP server inside FreeCAD and uses a bounded queue plus QTimer. HTTP threads authenticate and enqueue requests; only the GUI timer calls the modeling engine. Every document operation is serialized with FreeCAD's GUI event loop. A running geometry call is synchronous; expensive operations may temporarily block the window. A cancelled pending request is never executed. An operation that has already started cannot be safely interrupted at arbitrary native kernel instructions.

`apply_operations` validates the allowed operation shape, opens a FreeCAD document transaction, executes dependent operations in order, recomputes, checks validity, then commits. On exception it aborts and recomputes. A view-refresh failure after commit is returned as a warning. Views are refreshed on the edited document. The operation transaction does not include independent filesystem writes. UI undo can target the same live transaction; the undo tool can also undo a recent manual transaction.

Revision hashes combine object names/types, inspectable properties and mesh-free native BREP content. Native wrapper memory addresses are normalized. Tokens intentionally describe this session; they do not authenticate serialized file equality or form a complete dependency/version history.

The workspace resolver rejects traversal and resolved paths outside the configured root, including resolved symlinks. Existing writes require explicit overwrite and copy the existing bytes to a unique backup. This is ordinary path confinement, not a defense against a hostile process racing directory changes. Native FCStd restoration and add-on loading remain FreeCAD behaviors.

Imports use native Part readers for STEP/BREP and native Mesh readers for STL. They run inside the same edit transaction as other operations; source bytes are hashed before and after parsing. Import returns a static geometry snapshot and source metadata. Closed-mesh conversion also produces a static BREP snapshot. Native `Part::Fillet` and `Part::Chamfer` objects carry their base dependency and edge parameters without custom Python proxies. They therefore retain native recomputation and save/reopen behavior. Consumed input visibility is stored even in background-created FCStd files.

Topology inspection pages through the current shape's indexed subelements and reports geometry and measurements. Edge selections are resolved against the named base shape and checked for valid, unique indices before kernel work. Revision tokens guard stale edits; topology indices themselves are not durable identifiers. Minimum-distance calls use the native BREP distance solver. Meshes require explicit conversion before those BREP operations. Mesh vertex/connectivity bytes participate in document revision hashes.

The generated start macro is the initial/core-upgrade path: it closes old controls, stops the GUI bridge, disposes the old registry, reloads core modules and creates a fresh bridge/token. Existing document features are native FreeCAD objects, so module reloading does not replace or close those documents. A core MCP contract change still needs the client connection updated. Ordinary extension reloads keep the existing MCP connection, bridge/token, native worker and document ownership intact.

`parameters.py` creates typed native property containers (`App::FeaturePython` without a Proxy) and applies a restricted arithmetic subset of FreeCAD expressions. A lexical allowlist accepts arithmetic, fixed units, pi and references that resolve to numeric native properties or dimensional constraints in the same document. Native parsing, unit checks and cycle detection remain authoritative. No Python evaluation occurs. Numeric paths are resolved explicitly, including canonicalization of native named sketch constraint bindings. Inspection reports expression strings; direct writes to expression-driven datums and placements are rejected.

`features.py` builds native `Part::Loft` and `Part::Mirroring` features. Loft profiles are ordered, distinct, top-level single wires, with closed wires required for solid mode. Dependency traversal rejects update cycles before linking. Mirror planes use document coordinates and nonzero normals; reflected geometry excludes the source. Both types retain native links, recomputation, undo and save/reopen behavior, without custom feature proxies.

The same module builds native `Part::Sweep` and `Part::Helix` features. Sweeps validate ordered single-wire sections, whole-wire or explicitly selected connected spine edges, solid/surface mode and native framing/corner controls. The native `Sections` and `Spine` links retain geometry dependencies through updates, undo and file restore; omitted sweep controls are preserved on update while edge selection is explicitly replaced. Helix creation validates positive dimensions, handedness, taper/top radius and the native turn limit, then stores ordinary native dimensional properties. Profile orientation is explicit rather than inferred. Helix/sweep numeric comparisons use a declared tolerance because the native curve/surface representation is approximate.

`sketches.py` handles native geometry/constraint creation and readback. Rectangles expand into four native lines and, by default, fully constraining named dimensions. Arc creation uses a three-point native constructor. The helper is shared by creation and append operations within the engine's transaction. `inspect_sketch` reads local geometry and dimensional datum metadata without solving or changing the sketch. Geometric constraints have no driving/reference datum flag, so that field is null for them.

`patterns.py` creates compact native `App::Link` arrays (`ShowElement=false`) with evaluated placement lists and read-only parameter metadata. No Python feature proxy executes on recompute or file restore. Native linked geometry follows source dimensions. Source placement is sampled into document-space transforms, and dedicated pattern-update operations resample it while retaining the array object's own Placement. These controls are intentionally distinct from live expression-driven placement constraints. Partial circular spans include endpoints; full circles omit the duplicate final position. Instances remain separate shapes rather than a fused union.

Native array Shape access can construct a new compound, so its identity hash is unstable. Revision hashing serializes a mesh-free topology copy instead, and skips internal native properties. Geometry bounds use `optimalBoundingBox(false, false)` so display triangulations do not change measured extents. The BREP export path writes evaluated shape compounds directly because FreeCAD 1.0.2's object-dispatch exporter can silently ignore link arrays. Empty topology is rejected at import/export boundaries.

The Responses API example uses an in-process MCP client for schema discovery and validated tool dispatch. It does not expose the localhost bridge to OpenAI's remote MCP infrastructure. Cloud-hosted access would need a separate authenticated transport design; the current bridge is for the same computer only.

`motion.py` stores bounded affine coupling rules as a native assembly string property and unwrapped coordinates as native joint floats. Rules form acyclic directed dependencies among movable joints. Commands invert follower chains to recover driver coordinates, expand dependent coordinates, reject conflicts, and use `assemblies.position` for native solving, limits and residual checks. Proposed rules are validated before touching the assembly to avoid unnecessary native recomputation on early rejection. Native Assembly proxies remain standard installed FreeCAD code; this metadata is enforced by our shared controller rather than the native solver alone.

`interference.py` measures native BREP common volume and minimum distance, with bounding-box broad-phase rejection. Motion sampling recursively copies the native assembly graph into a hidden document, drives the copy, records pair results and all joint coordinates, and closes the copy in a finally block. Revisions serialize mesh-free BREP content for every shape because copy operations can change native identity hashes without changing source geometry. This establishes discrete geometric checks rather than a continuous/dynamic collision solver.

`panel.py` and `viewport.py` are stable entry-point facades; the dock and Coin controller live in `extensions/cad_panel`. They use the same Engine for revision-guarded parameter/coupling edits and checks, and the shared pose implementation for responsive playback. The viewport controller resolves picks to assembly links and their nearest movable parent joint, projects the cursor onto the revolute plane or slider axis, and applies coupled poses within one native transaction per gesture. Projection and controller behavior have headless native checks; actual Coin event delivery and physical mouse picking require manual GUI validation.

Reload refuses pending native transactions and active GUI tasks. After staging succeeds, the stable UI facade captures an open dock's settings and removes its timers, selection observer and viewport callback. The registry publishes the candidate and rebuilds the dock against it, preserving selectors, placement and inputs while pausing playback. A rebuild failure restores the previous registry and invokes its UI restoration. The old import namespace is released only after publication/restoration succeeds. Native Qt behavior requires the opt-in isolated GUI harness; lifecycle publication and rollback contracts also have tests using explicit doubles without a GUI.

The engine checks both document pending changes and the application's active transaction. In FreeCAD 1.0.2 an empty document transaction is absent from `HasPendingTransaction`; it is still visible through `getActiveTransaction`. Closing an empty document transaction can leave that application transaction active. The shared transaction finalizer explicitly closes this remainder after commit/abort, including clicks without movement and failures before any property change. External writes, Undo and file saves are rejected while an edit is active.
