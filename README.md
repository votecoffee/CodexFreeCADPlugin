# FreeCADMCPServer

Local MCP tools for live and headless FreeCAD modeling.

Create, inspect and edit native FreeCAD models from an MCP client such as Codex, or from Python. Use an open FreeCAD window for visible editing or a persistent FreeCADCmd worker for background modeling. Both backends share the same modeling engine, validation and file protections. No OpenAI API key is required for MCP or direct Python use.

Application version **26.1022.184257** is a source/package checkpoint using a fixed New York timestamp. Backend, host and standalone plugin share this identity; framework and protocol dependency versions remain independent. Runtime deployment and lifecycle acceptance remain pending. See [versioning](docs/VERSIONING.md) and the [changelog](docs/CHANGELOG.md).

Features include reloadable hole and fastener tools, parametric modeling, movable assemblies, saved joint couplings and interference checks.

A separate **standalone offline candidate** provides read-only FCStd ZIP/XML inspection, source hashes and bundled capability-schema references. It has no native, live-bridge, external-extension or shared-host route. Candidate generation preserves installed selections; source checks do not release its runtime. See [offline profile and acceptance](docs/OFFLINE.md).

The current checkout also includes saved design requirements with opt-in edit enforcement, a source-aware bill of materials, refreshable native spreadsheets, source-preserving parameter sweeps, numeric change previews with added/removed material reports, saved configuration snapshots and dimensioned TechDraw sheets with headless SVG rendering. See [engineering extensions](docs/ENGINEERING.md).

The Python distribution and CLI retain the name `codex-freecad`, the import is `codex_freecad`, and the optional Codex plugin ID is `freecad-modeling` for compatibility. Their display name is **FreeCADMCPServer**.

Development now includes an **experimental app-owned shared-framework host** pinned to `universal-codex-tools==0.20.0`, with MCP 2.3 throughout, a stable MCP front door and immutable backend publications. FreeCAD keeps its own Codex plugin, native skills and direct endpoints. The shared app framework and independent Windows manager do not add a universal Codex plugin or connection. The distribution/import names `universal-codex-tools` / `universal_tools` identify the shared library. Legacy protocol remains the default; candidate publications can explicitly opt into modern discovery. Isolated protocol/package checks do not establish native workflow or Codex UI acceptance. See [framework development and acceptance gaps](docs/FRAMEWORK.md).

The app-owned host serves hash-pinned workflow guides through ordinary tools and Skills-over-MCP on its authenticated HTTP endpoint. Guide-only publications can update connected clients without replacing CAD workers. CAD batches report dispatch/reply progress; cancelling a request cannot establish that FreeCAD stopped. See [runtime guides and feature boundaries](docs/RUNTIME_FEATURES.md).

Lifecycle hardening is under review: plugin connections require an explicitly started host, with bounded frontend slots and Windows process ownership guards. These changes need isolated process-tree and shutdown acceptance before deployment; see [lifecycle status](docs/SERVICE_MANAGEMENT.md#process-lifetime-hardening).

The 0.20 source target integrates the shared durable resource ledger for native workers and protected attachments. Native report-only records preserve recovery barriers. Complete SDK-launcher coverage and shared shutdown remain unaccepted; existing installations are not upgraded by changing the source pin.

Managed source runtimes need the reviewed 0.20 library, including when using direct endpoints. The `managed` extra declares that dependency; install it from a verified local wheel in the selected host environment. Ordinary backend setup alone does not supply this library. Prepare a new framework installation with `Setup.ps1 -Integration none` before the explicit framework installer, and complete lifecycle acceptance before deployment.

To explicitly install that host, run `scripts\Install-Framework.ps1` after normal setup with a trusted framework wheel and its SHA-256. It audits application wheels, installs a separate runtime and updates FreeCAD's existing standalone plugin. The plugin starts only FreeCAD's app-owned host on connection. Later setup/launcher runs preserve this selection; they do not switch connections automatically. See [framework installation](docs/FRAMEWORK.md#install-the-app-owned-host).

The app-owned host reports cached status and component versions to the optional Windows MCP Service Manager. Tray restart remains disabled until an app-owned supervisor can protect every chat's native state. FreeCAD setup does not install another manager. See [tray service reporting](docs/SERVICE_MANAGEMENT.md).

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

FreeCADMCPServer exposes 25 fixed MCP tools and 44 structured operation kinds, with additional CAD capabilities discovered through an extension catalog. Native features, dimensions and dependencies remain editable after saving and reopening FCStd files.

Supported workflows include sketches, pads and pockets, revolutions, patterns, sweeps and helices, lofts, mirrors, expressions, STEP/BREP/STL import, edge finishing, holes, simplified fasteners and assemblies with fixed, revolute and slider joints. The live backend also provides selection, viewport images and a native **Codex CAD** dock with parameter controls, playback and viewport dragging.

Coverage is growing: closed-loop joint driving, nested assemblies, contact dynamics and sheet metal are not implemented. Drawing support currently covers orthographic views and overall extents with SVG output. Fasteners are unthreaded geometry; discrete interference samples do not establish continuous collision-free travel. The [tool reference](docs/TOOLS.md) describes supported inputs and limits. Native panel reload and physical dragging require the [manual GUI checks](docs/PANEL_TESTING.md).

## Install

### Dependencies

- **FreeCAD 1.0.2**, including `FreeCADCmd`, installed separately. Other FreeCAD versions are unverified.
- **Python 3.13** and the Windows Python launcher (`py`) for the PowerShell setup script. The package declares Python 3.11 or later; the reference host environment is Python 3.13 on Windows.
- **Git** to clone the repository.
- **Codex CLI**, if installing the standalone plugin or using direct registration. Other MCP clients can launch the server through stdio.

FreeCAD uses its bundled Python interpreter. Do not install the host MCP dependencies into FreeCAD's Python. See [validation scope](docs/VALIDATION.md) for platform and runtime boundaries.

### Set up a checkout

From PowerShell:

```powershell
git clone https://github.com/votecoffee/FreeCADMCPServer.git
cd FreeCADMCPServer
.\scripts\Setup.ps1
```

Setup creates `.venv`, installs the package and development dependencies, generates installation-specific macros and configuration in ignored `.local/`, and installs FreeCAD's own Codex plugin. The default CAD workspace is ignored `models/`. Use `-Integration none` to skip Codex plugin installation, such as when using another MCP client. To use another workspace or FreeCADCmd executable:

```powershell
.\scripts\Setup.ps1 -Workspace 'C:\CAD\Models' -FreeCADCmd 'C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe'
```

Windows users can install and start the headless stdio server with the root launcher:

```cmd
.\Install-and-Run.cmd
```

It uses the same setup script, then starts the server with `models/` as its workspace. FreeCAD and Python must already be installed. It works from any current directory, leaves the desktop alone, and writes installation/status messages to stderr so stdout remains available for MCP. The server waits for an MCP client; it does not open an interactive prompt.

Use `-InstallOnly` to install without starting a server, or `-SkipInstall` for later launches. Installation includes the standalone Codex plugin by default; `-Integration none` skips that step. Arguments include `-Mode live`, `-Workspace "C:\CAD\Models"` and `-FreeCADCmd "C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe"`. Relative workspaces resolve against the checkout. Repeat custom workspace/FreeCADCmd arguments when using `-SkipInstall`. Live mode connects to a bridge you start manually with the generated macro. Run `.\Install-and-Run.cmd -Help` for help.

Installation creates a **FreeCADMCPServer** shortcut in the current user's Start menu with the bundled [application icon](assets/README.md). It remembers the selected mode, workspace and FreeCADCmd path, and launches the existing installation without reinstalling dependencies. No administrator access is needed. Use `-NoStartMenuShortcut` with either installer to skip creating/updating the shortcut. `scripts\Setup.ps1` defaults the shortcut to headless mode; pass `-ShortcutMode live` for a live shortcut. The entry starts the stdio server in a console and waits for an MCP client. Live mode uses the bridge you start manually in FreeCAD. Rerun setup after moving the checkout or updating the icon to refresh the shortcut; deleting the Start menu entry removes the shortcut.

### Connect an MCP client

Setup installs `freecad-modeling@freecad-development`. Start a new Codex chat after installation. To preview or repeat only the plugin installation after generating configuration:

```powershell
.\scripts\Install-CodexPlugin.ps1 -Preview
.\scripts\Install-CodexPlugin.ps1
```

The installation choices are `standalone` (default) and `none`. Existing direct FreeCAD MCP entries require an explicit migration step before plugin installation. See [standalone connections and session behavior](docs/CONNECTIONS.md).

To install the standalone plugin manually, use the generated marketplace:

```powershell
codex plugin marketplace add (Join-Path (Get-Location) '.local')
codex plugin add freecad-modeling@freecad-development
```

The generated plugin points to this checkout's virtual environment. Regenerate configuration after moving the checkout. Plugin-browser installation and public plugin-directory publishing are unverified.

For direct MCP registration without a plugin, first run setup with `-Integration none`, then run `.\scripts\Register-Codex.ps1`. This adds `freecad-live` and `freecad-headless` to the user Codex MCP configuration. Pass the same `-Workspace` used during setup, then start a new Codex chat. Choose one connection route to avoid duplicate tools.

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

- [Experimental shared-framework host and backend publication](docs/FRAMEWORK.md)
- [Tray service reporting and restart limits](docs/SERVICE_MANAGEMENT.md)
- [Standalone plugin and direct MCP connections](docs/CONNECTIONS.md)
- [Tools, modeling operations, assemblies and file behavior](docs/TOOLS.md)
- [Examples and demonstrations](docs/EXAMPLES.md)
- [Hole and fastener capabilities](docs/HOLES_FASTENERS.md)
- [Engineering extensions: requirements, BOMs, studies and drawings](docs/ENGINEERING.md)
- [Feature roadmap](docs/ROADMAP.md)
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
