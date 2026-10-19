# Reloadable FreeCAD features — extension API v1

Version 0.8 separates a fixed MCP interface from installed CAD and UI extensions. A running chat can discover new capabilities after a reload without changing its MCP tool names or schemas, replacing its MCP connection, or restarting the native worker. Live and headless sessions have separate registries; reload the backend you are using, or both when both are active.

## Install this core update once

Run `scripts\Setup.ps1` to install the current package and regenerate `.local`. Reconnect the FreeCAD MCP servers once to load the four permanent discovery/reload tools and the generic extension edit envelope. Your client may need a new chat to discover this initial interface change. In FreeCAD, run the regenerated `.local\StartBridge.FCMacro` once to load the new native core. These initial steps apply to the migration from v0.7; they are not the normal extension update workflow.

The fixed interface now has 24 MCP tools and 44 structured operation kinds. Existing typed tools and operations remain available. The new tools are `list_capabilities`, `describe_capability`, `run_query`, and `reload_extensions`. The new operation kind is `extension`.

## Normal update workflow

1. Install or edit a complete extension package in an already-configured extension directory.
2. Tell the chat: **“Reload the FreeCAD extensions and list the capabilities that changed.”** Alternatively, click **Reload extensions** in the native dock, or execute `.local\ReloadExtensions.FCMacro` inside FreeCAD. The button and macro reload the live backend only.
3. Describe the capability again and use its current argument schema and `catalog_revision`. An update can change a capability's parameters or add capabilities without changing the MCP tools.

The reload result lists changed extension IDs, versions and content hashes. Unchanged files produce a no-op. Code and relative helper imports come from a fresh, generation-specific source snapshot, so changes are detected even when file size and timestamp are unchanged. Every Python source file is compiled before publication, including helpers imported only when a capability runs. Missing/invalid manifests, unsupported API/schema versions, syntax errors and missing handlers reject the candidate without replacing the working generation. Files changing during staging also reject the update.

Finish an active edit or drag first. A changed generation rebuilds an open CAD dock, preserving document, assembly, joint/follower selection, tab, placement and numeric settings. Playback pauses and old event callbacks/selection observers/timers are removed. Check results are refreshed separately. A UI restore failure switches back to the old generation and attempts to reopen the old dock. Documents and their native Undo history remain owned by the stable core. Actual Qt/viewport integration requires separate manual GUI validation; lifecycle publication/rollback is covered with test doubles, and native model/Undo preservation is tested through a persistent MCP session.

## Call an installed capability

`list_capabilities` returns IDs, query/edit kinds, descriptions, versions and the catalog revision. `describe_capability` returns the exact parameters schema. Every capability receives an existing document.

For the included tube feature, pass this operation to `apply_operations` with the inspected document name and optional document `expected_revision`:

```json
{
  "op": "extension",
  "capability": "parts.create_tube",
  "arguments": {
    "name": "Sleeve",
    "outer_radius": 10,
    "inner_radius": 6,
    "height": 20
  }
}
```

Also supply `catalog_revision` from the capability description when guarding against an extension changing between inspection and execution. This guard is independent of the document revision. Extension operations can be mixed with existing operations in one atomic batch; failure rolls back the entire batch and a successful batch remains one native Undo entry.

For a query, call `run_query` with `document`, `capability="parts.mass_properties"`, and `arguments={"object":"Sleeve","density_kg_m3":7800}`. Results include native volume/area, volume-weighted center of mass of the solid instances, and mass for the specified density. Geometry is mm/mm²/mm³ and density is kg/m³. The dispatcher rejects edit capabilities at the query entry point and vice versa. A native document transaction guard rolls back changes made to the queried document by a misbehaving query handler; native Undo support is required. This guard is not a Python or operating-system sandbox.

Version 0.9 also includes the `holes` and `fasteners` packages. They add six capabilities through this same interface without altering its MCP tools. [Hole and fastener reference](HOLES_FASTENERS.md) covers the native geometry, world entry frames, through-extent refresh, explicit fastener dimensions and unthreaded scope. Installing these complete folders into an existing v0.8 package location and reloading is sufficient for their feature code; the running core's package-version string may remain cached until its next startup. The capability catalog identifies the actual loaded extension versions/content hashes.

## Add an extension

The current checkout also includes `bom`, `studies` and `drawings`, adding nine capabilities through the same fixed tool interface. They provide native metadata/spreadsheet BOMs, source-preserving parameter studies and dimensioned native drawing snapshots with SVG rendering. See [ENGINEERING.md](ENGINEERING.md). Installing these complete extension folders and reloading loads the feature code without introducing new MCP tool schemas. Qt core dispatch for headless drawing projection is initialized only when a drawing edit is requested, and remains owned by the native runtime across reloads.

Built-ins live under `src/codex_freecad/extensions` in the development checkout and inside the installed Python package in a wheel. Additional roots are explicit startup configuration, never supplied as tool arguments or automatically discovered in CAD model folders:

```powershell
.\scripts\Setup.ps1 -Extensions 'C:\CADTools\Extensions'
.\scripts\Register-Codex.ps1 -Extensions 'C:\CADTools\Extensions'
```

Use the same roots when generating the live macro and registering headless MCP. Direct Python setup also accepts repeated `--extensions` arguments; direct `HeadlessClient` accepts `extension_dirs=[...]`. Changing the configured roots requires a backend configuration update; adding/removing packages within a configured root uses the normal reload command. If needed, `CODEX_FREECAD_EXTENSION_PATHS` supplies a JSON array of roots at native startup. Explicit startup configuration takes precedence.

Each root contains package folders:

```text
Extensions/
  custom_parts/
    manifest.json
    __init__.py
    helpers.py
```

The manifest has exactly these fields. Capability IDs become `extension_id.local_name`:

```json
{
  "id": "custom_parts",
  "version": "1.0.0",
  "api_version": 1,
  "description": "Custom native parts",
  "ui": false,
  "capabilities": {
    "block": {
      "kind": "edit",
      "description": "Create a native box; side is in mm",
      "handler": "block",
      "parameters": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "side"],
        "properties": {
          "name": {"type":"string","pattern":"^[A-Za-z][A-Za-z0-9_]*$"},
          "side": {"type":"number","exclusiveMinimum":0}
        }
      }
    }
  }
}
```

Its `__init__.py` exports the named handler:

```python
def block(engine, doc, arguments):
    side = arguments["side"]
    return engine.operation(doc, {
        "op": "create_box", "name": arguments["name"],
        "length": side, "width": side, "height": side,
    })
```

Handlers take `(engine, doc, arguments)` and return finite JSON. They use the shared engine's workspace/modeling helpers or native FreeCAD APIs. The core owns the transaction; handlers must not commit/abort it, close existing documents, start background callbacks, or reload the registry. A source-preserving study may own a hidden temporary dependency copy: close only that copy in a `finally` block and restore the previous active document on success or failure. It must not retain external source links or change the source's revision/Undo. Imports must not change models or start UI activity. Relative helper imports are supported and stay bound to the loaded generation. Use Python 3.11-compatible code and standard/native FreeCAD dependencies. Extension packages are trusted local executable code with the native process's privileges; the tool interface accepts data and registered capability IDs, with no source-code or module-path parameters.

Use persistent native features and links. Generation-owned feature/view proxies are rejected because their temporary module namespaces cannot be restored from FCStd after a restart. Existing native output therefore remains usable when its creation extension is removed. The bundled `cad_panel` package is the supported dock lifecycle provider; arbitrary additional UI providers are outside extension API v1.

Schemas support single `type` values (`object`, `array`, `string`, `number`, `integer`, `boolean`, `null`), properties/required/strict additional fields, homogeneous items and length limits, numeric bounds, string patterns, enums, descriptions/titles and defaults. Defaults are copied into arguments before required-field checks. Unknown keywords, unions, external references and schema functions are rejected. Numbers are finite; booleans are not numbers. Limits include 12 schema/value levels, 64 KiB argument payloads, 32 extension packages and 256 capabilities. A package has at most 128 Python/JSON files of at most 256 KiB each and 4 MiB total. Metadata/resource JSON participates in content hashes; API v1 snapshots Python imports, not arbitrary filesystem resource reads.

The stable core still contains legacy typed modeling implementations. Editing `server.py`, `engine.py`, `schemas.py`, the loader, or legacy feature helpers is a core update, not an extension reload. Native FreeCAD/Python upgrades also require the relevant process update. New routine features should use extensions to keep that boundary stable.

## Verification

The persistent stdio MCP regression changes helper code, adds a capability with new parameters, reloads it, and calls it through the original connection. It verifies identical MCP schemas and native worker PID, unchanged model revision, Undo across reloads, failed-load recovery, stale-catalog rejection, and fresh native reopen of output without the external extension. Additional tests cover helper cache isolation, lifecycle commit/rollback contracts, strict runtime schemas, mixed-batch rollback, guarded queries, persisted tube geometry and rejection of transient feature proxies.

For manual native UI validation, run `.venv\Scripts\python.exe scripts\smoke_panel.py --interactive` from the repository. It opens an isolated test window and checks a dock rebuild after an extension update, including bridge/token continuity, before holding the arm model for manual dragging. See [PANEL_TESTING.md](PANEL_TESTING.md) for expected manual results.
