# FreeCADMCPServer

Local MCP tools for live and headless FreeCAD modeling.

Create, inspect and edit native FreeCAD models from an MCP client such as Codex, or from Python. Use an open FreeCAD window for visible editing or a persistent FreeCADCmd worker for background modeling. Both backends share the same modeling engine, validation and file protections. No OpenAI API key is required for MCP or direct Python use.

Features include reloadable hole and fastener tools, parametric modeling, movable assemblies,
saved joint couplings, interference checks, design requirements, bills of materials, parameter
studies and dimensioned TechDraw sheets. See [engineering extensions](docs/ENGINEERING.md).

FreeCAD keeps its **standalone MCP server, app-owned Codex plugin and native skills**. The
[CodexMCPBroker project](https://github.com/votecoffee/CodexMCPBroker) supplies the shared framework
library and a **separate Windows management app**. There is no universal Codex plugin or broker
route to install. The manager is optional; it does not own or migrate CAD documents.

The host dependency is pinned to `universal-codex-tools==0.20.0` and MCP `2.3.0`. FreeCAD's bundled
Python stays independent of host MCP/Pydantic packages. The Python distribution/CLI remains
`codex-freecad`, the import is `codex_freecad`, and the plugin ID is `freecad-modeling`.

| Connection | Scope | Guide |
| --- | --- | --- |
| Standalone native | 27 tools: shared CAD tools plus target review and native workflow; private headless worker or explicitly pinned live bridge | [Native profile](docs/NATIVE.md) |
| Standalone offline | Four tools for FCStd ZIP/XML evidence and bundled schema references; no native CAD | [Offline profile](docs/OFFLINE.md) |
| Checkout direct | Development API only; not published by the installer | [Connections](docs/CONNECTIONS.md) |
| Experimental app-owned host | Immutable backend publications, retained contexts and runtime guidance | [Framework guide](docs/FRAMEWORK.md) |

The native profile defines 48 metadata slots in one shared pool: 24 steady connections plus
24 overlapping reconnects. Slots 0–15 retain the 128 MiB Windows commit reservation used by
release 26.1024.101538; slots 16–47 use 96 MiB, giving a 5 GiB metadata-only reservation.
The smaller reservation is distinct from measured private memory use. Native capacity
is reserved only at the first backend call and remains with that connection until cleanup. A
competing native call returns a busy explanation before dispatch. Hash/revision guards and durable
uncertainty receipts protect file operations; a new chat does not reconcile an unknown write.
Existing connections retain their leases and count in the same pool during updates. Earlier
four-slot legacy generations retain their original policies and are reported separately. See the
[connection development and capacity guide](docs/CONNECTION_READINESS.md) for limits and proof requirements.

Headless geometry, save/reopen/export and process cleanup have been exercised separately from
source/fixture checks. GUI interaction, physical dragging and experimental shared-host acceptance
remain separate. See [validation scope](docs/VALIDATION.md) and [service management](docs/SERVICE_MANAGEMENT.md).
Application release stamps, framework versions and protocol versions are independent; see
[versioning](docs/VERSIONING.md) and the [changelog](docs/CHANGELOG.md).

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

The checkout direct backend exposes 25 fixed MCP tools (27 in the standalone native profile) and 44 structured operation kinds, with additional CAD capabilities discovered through an extension catalog. Native features, dimensions and dependencies remain editable after saving and reopening FCStd files.

Supported workflows include sketches, pads and pockets, revolutions, patterns, sweeps and helices, lofts, mirrors, expressions, STEP/BREP/STL import, edge finishing, holes, simplified fasteners and assemblies with fixed, revolute and slider joints. The live backend also provides selection, viewport images and a native **Codex CAD** dock with parameter controls, playback and viewport dragging.

Coverage is growing: closed-loop joint driving, nested assemblies, contact dynamics and sheet metal are not implemented. Drawing support currently covers orthographic views and overall extents with SVG output. Fasteners are unthreaded geometry; discrete interference samples do not establish continuous collision-free travel. The [tool reference](docs/TOOLS.md) describes supported inputs and limits. Native panel reload and physical dragging require the [manual GUI checks](docs/PANEL_TESTING.md).

## Install

### Dependencies

- **FreeCAD 1.0.2**, including `FreeCADCmd`, installed separately. Other FreeCAD versions are unverified.
- **Python 3.13** and the Windows Python launcher (`py`) for the PowerShell setup script. The package declares Python 3.11 or later; the reference host environment is Python 3.13 on Windows.
- **Git** to clone the repository.
- **Codex CLI**, if installing the standalone plugin. Other MCP clients use the retained stable stdio route.

FreeCAD uses its bundled Python interpreter. Do not install the host MCP dependencies into FreeCAD's Python. See [validation scope](docs/VALIDATION.md) for platform and runtime boundaries.

### Install the stable standalone server

From PowerShell, using a clean committed checkout:

```powershell
git clone https://github.com/votecoffee/FreeCADMCPServer.git
cd FreeCADMCPServer
.\Install.cmd -FrameworkWheel "C:\Packages\universal_codex_tools-0.20.0-py3-none-any.whl" -FrameworkSha256 TRUSTED_SHA256
```

Supply the reviewed framework wheel from [CodexMCPBroker](https://github.com/votecoffee/CodexMCPBroker)
and its independently verified SHA-256. It must also match the reviewed dependency lock.
Existing installations can reuse retained wheels; `-Wheelhouse PATH` supplies an offline wheel
directory. Other missing dependencies download only during explicit installation, at pinned
versions and hashes. MCP remains **2.3.0**, framework **0.20.0**.

Setup builds and verifies the source wheel, checks all wheel RECORD bytes, and selects a retained
runtime beneath `%USERPROFILE%\.local\share\FreeCADMCPServer`. The stable entry, working directory, runtime,
plugin and skills survive checkout moves and disposable Codex plugin-cache replacement.
Installation reads/hashes the explicit FreeCAD executable; it does not start FreeCAD or open a model.
See the [stable launcher contract and recovery guide](docs/STABLE_LAUNCHER.md).

```powershell
.\Install.cmd -Workspace 'C:\CAD\Models' -FreeCADCmd 'C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe'
```

Install, run, or combine both steps with the root launchers:

```cmd
.\Install.cmd -Help
.\Run.cmd
.\Install-and-Run.cmd -FrameworkWheel "C:\Packages\universal_codex_tools-0.20.0-py3-none-any.whl" -FrameworkSha256 TRUSTED_SHA256
```

`Install.cmd` installs/selects without starting a server. `Run.cmd` runs the existing selection
with inherited stdio, without setup or downloads. The combined command supports `-InstallOnly`
and `-SkipInstall`. Change workspace, mode or target during installation; run does not override
a reviewed binding. `-InstallRoot PATH` selects another persistent app-owned root. Fresh workspaces
default beneath that root. Existing native upgrades retain the configured workspace, shared
admission, registry and uncertainty receipts. Old retained state directories remain required
while their bindings or live peers reference them.

Installation includes the standalone plugin by default; `-Integration none` prepares/selects
without changing Codex. Live mode requires an explicit existing bridge descriptor, supplied with
`-Mode live -BridgeDescriptor PATH`. No installer or launcher starts GUI macros. Run the combined
command with `-Help` for supported switches.

The Start menu shortcut uses the bundled [icon](assets/README.md) and shows the verified installed
selection. It reports running health as **Not reporting** unless actually observed. It does not
launch an engineering application. `-NoStartMenuShortcut` skips its creation.

### Connect an MCP client

The installer keeps `freecad-modeling@freecad-development` and its native skill. The plugin has
one resolved `freecad` connection using retained real `pythonw.exe -I -S -B`, the app-owned
`Start-Mcp.py`, and stable `cwd/`. There is no universal plugin or shared broker route.
Start a new Codex chat after a host reload when needed; CLI success alone does not prove discovery
inside an already-open desktop chat. To preview or install only the plugin after preparation:

```powershell
.\scripts\Install-CodexPlugin.ps1 -Preview
.\scripts\Install-CodexPlugin.ps1
```

The retained `installation.json` contains the plugin directory and exact route for other MCP
clients. Existing checkout/cache-bound or duplicate routes need an explicit byte-preserving
migration and are not silently removed. The old dual `Register-Codex.ps1` path is retired.
The application never edits immutable Codex cache files. See
[connections and migration](docs/CONNECTIONS.md).

### Update extensions

For an existing v0.8-compatible backend, update the installed extension code and call `reload_extensions`, use the dock's **Reload extensions** button, or run `.local\ReloadExtensions.FCMacro`. Discover the current capability schemas after reloading. Routine extension updates preserve the MCP connection and native documents.

That development/live reload workflow requires explicitly reviewed extension roots. Production
bundled code remains immutable; a new reviewed runtime applies to new connections while peers
retain their original code and documents. Do not edit a selected retained runtime in place.

Core changes can require a reconnect. Upgrading from v0.7 or earlier requires rerunning setup, reconnecting the MCP servers and running the regenerated start macro once. See the [extension guide](docs/EXTENSIONS.md).

## Usage

The selected headless server starts FreeCADCmd on its first native call. Metadata discovery,
current guides and target-file hash review do not reserve native capacity. Visible editing uses
an explicitly selected existing live bridge; keep that GUI open. Legacy development macros are
separate workflows and are not run by the stable installer.

Example chat requests:

> Use the selected FreeCAD headless connection to create an 80 × 50 × 8 mm mounting plate with a 10 mm through-hole at X=15, Y=15. Verify the solid and save Plate.FCStd and Plate.step.

> Use the selected FreeCAD live connection to inspect the selected object. Change its pad length to 25 mm, verify its volume and show the updated view. Leave the document unsaved.

> Reload the FreeCAD extensions. Discover holes.bolt_circle, drill six clearance holes in the flange and add dimensioned socket-cap bolts. Check for overlap and save a new copy.

Live and headless sessions have separate documents and Undo histories. Exchange models by saving FCStd explicitly. File operations stay inside the configured workspace; overwrites require explicit opt-in and preserve a backup. Use trusted CAD files and installed add-ons: native FCStd loading is not a sandbox. See [session and file behavior](docs/TOOLS.md#session-and-file-behavior).

### CLI

For development only, a separately prepared development environment can run the source endpoints:

```powershell
.\.venv\Scripts\codex-freecad.exe --mode headless --workspace .\models
.\.venv\Scripts\codex-freecad.exe --mode live --workspace .\models
```

Launch one backend per MCP server entry. These commands speak MCP over stdio and wait for a client; they are not interactive terminals. `python -m codex_freecad.server` is equivalent. Use `--help` for options, including `--freecad-cmd` and trusted startup `--extensions` directories.

### Python

After preparing the development environment, run this with its Python. The installed server uses
its retained closure instead of this environment. Choose a fresh output name on repeat runs:

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

- [Stable standalone launcher, updates and recovery](docs/STABLE_LAUNCHER.md)

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

The production installer retains a separate runtime; it does not add developer test tools to it.
Prepare a development environment explicitly, including the reviewed framework wheel:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install C:\Packages\universal_codex_tools-0.20.0-py3-none-any.whl
.\.venv\Scripts\python.exe -m pip install -e ".[dev,managed]"
```

Source-generated macros and experimental host publications remain development workflows. Their
preview configurations are not production routes; plugin publication requires the stable entry.

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
