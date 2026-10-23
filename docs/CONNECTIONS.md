# Standalone connections

FreeCAD owns its standalone MCP server, Codex plugin and native skill. The shared
framework and optional separate Windows manager come from
[CodexMCPBroker](https://github.com/votecoffee/CodexMCPBroker). Installing that
manager does not install this server, migrate models, or introduce a universal
plugin/broker route. Framework **0.20.0** and SDK **2.3.0** remain independently pinned.

## Installed route

Follow [README installation](../README.md#install). The root installer prepares
a retained immutable runtime and selects an app-owned `Start-Mcp.py` and `cwd/`
outside the checkout and disposable plugin caches. The direct standalone native
profile has one `freecad` connection and 27 tools. The offline profile has four
read-only FCStd ZIP/XML tools and no native execution. See
[stable launch and recovery](STABLE_LAUNCHER.md) for exact publication policy.

```powershell
.\Install.cmd -Integration none -NoStartMenuShortcut
.\scripts\Install-CodexPlugin.ps1 -Preview
.\scripts\Install-CodexPlugin.ps1
```

The first command prepares/selects without changing Codex. Supply the reviewed
framework wheel/hash on a fresh machine, or a reviewed retained wheelhouse. The
plugin installer supports `-CodexHome` for a disposable or alternate host home.
Preview reads configuration but never writes it. Actual plugin publication refuses
legacy source-bound routes; it uses only the current reviewed stable selection.

The plugin source remains in the retained connection directory. Its manifest and
native skill are application-owned. Updating a Codex cache cannot remove the
launcher, interpreter binding, working directory, backend closure or shared state.
The application never patches files inside immutable Codex caches.

Other stdio clients can use the exact command, argument array, cwd and environment
in the app-owned `installation.json`. `Run.cmd` starts that existing selection
without setup. Published host routes launch the real `pythonw` entry directly,
without CMD/PowerShell forwarding wrappers. An ordinary console is not an MCP
client; the windowless profile requires inherited protocol pipes.

## Migrate an older host binding

Save native work before closing its owning connection. An uncertain operation
requires inspection of its original model/receipt, not replay or route switching.
Keep old runtime directories, plugin versions, state, registry and exact backups
until no configuration or active owned generation needs them.

Prepare and validate the new stable installation first. Read the actual host
settings as bytes, preserve BOM/comments/newlines/unrelated entries, and compare
the expected route/settings hash before a serialized atomic publication. Keep
one effective enabled `freecad` route and the standalone plugin/skills. If a
host leaves a packaged placeholder unresolved, an authorized host-local absolute
binding can select the same stable entry while disabling the unresolved duplicate.
Never restore a stale global configuration over another app's changes.

`Register-Codex.ps1` no longer adds checkout-bound `freecad-live` and
`freecad-headless` duplicates. Existing old entries cause plugin installation to
stop for a reviewed migration; they are not automatically deleted. Installation,
plugin enablement, route enablement, backend readiness and desktop-chat discovery
are separate observations. A new chat/host reload may be required, and direct
SDK/CLI evidence does not prove activation in an already-open desktop chat.

## Sessions and updates

Live and headless modes use the shared modeling engine with separate documents
and Undo histories. Live selection requires an explicit existing bridge descriptor;
no GUI is started. FCStd save/open is the explicit exchange between sessions.
Headless disconnect loses unsaved documents; reconnect does not recover them.

An update atomically selects reviewed new bytes through the unchanged stable host
route. Active peers retain their original runtime, documents and shared leases.
Shared state/registry bindings remain explicit and are preserved during an upgrade.
Management distinguishes selected from running versions and never equates a valid
selection with observed health. EOF and parent loss use the retained original wire
and pinned process handle, with a separate parent watcher for blocked readers.

## Development and experimental hosts

The source setup generator can still prepare development macros and preview
configurations. Those previews are not production registrations. The
[experimental framework host](FRAMEWORK.md) remains a separate, explicitly reviewed
profile; installing the stable standalone native server does not enable or accept
shared-host/native GUI behavior. Retired broker/auto routes and broker manifests
are not part of the current installer.
