# Standalone connections

FreeCADMCPServer owns its Codex plugin and MCP endpoints. Live GUI editing and headless FreeCADCmd modeling use the same application engine, with separate documents and Undo histories.

## Codex plugin

Windows setup installs `freecad-modeling@freecad-development` from the generated local marketplace:

```powershell
.\scripts\Setup.ps1
```

The root `Install-and-Run.cmd -InstallOnly` performs the same installation without starting a server. The installed plugin exposes both `freecad-live` and `freecad-headless`. Start a new Codex chat after installation. Live editing connects to the bridge you start manually with `.local\StartBridge.FCMacro`.

Setup uses this checkout's virtual environment and stores machine-specific files in ignored `.local/`. Rerun setup after moving the checkout or changing the native skill. To generate configuration before reviewing the plugin installation:

```powershell
.\scripts\Setup.ps1 -Integration none
.\scripts\Install-CodexPlugin.ps1 -Preview
.\scripts\Install-CodexPlugin.ps1
```

`standalone` and `none` are the only installation choices. Preview never changes Codex configuration. `-CodexHome` on the plugin installer supports another Codex installation; otherwise it uses `CODEX_HOME` or `~/.codex`. Existing direct FreeCAD MCP entries stop plugin installation rather than being removed automatically. The package uses Codex's [local marketplace and plugin format](https://developers.openai.com/plugins/build/plugins).

## Direct MCP clients

For a client that launches stdio MCP servers, run setup with `-Integration none` and use the generated `.local\codex-mcp.toml` as a configuration reference. To register those endpoints directly with Codex:

```powershell
.\scripts\Setup.ps1 -Integration none
.\scripts\Register-Codex.ps1
```

Use the same workspace arguments for setup and registration. Choose one FreeCAD connection per workflow to avoid duplicate tools and independent headless documents. Saving an FCStd file is the explicit exchange between sessions. Disconnecting a headless server loses unsaved documents; reconnecting does not recover them automatically.

## App-owned framework host

The [experimental framework host](FRAMEWORK.md) packages another standalone FreeCAD plugin with a stable discovery/invocation front door and immutable backend publications. Its installation and activation remain separate from normal setup. The shared library is an implementation dependency; no central broker plugin, service registration or automatic route selection is provided.

## Updates from older installations

Broker registration, automatic Universal Tools detection, generated broker service manifests and the `--broker-catalog` server option have been removed. Old `broker` and `auto` installer choices are rejected before changing client configuration. Retire previous FreeCAD registrations in their original administrator-managed environment before using the standalone plugin; this installer does not manage other applications or a shared service's state. Old generated `.local/broker/` manifests are unused and can be archived outside the active configuration.

Save native documents before disconnecting an old route. Do not switch routes or replay a write after a lost reply; inspect the original operation and model state first. Document revisions, workspace confinement, explicit overwrites and backups remain application safeguards.
