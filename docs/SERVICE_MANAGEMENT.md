# Tray service reporting

## Standalone stable profile

Normal installation uses the [app-owned stable entry](STABLE_LAUNCHER.md), framework
0.20.0 and SDK 2.3.0. Each surviving standalone frontend registers its actual owner
generation. Native management reports the MCP frontend, held native lease and
whether its backend was validated; metadata availability does not prove CAD health.
Unresolved or unreadable native receipt history reports degraded and blocks new
writes before native admission. Receipt metadata reads are bounded to 256 records
and 256 KiB per record; invalid history remains unknown and requires inspection.
Selected/running versions and snapshots remain separate during an immutable update.
The installed-status shortcut verifies selection and reports **Not reporting** for
unobserved running health.

Sixteen metadata frontends, each initially limited to 128 MiB committed memory,
and one lazy native lease share retained state. Four legacy frontend leases remain
separate and untouched during an update. Native admission restores the previous
CAD memory policy before dispatch; it never changes the native process bound. The
native root job has an actual four-process bound; offline roots permit one process.
Job status reads the OS limit rather than reporting the inventory array's capacity.
Generation observations include root and retained job members, including observed
indirect actors. Dead-claim reconciliation preserves exact before-images and only
releases proven departed claims; native barriers/receipts, live or unknown peers,
unbound intents and legacy claims lacking generation evidence remain protected.
See [connection readiness](CONNECTION_READINESS.md) for aggregate and transition budgets.

Tray restart stays disabled: a per-frontend supervisor is not a cross-chat restart
coordinator with dirty-document and uncertain-operation approval. Native/GUI/shared
host acceptance remains separate from launch/process fixtures. The sections below
describe the **experimental framework host and its historical acceptance limits**;
their eight/32-process budgets are not the normal standalone native profile.

The app-owned framework host registers with the optional Windows MCP Service Manager through framework 0.20.0. It retains FreeCAD's standalone plugin and connection; it does not register with a universal broker. Install the shared manager separately once if wanted. FreeCAD setup never installs or launches another manager.

Only the owning host registers. Chat proxies and CAD backend workers do not create service rows. The canonical plugin association is `freecad-modeling@freecad-development`; each host process receives a fresh random instance ID. The framework uses the Windows user's Local AppData known folder and the private `CodexMCPManager/Registry` directory, independently of host-specific `LOCALAPPDATA` overrides. `--management-registry PATH` selects a separate registry for isolated tests.

## Reported state

The status callback returns a thread-safe cached snapshot. A background collector reads the host's cached catalog, local package/installer metadata and read-only ownership/write journals. It never acquires an engineering context, opens a CAD document, inspects an existing FreeCAD GUI or contacts a controller. CAD-facing calls update a shared operation counter, including completion, exceptions and cancellation. Retained contexts report busy even between calls; lost contexts or unresolved effects report degraded. A stale or failed collector reports degraded rather than claiming current native state.

Components include the app adapter, host, standalone plugin, framework and MCP SDK. Installed and running package versions remain distinct. The plugin's installed version is the last version verified by the installer against Codex's read-only inventory; its running native skill version is unknown. Available versions come only from audited local installer artifacts. Missing availability stays unknown, and an update is flagged only when those numeric versions establish a newer available artifact. These are not checks of GitHub, a package feed or the FreeCAD desktop version.

The manager uses authenticated loopback status and private registrations. Public snapshots omit tokens and control endpoints. Runtime files, registrations, journals and installation-specific captures belong outside public Git.

## Restart limitation

Tray restart is disabled. FreeCAD currently has no shared restart coordinator that atomically fences every chat, verifies unsaved documents and Undo history, handles pending reviews/jobs and reconciles uncertain native effects. The reporting adapter returns a specific blocked reason and performs no restart effect. An idle request counter or an empty ownership journal does not establish that an unrelated FreeCAD GUI is saved or restartable.

Explicit host maintenance remains available through the [framework upgrade workflow](FRAMEWORK.md#install-the-app-owned-host), with its separate idle/journal checks and preservation rules. The tray never invokes that installer, closes a FreeCAD GUI, guesses a launch command or kills a PID. A crashed/unreachable host cannot be restarted through this reporting endpoint.

Framework restart intents remain durable and app-scoped across instances. Duplicate IDs return receipts; changed payloads are rejected; uncertain outcomes retain their barrier. The app does not automatically reconcile or clear management or CAD journals.

## Verification

### Process lifetime hardening

Source hardening after the 0.1.5 host removes implicit host startup from `connect`. Only explicit administrator `start`/`serve` or an explicitly requested installer activation may launch the owner. There is one state-locked HTTP owner; app frontends have eight OS-locked slots per state, and direct frontends have eight per workspace. Slot release never clears CAD ownership journals or uncertain receipts.

Windows owners establish non-inheritable Job Object handles before starting workers, with kill-on-owner-exit and bounded descendant counts (32 for the host, eight for a stdio adapter). Existing external FreeCAD GUIs are outside those jobs. Stdio adapters pin a parent process handle and duplicate the input pipe solely for non-consuming EOF observation. Disconnect allows ten seconds for SDK cleanup before forced owner exit; no native stop/rollback is inferred. Once the SDK returns from cleanup, the CLI explicitly exits rather than waiting for orphan reader threads. The SDK's normal lifespan cleanup remains primary.

These changes are **source-only and unassessed at runtime**. Pure slot/observer/failure-path checks do not prove Windows Job Object nesting, abrupt termination, SDK EOF behavior, native subprocess cleanup, unsaved-model preservation or successful installation. Run isolated process-tree/shutdown tests in a dedicated management registry only after runtime validation is authorized. Non-Windows process-tree protection is not implemented. Tray restart remains disabled.

Native FreeCADCmd workers use a separate exclusive job. A worker is created suspended, its retained process handle and creation FILETIME are captured, and assignment succeeds before its initial thread resumes. Thread ownership/creation is rechecked before resume. Normal close, startup failure and timeout cleanup address those retained handles. Closing the worker job also contains inherited child processes; no process-name scan or PID-only termination is used. Reader cleanup is bounded, and an incomplete cleanup disables the session instead of starting another worker. The live bridge remains an external attachment whose close action only detaches.

Containment covers inherited process creation, including app-owned shell/Node wrappers. WMI/COM services or native APIs that launch outside that tree require explicit ownership/cleanup adapters and are not accepted by this implementation. App launchers request no new console; unrelated console hosts and user processes are not cleanup targets.

`freecad_status` includes native worker or attachment ownership. The host's cached `broker_status`/doctor data includes verified membership of its own job and sampled frontend leases; tray text identifies lease count and the external-GUI policy. These observations do not inspect dirty native documents. The source follows Microsoft's [Job Object process inheritance](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) and [suspended process creation](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags) contracts; actual behavior still requires isolated acceptance.

Framework 0.20's `ResourceLedger`/`ResourceOwner` now back native launch reservations, exact process binding before resume, protected GUI attachments and shared frontend references. The owner is the actual surviving Python host/adapter or API process. Native records are report-only, with conservative recovery barriers; verified OS process exit can retire a claim while preserving its barrier and reconciliation evidence. It does not reconcile a CAD write or establish that dirty model state was saved. The native FreeCAD startup probe stays standard-library-only and does not create a host-framework dependency inside FreeCAD.

The background `ResourceOwner.launch()` helper is not used for pipe-based workers: it does not inherit streams. FreeCAD retains its existing pipe transport and app-owned job/EOF guards, using `begin_launch()` and `bind_process()` before native execution. The resource registry is explicit in private host publications; an isolated host refuses a publication whose backends would use another registry. Direct APIs can supply `resource_registry`; managed CLI runtimes need the reviewed framework package (the backend declares a `managed` extra).

**Deployment remains blocked on complete SDK-launcher registration, shared last-owner admission/drain fencing and native recovery acceptance.** SDK-created MCP processes/indirect wrappers still need a reservation/registration hook owned by the app supervisor; a sampled job inventory is not a complete durable launch history. HTTP clients must participate in the same shared admission policy before last-client shutdown can be safe. Do not automatically stop a shared owner using only sampled frontend counts, release another chat's context, acknowledge uncertain writes or close an attached GUI. The existing CAD ownership/write journals remain authoritative. Native report-only/barrier records must not be promoted to manager termination simply because the framework supports it.

The shared manager can reject discovery when its bounded registry contains too many instance records. A verified app endpoint can still be healthy in that case. Do not raise the cap or remove another app's records implicitly; inspect and reconcile stale registrations through owner administration, retaining journals and unresolved outcomes.

The opt-in framework suite includes private real-HTTP management checks for cached status/version reporting, concurrent CAD-call counting and cancellation, busy/stale denial, blocked production restart receipts, random instance identities and clean shutdown. Synthetic supervisors separately exercise duplicate requests, independently recorded fake effects, lost receipts and a subprocess crash followed by a replacement instance. They never restart FreeCAD. Existing protocol profiles check unchanged front-door schemas, ownership, Undo, publications, media and uncertain-write recovery with disposable providers.

See [validation commands](VALIDATION.md#app-owned-framework-host). Actual tray rendering and a real native-service restart remain separate acceptance work. Reporting a live endpoint does not establish Codex skill activation or native CAD correctness.
