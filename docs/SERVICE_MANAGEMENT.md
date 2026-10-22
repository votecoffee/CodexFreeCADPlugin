# Tray service reporting

The app-owned framework host registers with the optional Windows MCP Service Manager through framework 0.18.0. It retains FreeCAD's standalone plugin and connection; it does not register with a universal broker. Install the shared manager separately once if wanted. FreeCAD setup never installs or launches another manager.

Only the owning host registers. Chat proxies and CAD backend workers do not create service rows. The canonical plugin association is `freecad-modeling@freecad-development`; each host process receives a fresh random instance ID. The framework uses the Windows user's Local AppData known folder and the private `CodexMCPManager/Registry` directory, independently of host-specific `LOCALAPPDATA` overrides. `--management-registry PATH` selects a separate registry for isolated tests.

## Reported state

The status callback returns a thread-safe cached snapshot. A background collector reads the host's cached catalog, local package/installer metadata and read-only ownership/write journals. It never acquires an engineering context, opens a CAD document, inspects an existing FreeCAD GUI or contacts a controller. CAD-facing calls update a shared operation counter, including completion, exceptions and cancellation. Retained contexts report busy even between calls; lost contexts or unresolved effects report degraded. A stale or failed collector reports degraded rather than claiming current native state.

Components include the app adapter, host, standalone plugin, framework and MCP SDK. Installed and running package versions remain distinct. The plugin's installed version is the last version verified by the installer against Codex's read-only inventory; its running native skill version is unknown. Available versions come only from audited local installer artifacts. Missing availability stays unknown, and an update is flagged only when those numeric versions establish a newer available artifact. These are not checks of GitHub, a package feed or the FreeCAD desktop version.

The manager uses authenticated loopback status and private registrations. Public snapshots omit tokens and control endpoints. Runtime files, registrations, journals and installation-specific captures belong outside public Git.

## Restart limitation

Tray restart is disabled. FreeCAD currently has no surviving app-owned supervisor that atomically fences every chat, verifies unsaved documents and Undo history, handles pending reviews/jobs and reconciles uncertain native effects. The reporting adapter returns a specific blocked reason and performs no restart effect. An idle request counter or an empty ownership journal does not establish that an unrelated FreeCAD GUI is saved or restartable.

Explicit host maintenance remains available through the [framework upgrade workflow](FRAMEWORK.md#install-the-app-owned-host), with its separate idle/journal checks and preservation rules. The tray never invokes that installer, closes a FreeCAD GUI, guesses a launch command or kills a PID. A crashed/unreachable host cannot be restarted through this reporting endpoint.

Framework restart intents remain durable and app-scoped across instances. Duplicate IDs return receipts; changed payloads are rejected; uncertain outcomes retain their barrier. The app does not automatically reconcile or clear management or CAD journals.

## Verification

The opt-in framework suite includes private real-HTTP management checks for cached status/version reporting, concurrent CAD-call counting and cancellation, busy/stale denial, blocked production restart receipts, random instance identities and clean shutdown. Synthetic supervisors separately exercise duplicate requests, independently recorded fake effects, lost receipts and a subprocess crash followed by a replacement instance. They never restart FreeCAD. Existing protocol profiles check unchanged front-door schemas, ownership, Undo, publications, media and uncertain-write recovery with disposable providers.

See [validation commands](VALIDATION.md#app-owned-framework-host). Actual tray rendering and a real native-service restart remain separate acceptance work. Reporting a live endpoint does not establish Codex skill activation or native CAD correctness.
