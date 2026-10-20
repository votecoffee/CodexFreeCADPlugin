# Experimental app-owned framework host

The shared app framework is the primary development direction. FreeCAD owns its standalone Codex plugin, stable discovery/invocation interface, CAD backends and native validation. The framework is an implementation dependency of this app-owned host. It does not add a central plugin, broker registration or automatic route selection. Normal standalone setup does not activate this prototype.

**Current baseline: framework 0.14.0 and MCP 2.3.0 throughout.** The framework uses `MCPServer`, typed pagination and snake_case Python fields with wire aliases. SDK 1.x compatibility is not required. This application's isolated profile uses the negotiated `2025-11-25` handshake; modern discovery/cache and multi-round-trip protocol workflows are not claimed. Framework support for SDK 2.2 does not establish this app's acceptance of a different version than its exact MCP 2.3 pin.

## Packages and SDK boundary

| Package | Environment | Pinned dependency |
| --- | --- | --- |
| `codex-freecad` | CAD MCP backend | `mcp==2.3.0` |
| `freecad-mcp-host` | App-owned host | `universal-codex-tools==0.14.0`, `mcp==2.3.0` |
| Native FreeCAD engine | FreeCAD's bundled Python | Native FreeCAD modules; no host MCP/Pydantic imports |

The host imports `universal_tools.framework` from a normal exact package dependency. The framework pin and `framework-host/requirements.lock` are updated together from the MCP 2.3 baseline. Use normal pip installation with a verified wheel or an explicit editable framework checkout for coordinated development. No framework source is copied into this project, no Git submodule is used, and no public package feed or native .NET binding is assumed. A separate app-owned environment keeps deployment/rollback independent even though both host and backend now use MCP 2.3.

Create a separate environment and install the host with a verified framework wheel available in a chosen wheel directory:

```powershell
py -3.13 -m venv .local\framework-runtime
.\.local\framework-runtime\Scripts\python.exe -m pip install C:\Packages\VerifiedWheels\universal_codex_tools-0.14.0-py3-none-any.whl -r framework-host\requirements.lock -e framework-host
.\.local\framework-runtime\Scripts\python.exe -m pip check
```

For a release, build/install the host wheel instead of the editable host. Verify wheel hashes and RECORD entries against the intended package source before installation. Build wheels from a clean committed tree:

```powershell
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist framework-host
```

The wheel auditor checks trusted framework hash, wheel RECORD entries, exact normal dependency pins, MCP 2.3 requirements and application code/resource bytes against this checkout:

```powershell
.\.venv\Scripts\python.exe scripts\verify_framework_wheels.py --backend-wheel dist\codex_freecad-0.9.0-py3-none-any.whl --host-wheel dist\freecad_mcp_host-0.1.0-py3-none-any.whl --framework-wheel C:\Packages\VerifiedWheels\framework.whl --framework-sha256 EXPECTED_SHA256
```

The old framework artifact is rejected before installation. Unit fixtures for this audit do not establish that an actual updated framework artifact exists.

Run the auditor from the same source tree used for the build. A Git source export can normalize text line endings differently from an existing Windows working copy; compare wheels built from that export with the exported source, without weakening byte checks. Install the trusted framework wheel by explicit file path to avoid assuming a package-feed release.

## Generate a candidate

After normal backend setup, publish to a separate ignored candidate directory:

```powershell
.\.venv\Scripts\python.exe -m codex_freecad.framework_setup --workspace models --host-python .local\framework-runtime\Scripts\python.exe --output .local\framework-candidate
```

This copies the application package and optional installed extension roots into an immutable deployment, writes a version-1 `application.json` and generates FreeCAD's own plugin/marketplace. It does not start a host or native engine, install a plugin, update an existing registration, change runtime pointers or open a CAD file. Existing direct setup remains available through `codex_freecad.setup`. Never reuse a universal broker state directory for this app host.

The output prints explicit host commands. For the default candidate:

```powershell
.\.local\framework-runtime\Scripts\python.exe -m freecad_mcp_host --state .local\framework-candidate\state --publication .local\framework-candidate\application.json init --port 8891
.\.local\framework-runtime\Scripts\python.exe -m freecad_mcp_host --state .local\framework-candidate\state --publication .local\framework-candidate\application.json serve
```

The standalone plugin's stdio proxy connects to this authenticated loopback application host. Start the app host explicitly; the proxy never auto-starts a universal daemon. The original direct standalone plugin works independently of this candidate. Installing or selecting the experimental plugin is a separately authorized pilot; generating files does not activate them. Its native skill changes require a plugin update and Codex reload.

## Stable interface and publications

The app-owned MCP front door has the framework's fourteen tools. Its exclusive `freecad-live` and `freecad-headless` backends retain documents and Undo across dependent calls. Search and describe tools, acquire the selected backend, read its `get_workflow` guidance, then invoke the existing domain handlers through that retained context. The direct interface retains 24 tools. Framework backends add the read-only workflow reader and `list_host_capabilities`, an installation-only catalog that never imports extension handlers or contacts FreeCAD. Native operations and responses are not reimplemented in the framework host.

Deployment revisions bind the complete captured application/extension file closure and backend configuration. The framework pins the launcher artifact; the launcher independently verifies the closure manifest, every captured file and the file set before importing the backend. Changed source creates a new deployment; existing deployments are never overwritten. Native FreeCAD, installed MCP dependencies and external native add-ons remain separate dependency boundaries, not covered by that code/resource hash.

Publishing updates only the desired application definition. On the same connected front door, finish/save work, release the affected backend and call `refresh_services`. A retained context defers replacement. Invalid candidates retain the working generation. Failed/uncertain writes and lost contexts block replacement pending explicit app-admin reconciliation; there is no automatic acknowledgment or cross-route retry. A release discards unsaved headless documents. Save and reopen an explicit FCStd file when moving to a new headless generation. Live backend replacement does not reload the separately running FreeCAD bridge.

Routine extension reload still uses the existing `reload_extensions` operation. Built-in published code and captured extension roots are immutable; new code needs a new publication. Live bridge extension roots remain configured by its own startup macro and must match the intended native generation. Host catalog metadata does not prove that a live bridge has loaded that generation.

## Validation and remaining gaps

Host tests cover publication immutability, complete captured closure checks, standalone package generation and separation of SDK dependencies. The opt-in isolated framework profile substitutes a disposable provider beneath the original CAD MCP handlers and uses real stdio/HTTP framework transports. It checks direct versus hosted schemas/results/media, independent frontend ownership, revisions/Undo, write receipts, failed publication/recovery, same-session refresh and a lost-reply recovery barrier after restart. It records five warm direct/host inspection samples; each host sample includes describing the tool and invoking it. These are not pure transport overhead or native latency acceptance. See [validation commands](VALIDATION.md#app-owned-framework-host). Keep per-run captures and latency samples in ignored `local/` or `work/`.

Actual FreeCAD GUI behavior, native generation migration, real Codex plugin activation, reconnect/reload acceptance and full direct/host latency criteria remain separate acceptance work. Serialized backend calls can delay other calls on that same backend; this prototype does not add app-owned jobs or parallel private contexts.

No chat-approval-mode adapter exists. Model arguments cannot select Full access, Approve for me or Ask for approval, override app safeguards or reconcile an uncertain write. Framework policy, document revisions, explicit workspace/overwrite protections and original-file backups retain their existing roles. Native skills or front-door schemas require plugin update and Codex reload even when backend publication keeps the front-door connection alive.
