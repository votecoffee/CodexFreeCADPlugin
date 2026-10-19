# Codex plugin and Universal Tools integration

The [shared-framework host](FRAMEWORK.md) is now the primary development direction. This page documents the existing optional direct-to-broker route. Its compatibility checks do not establish aggregation of a framework-based app host.

FreeCADMCPServer remains an independent MCP application. Setup always generates its own `freecad-modeling` Codex plugin and direct stdio configuration, plus optional Universal Tools service manifests. Neither backend requires the broker to run.

The standalone package uses Codex's [local marketplace and plugin format](https://developers.openai.com/plugins/build/plugins). Universal Tools registration is a separate application integration contract.

## Choose a connection

Run setup, then use the broker-aware installer:

```powershell
.\scripts\Setup.ps1
.\scripts\Install-CodexPlugin.ps1 -Preview
.\scripts\Install-CodexPlugin.ps1
```

The default `auto` policy checks the user configuration under `CODEX_HOME`, or `~/.codex` when unset. An explicitly enabled `universal-tools@<marketplace>` plugin with a valid cached manifest and runtime selects broker registration. FreeCAD's own plugin is generated but is not installed in this case. The installer registers `freecad-live` and `freecad-headless` through the broker's CLI. Ask an existing broker chat to call `refresh_services` afterward.

If no enabled Universal Tools plugin is found, the installer adds the generated local marketplace and installs `freecad-modeling@freecad-development` through the Codex CLI. A disabled plugin or cache files alone do not count as an enabled installation. Start a new Codex chat after installing the standalone plugin.

Broken or ambiguous enabled broker runtimes stop installation. They do not silently install a second integration. Repair the installation or select a runtime explicitly:

```powershell
.\scripts\Install-CodexPlugin.ps1 -Integration broker -BrokerPython 'C:\Apps\Broker\python.exe' -BrokerState 'C:\Apps\Broker\state'
```

Universal Tools 0.8 or later is required for exclusive sessions, exact write allowlists and capability catalogs. Before registering either service, the installer validates all pending manifests using the selected broker's actual Python package. An incompatible runtime stops without registering services, even if its cached plugin advertises a newer version. The installer never upgrades the broker automatically.

`-Integration standalone` explicitly chooses the FreeCAD plugin even when Universal Tools is installed. `-Integration none` performs no connection changes. `-CodexHome` supports a separate Codex installation. Detection reads user settings and installed cache files; it does not resolve project or managed policy overrides, check the running broker, or prove that a particular chat has enabled the plugin. Use an explicit choice when those settings differ.

For other operating systems or Python installations, use the same planner directly:

```sh
python -m codex_freecad.setup --workspace models --output .local
python -m codex_freecad.integration --output .local
python -m codex_freecad.integration --output .local --apply
```

Without `--apply`, the Python command only prints a connection plan. Setup and the Windows root launcher continue to generate configuration without installing a Codex plugin automatically.

## Existing installations

The installer never removes direct MCP entries or disables an installed FreeCAD plugin. Before migrating to the broker, explicitly disable those direct FreeCAD connections in Codex, then rerun the installer. Unsaved documents in an old headless process do not transfer to a new broker session; save them before disconnecting.

Matching broker registrations are left alone on repeat runs. If either existing service differs, preflight stops before installing either service. Inspect the generated manifests and intentionally update each changed service with the broker CLI:

```text
python -m universal_tools --state STATE register .local/broker/freecad-headless.service.json --replace
```

Use the broker's configured Python and state directory. Replace the live manifest separately when needed. An installation failure can leave a newly registered service; rerunning the installer recognizes matching registrations. It does not automatically start or refresh the broker, replay native work, or clear a recovery barrier.

## Session and write behavior

Both manifests use `session_mode: exclusive`. Acquire the selected service, retain its `context_id` for the workflow, and pass it to routed calls. This keeps one MCP adapter and its headless worker across calls, preserving documents, extension generations and Undo. Transient sessions are unsuitable for these process-owned documents. Live and headless remain independent backends.

The generated manifests enable writes only for the ten explicitly named mutating outer tools, including `apply_operations`, save/export, reload and viewport actions. Installing this route enables those tools under the broker's normal write channel and unique request-ID rules. Administrators can review the generated files and restrict writes before registering manually. An allowlist for `apply_operations` covers its whole batch, including extension edits; it does not filter individual operations. App validation, document revisions, workspace restrictions, explicit overwrite and backups remain in force.

Closing or expiring a headless context closes its process and loses unsaved documents. Releasing a live context disconnects its proxy; it does not close FreeCAD or restore the model. Save explicitly before release. After an uncertain write, inspect the request receipt and actual model state; never replay the write automatically. Broker ownership does not fence GUI edits or direct clients.

## Extension discovery

Broker manifests add `--broker-catalog` to the normal MCP server command. The broker endpoint exposes the existing 24 tools unchanged plus the read-only `list_broker_capabilities` adapter. Direct connections retain exactly 24 tools.

The provider returns the broker's normalized version-1 catalog using installation files only. It does not start FreeCAD, import extension handlers, call the live bridge or access a model. Each entry points to the existing read-only `describe_capability` tool. Broker capability matches are discovery hints, never callable write routes.

An installation snapshot can differ from a backend's loaded generation. Acquire the backend and describe its capability to obtain the actual native schema and catalog revision before querying or editing. After updating code, call FreeCAD's `reload_extensions`, discover the native catalog again, then call broker `refresh_capabilities` for the owned context. Broker refresh only indexes metadata; it does not reload FreeCAD extensions. Live custom extension directories must also be configured through the generated startup macro.

The broker does not distribute application skills. The standalone plugin and direct interfaces remain available independently of this optional catalog adapter. Native GUI operation and real Codex plugin-browser installation require separate manual acceptance.
