# FreeCADMCPServer

Local MCP tools for live and headless FreeCAD modeling.

Create, inspect and edit native FreeCAD models from an MCP client such as Codex, or from Python. Use an open FreeCAD window for visible editing or a persistent FreeCADCmd worker for background modeling. Both backends share the same modeling engine, validation and file protections. No OpenAI API key is required for MCP or direct Python use.

Version **0.9.0** includes reloadable hole and fastener tools, parametric modeling, movable assemblies, saved joint couplings and interference checks. See the [changelog](docs/CHANGELOG.md) for release details.

The current checkout also includes a source-aware bill of materials, refreshable native spreadsheets, source-preserving parameter sweeps, saved configuration snapshots and dimensioned TechDraw sheets with headless SVG rendering. See [engineering extensions](docs/ENGINEERING.md).

The Python distribution and CLI retain the name `codex-freecad`, the import is `codex_freecad`, and the optional Codex plugin ID is `freecad-modeling` for compatibility. Their display name is **FreeCADMCPServer**.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Documentation](#documentation)
- [Development](#development)
- [API](#api)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

FreeCADMCPServer exposes 24 fixed MCP tools and 44 structured operation kinds, with additional CAD capabilities discovered through an extension catalog. Native features, dimensions and dependencies remain editable after saving and reopening FCStd files.

Supported workflows include sketches, pads and pockets, revolutions, patterns, sweeps and helices, lofts, mirrors, expressions, STEP/BREP/STL import, edge finishing, holes, simplified fasteners and assemblies with fixed, revolute and slider joints. The live backend also provides selection, viewport images and a native **Codex CAD** dock with parameter controls, playback and viewport dragging.

Coverage is growing: closed-loop joint driving, nested assemblies, contact dynamics and sheet metal are not implemented. Drawing support currently covers orthographic views and overall extents with SVG output. Fasteners are unthreaded geometry; discrete interference samples do not establish continuous collision-free travel. The [tool reference](docs/TOOLS.md) describes supported inputs and limits. Native panel reload and physical dragging require the [manual GUI checks](docs/PANEL_TESTING.md).

## Install

### Dependencies

- **FreeCAD 1.0.2**, including `FreeCADCmd`, installed separately. Other FreeCAD versions are unverified.
- **Python 3.13** and the Windows Python launcher (`py`) for the PowerShell setup script. The package declares Python 3.11 or later; the reference host environment is Python 3.13 on Windows.
- **Git** to clone the repository.
- **Codex CLI**, if using the registration script. Other MCP clients can launch the server through stdio.

FreeCAD uses its bundled Python interpreter. Do not install the host MCP dependencies into FreeCAD's Python. See [validation scope](docs/VALIDATION.md) for platform and runtime boundaries.

### Set up a checkout

From PowerShell:

```powershell
git clone https://github.com/votecoffee/FreeCADMCPServer.git
cd FreeCADMCPServer
.\scripts\Setup.ps1
```

Setup creates `.venv`, installs the package and development dependencies, and generates installation-specific macros and configuration in ignored `.local/`. The default CAD workspace is ignored `models/`. To use another workspace or FreeCADCmd executable:

```powershell
.\scripts\Setup.ps1 -Workspace 'C:\CAD\Models' -FreeCADCmd 'C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe'
```

### Connect an MCP client

For Codex, run:

```powershell
.\scripts\Register-Codex.ps1
```

This adds `freecad-live` and `freecad-headless` to the user Codex MCP configuration. If setup used a custom workspace, pass the same `-Workspace` argument to registration. Start a new Codex chat after registering.

Alternatively, setup generates a local Codex plugin and a repository marketplace. Use this route instead of direct registration to avoid duplicate tools:

```powershell
codex plugin marketplace add (Get-Location).Path
codex plugin add freecad-modeling@freecad-development
```

The generated plugin points to this checkout's virtual environment. Regenerate configuration after moving the checkout. Plugin-browser installation and public plugin-directory publishing are unverified.

### Update extensions

For an existing v0.8-compatible backend, update the installed extension code and call `reload_extensions`, use the dock's **Reload extensions** button, or run `.local\ReloadExtensions.FCMacro`. Discover the current capability schemas after reloading. Routine extension updates preserve the MCP connection and native documents.

Core changes can require a reconnect. Upgrading from v0.7 or earlier requires rerunning setup, reconnecting the MCP servers and running the regenerated start macro once. See the [extension guide](docs/EXTENSIONS.md).

## Usage

The headless server starts FreeCADCmd on its first modeling call. To edit visibly, open FreeCAD and execute `.local\StartBridge.FCMacro` through **Macro → Macros → Execute**. Keep that window open; `.local\StopBridge.FCMacro` disconnects it. The start macro also opens the Codex CAD dock.

Example chat requests:

> Use freecad-headless to create an 80 × 50 × 8 mm mounting plate with a 10 mm through-hole at X=15, Y=15. Verify the solid and save Plate.FCStd and Plate.step.

> Use freecad-live to inspect the selected object. Change its pad length to 25 mm, verify its volume and show the updated view. Leave the document unsaved.

> Reload the FreeCAD extensions. Discover holes.bolt_circle, drill six clearance holes in the flange and add dimensioned socket-cap bolts. Check for overlap and save a new copy.

Live and headless sessions have separate documents and Undo histories. Exchange models by saving FCStd explicitly. File operations stay inside the configured workspace; overwrites require explicit opt-in and preserve a backup. Use trusted CAD files and installed add-ons: native FCStd loading is not a sandbox. See [session and file behavior](docs/TOOLS.md#session-and-file-behavior).

### CLI

An MCP client can launch either stdio server directly:

```powershell
.\.venv\Scripts\codex-freecad.exe --mode headless --workspace .\models
.\.venv\Scripts\codex-freecad.exe --mode live --workspace .\models
```

Launch one backend per MCP server entry. These commands speak MCP over stdio and wait for a client; they are not interactive terminals. `python -m codex_freecad.server` is equivalent. Use `--help` for options, including `--freecad-cmd` and trusted startup `--extensions` directories.

### Python

After setup, run this with the virtual environment's Python. Choose a fresh output name on repeat runs:

```python
from codex_freecad.client import HeadlessClient

with HeadlessClient("models") as cad:
    created = cad.call("new_document", name="BoxDemo")
    result = cad.call(
        "apply_operations",
        document="BoxDemo",
        expected_revision=created["revision"],
        operations=[{"op": "create_box", "name": "Block", "length": 40, "width": 30, "height": 10}],
    )
    print(result)
    print(cad.call("save_document", document="BoxDemo", path="BoxDemo.FCStd"))
```

`LiveClient` provides the same modeling calls using the bridge state file. Run [examples/direct_client.py](examples/direct_client.py) with `--mode live` for a complete example. See the [example guide](docs/EXAMPLES.md) for more parts, hardware, planetary assemblies and the optional paid Responses API adapter.

For a complete BOM, thickness-study and drawing example, run `.venv\Scripts\python.exe examples\engineering_plate.py --workspace work\engineering-demo`. It creates FCStd/STEP models, a dimensioned SVG, CSV and verification reports using FreeCADCmd. See [engineering examples](docs/EXAMPLES.md#bom-thickness-studies-and-dimensioned-drawings).

## Documentation

- [Tools, modeling operations, assemblies and file behavior](docs/TOOLS.md)
- [Examples and demonstrations](docs/EXAMPLES.md)
- [Hole and fastener capabilities](docs/HOLES_FASTENERS.md)
- [Engineering extensions: BOMs, parameter studies and drawings](docs/ENGINEERING.md)
- [Extension installation, reloads and authoring](docs/EXTENSIONS.md)
- [Native panel and manual drag checks](docs/PANEL_TESTING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Validation procedures and coverage](docs/VALIDATION.md)
- [Changelog](docs/CHANGELOG.md)

## Development

Run from the repository root after setup:

```powershell
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check src tests examples scripts
.\.venv\Scripts\ruff.exe format --check src tests examples scripts
```

Use `pytest -m 'not native'` for host-only checks. Native tests require FreeCADCmd and skip if it cannot be found. Set `FREECAD_CMD` for another executable. GUI smoke scripts are separate, opt-in checks; see [validation instructions](docs/VALIDATION.md).

Keep personal CAD projects, machine paths, session notes, screenshots and raw test reports in ignored `local/`, `models/` or `work/`, or outside the checkout. `.local/` holds generated configuration; `.venv/`, `build/` and `dist/` are also ignored. Publish only reusable examples and documentation. See [contribution guidance](CONTRIBUTING.md) for the repository layout and release checks.

## API

Use `HeadlessClient.call(method, **arguments)` or `LiveClient.call(method, **arguments)` for the application API. Modeling edits use `apply_operations` with structured operations and an optional `expected_revision` guard. A failed batch rolls back as one native transaction.

For extension features, discover schemas with `list_capabilities` and `describe_capability`, use `run_query` for reads, and submit edits through the `extension` operation. The MCP tool schemas remain fixed during extension reloads. See the [tool reference](docs/TOOLS.md) and [extension contract](docs/EXTENSIONS.md).

## Maintainers

[@votecoffee](https://github.com/votecoffee)

## Contributing

[Open an issue](https://github.com/votecoffee/FreeCADMCPServer/issues) for questions, bugs or feature proposals. Pull requests are welcome; read [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks and public-repository hygiene.

## License

[MIT](LICENSE) © 2026 votecoffee.
