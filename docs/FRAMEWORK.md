# Experimental app-owned framework host

The architecture is a shared app framework with an independent Windows manager. FreeCAD owns its standalone Codex plugin, native skills, stable discovery/invocation interface, CAD backends and native validation. Plugin installation never depends on another app's plugin being present. There is no universal Codex plugin, aggregated skill installer or universal MCP connection. The framework is an implementation dependency of this app-owned host; its retained `universal-codex-tools` distribution and `universal_tools` import names do not imply a universal plugin deployment. Initial normal setup uses direct endpoints; framework installation is an explicit choice.

## Install the app-owned host

From a clean committed checkout, run normal setup, then select the framework host with a verified local artifact:

```powershell
.\scripts\Setup.ps1
.\scripts\Install-Framework.ps1 -FrameworkWheel C:\Packages\universal_codex_tools-0.20.0-py3-none-any.whl -FrameworkSha256 TRUSTED_SHA256
```

The installer checks the supplied hash before installing anything, builds both application wheels, verifies source bytes and wheel RECORDs, and installs normal dependencies into a separate runtime in ignored `.local/framework/runtimes/`. It reads installed package bytes back against all three audited wheels. It initializes dedicated app state, starts only the FreeCAD host, backs up the previous local Codex config and FreeCAD plugin cache, and replaces `freecad-modeling@freecad-development`. Other plugins are not selected or removed. No CAD document or GUI is opened. Native/GUI and Codex UI acceptance remain separate from installation and transport discovery.

The installed plugin runs `freecad_mcp_host ... connect`. This command requires an explicitly started app-owned host, authenticates to it and checks its identity. Opening a chat does not start or restart it. Local administrator commands `start`, `status` and `stop` use the same `--state` and `--publication` arguments. Explicit concurrent starts share one host using an OS-owned startup lock. Startup preserves ownership/recovery journals; occupied ports and mismatched state fail without fallback or terminating other processes. Plain `proxy` also requires a running server. Lifecycle hardening is source-only pending process-tree acceptance; see [management status](SERVICE_MANAGEMENT.md#process-lifetime-hardening).

An explicit selection marker makes subsequent `Setup.ps1`, `Install-CodexPlugin.ps1` and the root launcher retain this standalone connection. The root launcher exposes the shared host's live/headless discovery rather than selecting a private backend with `-Mode`. A damaged marker or missing runtime fails without reverting to direct tools. The Start menu shortcut uses the same selection. Normal setup reinstalls the selected plugin; it does not replace its immutable backend publication. A different workspace, native executable or extension set requires an explicit publication update.

For a deliberate host/framework upgrade, quiesce other callers, save and release retained contexts, then repeat the installer with `-Upgrade` and the new trusted wheel/hash. It prepares and audits a separate runtime before stopping the old host. A local activation step holds the proxy startup lock across shutdown, publication and healthy replacement startup; waiting chat proxies cannot relaunch the prior host in that interval. Read-only journal checks reject retained/lost contexts, orphan reservations and unresolved write receipts before shutdown and again afterward. It preserves the workspace, native executable, frozen external extensions, protocol choice, dedicated state and original receipts. It never acknowledges an uncertain outcome, retries native effects or switches to another connection. This is a maintenance operation; its startup fence is not native-work admission fencing for already connected clients. Ordinary backend updates can still use publication, save/release and `refresh_services` below.

The new runtime must pass `doctor` before plugin replacement. Local admin commands `doctor` and `check-idle` use the same `--state` and `--publication` arguments; neither calls native CAD tools. Old runtimes, selection/publication/plugin files and stopped journal backups remain under ignored `.local/framework/backups/`. Failure preserves these for deliberate inspection rather than automatically restoring/replaying work. Do not restore the entire Codex config over unrelated later changes. A host runtime change requires frontend reconnection; existing native sessions are not migrated. Starting a new Codex chat loads the updated plugin configuration.

The owning host also provides [cached tray reporting](SERVICE_MANAGEMENT.md) using framework 0.18's management endpoint. Backend dispatch still uses the original `ApplicationBackend` ownership and routing implementation, with an operation counter around CAD-facing requests. Tray restart stays disabled; this reporting interface does not add safe supervision to explicit installer maintenance. No duplicate manager, universal plugin or unrelated extension is installed.

**Source target: framework 0.20.0 and MCP 2.3.0 throughout. Protocol/native acceptance for this target is pending.** The framework uses `MCPServer`, typed pagination and snake_case Python fields with wire aliases. SDK 1.x compatibility is not required. Legacy publications retain the negotiated `2025-11-25` handshake. Explicit `auto` and `2026-07-28` candidates are assessed with disposable providers, including modern frontend ownership through independent stdio proxies. Framework support for SDK 2.2 does not establish this app's acceptance of a different version than its exact MCP 2.3 pin.

## Packages and SDK boundary

| Package | Environment | Pinned dependency |
| --- | --- | --- |
| `codex-freecad` | CAD MCP backend | `mcp==2.3.0` |
| `freecad-mcp-host` | App-owned host | `universal-codex-tools==0.20.0`, `mcp==2.3.0` |
| Native FreeCAD engine | FreeCAD's bundled Python | Native FreeCAD modules; no host MCP/Pydantic imports |

The host imports `universal_tools.framework` from a normal exact package dependency. The framework pin and `framework-host/requirements.lock` are updated together from the MCP 2.3 baseline. Use normal pip installation with a verified wheel or an explicit editable framework checkout for coordinated development. No framework source is copied into this project, no Git submodule is used, and no public package feed or native .NET binding is assumed. A separate app-owned environment keeps deployment/rollback independent even though both host and backend now use MCP 2.3.

Create a separate environment and install the host with a verified framework wheel available in a chosen wheel directory:

```powershell
py -3.13 -m venv .local\framework-runtime
.\.local\framework-runtime\Scripts\python.exe -m pip install C:\Packages\VerifiedWheels\universal_codex_tools-0.20.0-py3-none-any.whl -r framework-host\requirements.lock -e . -e framework-host
.\.local\framework-runtime\Scripts\python.exe -m pip check
```

For a release, build/install the host wheel instead of the editable host. Verify wheel hashes and RECORD entries against the intended package source before installation. Build wheels from a clean committed tree:

```powershell
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist framework-host
```

The wheel auditor checks trusted framework hash, wheel RECORD entries, exact normal dependency pins, MCP 2.3 requirements and application code/resource bytes against this checkout:

```powershell
.\.venv\Scripts\python.exe scripts\verify_framework_wheels.py --backend-wheel dist\codex_freecad-26.1022.173620-py3-none-any.whl --host-wheel dist\freecad_mcp_host-26.1022.173620-py3-none-any.whl --framework-wheel C:\Packages\VerifiedWheels\framework.whl --framework-sha256 EXPECTED_SHA256
```

Both application wheels carry the same fixed release manifest. The auditor checks its display/package identities against wheel metadata and source project versions. See [versioning](VERSIONING.md). Older or mismatched framework artifacts are rejected before installation. Unit fixtures for this audit do not establish that an actual updated framework artifact exists.

Run the auditor from the same source tree used for the build. A Git source export can normalize text line endings differently from an existing Windows working copy; compare wheels built from that export with the exported source, without weakening byte checks. Install the trusted framework wheel by explicit file path to avoid assuming a package-feed release.

## Generate a candidate

After normal backend setup, publish to a separate ignored candidate directory:

```powershell
.\.venv\Scripts\python.exe -m codex_freecad.framework_setup --workspace models --host-python .local\framework-runtime\Scripts\python.exe --output .local\framework-candidate
```

This copies the application package and optional installed extension roots into an immutable deployment, writes a version-1 `application.json` and generates FreeCAD's own plugin/marketplace. It does not start a host or native engine, install a plugin, update an existing registration, change runtime pointers or open a CAD file. Existing direct setup remains available through `codex_freecad.setup`. Never reuse a universal broker state directory for this app host.

`--protocol-mode legacy` is the default and leaves the publication's new protocol options unset. An explicit `--protocol-mode auto` negotiates modern discovery or a legacy handshake; `--protocol-mode 2026-07-28` requires modern discovery. These are local administrator publication choices, never model tool arguments. Changing this option binds a new backend revision while retaining its native resource identity. Quiesce/save and release an existing context before replacing its backend. Unsupported protocol values fail before writing a candidate.

The stdio proxy generates its own internal frontend affinity identity. Caller `clientInfo`, model arguments and a shared identifier cannot authenticate independent chats. This remains affinity inside the host's authenticated local-user deployment; separate-user authentication requires an assessed application adapter. No model-facing ownership or approval-mode parameters are added.

Add `--modern-discovery` only with an explicit `auto` or `2026-07-28` publication to select retained catalog watching and bounded, private discovery caching. The TTL is two seconds; absent hints disable SDK caching. Catalog notifications invalidate discovery, and invocation still rechecks current policy/schema. The normal installer preserves the selected profile, including legacy with watching/caching disabled. See [runtime feature acceptance and limitations](RUNTIME_FEATURES.md).

The host now composes a real `SkillCatalog` from the same guide snapshot used by `get_workflow`. Skills-over-MCP is available on its authenticated HTTP endpoint; the standalone stdio proxy uses ordinary guide tools and does not advertise a Skills relay. Native Codex skill imports remain static submission snapshots. Guide-only publication is explicit and does not execute extension code or change native state. Tasks, CAD artifact resources, advanced approval adapters, OAuth, Redis and MCP Apps remain unselected for the concrete reasons in the feature report. CAD operations remain synchronous atomic operations.

Framework 0.17 also supplies authorized task notifications, explicit protocol resource/prompt relays, MCP Apps composition, OAuth/DPoP profiles and optional Redis-backed native SDK replicas. These remain unselected here. FreeCAD has no durable CAD job adapter, remote credential/principal adapter, resource federation policy or assessed host iframe. Its retained native workers, journals and reservations require one owning process. Redis is not installed. The app keeps its local authenticated host, explicit backend ownership, stable standalone plugin and exact MCP 2.3 pin; upstream SDK 2.2 interoperability does not change that pin or establish native acceptance.

App-host backend publications explicitly cap argument structure at depth 64 and 100,000 nodes, alongside the existing 8 MiB byte budget. The framework checks structure before schema validation, write claims or provider dispatch. Rejected batches are returned whole: no splitting, truncation, automatic retry or route fallback is performed. These input limits do not constrain native document size or establish geometry validity.

The output prints explicit host commands. For the default candidate:

```powershell
.\.local\framework-runtime\Scripts\python.exe -m freecad_mcp_host --state .local\framework-candidate\state --publication .local\framework-candidate\application.json init --port 8891
.\.local\framework-runtime\Scripts\python.exe -m freecad_mcp_host --state .local\framework-candidate\state --publication .local\framework-candidate\application.json serve
```

The candidate plugin's plain stdio proxy connects to this authenticated loopback application host. Start a candidate host explicitly; it never starts a universal daemon. The original direct standalone plugin works independently of this candidate. Generating files does not activate them. The explicit installer above selects an app-owned `connect` command and the existing standalone marketplace identity. Native skill changes require a plugin update and Codex reload.

## Stable interface and publications

The app-owned MCP front door has the framework's fourteen tools. Its exclusive `freecad-live` and `freecad-headless` backends retain documents and Undo across dependent calls. Search and describe tools, acquire the selected backend, read its `get_workflow` guidance, then invoke the existing domain handlers through that retained context. The direct interface has 25 tools. Direct and hosted backends share the read-only workflow reader. Framework backends add `list_host_capabilities`, an installation-only catalog that never imports extension handlers or contacts FreeCAD. Native operations and responses are not reimplemented in the framework host.

Deployment revisions bind the complete captured application/extension file closure and backend configuration. The framework pins the launcher artifact; the launcher independently verifies the closure manifest, every captured file and the file set before importing the backend. Changed source creates a new deployment; existing deployments are never overwritten. Native FreeCAD, installed MCP dependencies and external native add-ons remain separate dependency boundaries, not covered by that code/resource hash.

Publishing updates only the desired application definition. On the same connected front door, finish/save work, release the affected backend and call `refresh_services`. A retained context defers replacement. Invalid candidates retain the working generation. Failed/uncertain writes and lost contexts block replacement pending explicit app-admin reconciliation; there is no automatic acknowledgment or cross-route retry. A release discards unsaved headless documents. Save and reopen an explicit FCStd file when moving to a new headless generation. Live backend replacement does not reload the separately running FreeCAD bridge.

Routine extension reload still uses the existing `reload_extensions` operation. Built-in published code and captured extension roots are immutable; new code needs a new publication. Live bridge extension roots remain configured by its own startup macro and must match the intended native generation. Host catalog metadata does not prove that a live bridge has loaded that generation.

## Validation and remaining gaps

Host tests cover publication immutability, complete captured closure checks, standalone package generation and separation of SDK dependencies. The opt-in isolated framework profile substitutes a disposable provider beneath the original CAD MCP handlers and uses real stdio/HTTP framework transports. It checks direct versus hosted schemas/results/media, independent frontend ownership, revisions/Undo, write receipts, failed publication/recovery, same-session refresh and a lost-reply recovery barrier after restart. It records five warm direct/host inspection samples; each host sample includes describing the tool and invoking it. These are not pure transport overhead or native latency acceptance. See [validation commands](VALIDATION.md#app-owned-framework-host). Keep per-run captures and latency samples in ignored `local/` or `work/`.

Actual FreeCAD GUI behavior, native generation migration, real Codex plugin activation, reconnect/reload acceptance and full direct/host latency criteria remain separate acceptance work. Serialized backend calls can delay other calls on that same backend; this prototype does not add app-owned jobs or parallel private contexts.

No chat-approval-mode adapter exists. Model arguments cannot select Full access, Approve for me or Ask for approval, override app safeguards or reconcile an uncertain write. Framework policy, document revisions, explicit workspace/overwrite protections and original-file backups retain their existing roles. Native skills or front-door schemas require plugin update and Codex reload even when backend publication keeps the front-door connection alive.
