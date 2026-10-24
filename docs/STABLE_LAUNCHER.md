# Stable standalone launch and recovery

The Windows installer retains FreeCAD's standalone MCP server, plugin and native
skill. The framework stays at **0.20.0** and the SDK at **2.3.0**. The optional
[CodexMCPBroker manager](https://github.com/votecoffee/CodexMCPBroker) is a separate
Windows application, not a broker route or a universal plugin. Launcher work does
not add framework features or broaden accepted native/GUI scope.

## Installed layout

The default per-user installation is `%USERPROFILE%\.local\share\FreeCADMCPServer`,
outside packaged Local AppData redirection:

```text
Start-Mcp.py                         stable stdlib-only entry
cwd/                                 stable working directory
launcher/current.json                atomic reviewed snapshot selection
launcher/snapshots/<sha>/manifest.json
launcher/backups/<prior-sha>.json     exact previous pointer bytes
runtimes/<release-generation>/runtime/
runtimes/<release-generation>/connection/plugin/
packages/                            retained hash-pinned wheels
installation.json                    last installer receipt
```

The host launches the reviewed paired **real `pythonw.exe -I -S -B`** and
`Start-Mcp.py`, with `cwd/` as its working directory. Neither its command nor its
script/cwd depends on a plugin cache, current source branch, virtual-environment
redirector or build directory. The entry executes the reviewed backend bootstrap
in the same surviving process; it adds no forwarding child or protocol pipe.

Ordinary startup reads only the explicit selection. Missing, malformed, linked,
reparse or changed metadata/payloads refuse startup. It never installs packages,
searches for a newest directory, changes profile, or falls back after refusal.
The retained bootstrap verifies the complete runtime closure before protocol use.
Reconstructed `None` streams retain the original inherited handles and UTF-8.
Startup diagnostics go to stderr, including early windowless refusal.

## Install and update

`Install.cmd` builds a clean committed checkout, verifies the application wheel's
sources against Git, checks dependency SHA-256 and wheel RECORD bytes, and copies
the complete closure into a new retained runtime. The Windows x64 Python 3.13
dependency lock is `src/codex_freecad/runtime-windows-py313.json`. It reuses supplied,
previously retained or app-owned wheels first; other missing wheels download only
at explicit installation and must match that lock. The custom framework wheel
must come from the reviewed framework build, not an unrelated package release.

Source text comparison follows Git's CRLF-to-LF normalization. Exact wheel/runtime
bytes retain their own hashes and RECORD verification; the installer records any
newline variations. Native acceptance reuse separately compares the relevant
retained domain bytes and policies rather than assuming text equivalence is runtime
acceptance.

The standalone plugin has one `freecad` route to the stable entry. Existing
checkout-bound registrations require a guarded migration; they are not removed
automatically. `-Integration none` prepares/selects an installation without
changing Codex. Plugin installation keeps the app-owned skills and uses the CLI;
the application never patches immutable Codex cache files.

`Run.cmd` uses the existing selection without setup or fetching. Workspace, mode
and native target changes belong to explicit installation, not per-run overrides.
The Start menu shortcut shows the **verified installed selection**, with running
health reported as **Not reporting** when no live observation is made. It does
not start a CAD application or present selection as backend health.

For administrator tooling, preparation and selection are separate:

```powershell
python -m codex_freecad.stable_install prepare --root C:\CadInstall `
  --runtime C:\ReviewedRuntime --workspace C:\CadModels `
  --native-target 'C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe'
python -m codex_freecad.stable_install select --root C:\CadInstall `
  --snapshot REVIEWED_SNAPSHOT_SHA256 --expected-selection PRIOR_POINTER_SHA256
```

Use `absent` only for a genuinely fresh pointer. Native is the default explicit
profile and requires its bound target; `--profile offline` prepares read-only
FCStd package inspection. Publication serializes cooperating writers, compares
the expected pointer hash, backs up exact old bytes, flushes the new bytes, and
replaces atomically. Interrupted or stale publication preserves the valid prior
selection. Failed preparations and previous runtimes stay available for review.

Already connected clients keep their original runtime, job, documents, leases and
receipt generation. A new connection follows the new selection through the same
host route. Management reports selected and running versions separately, and
marks a changed snapshot pending even if its display version is unchanged. A
changed selection is not proof that an already-open desktop chat reloaded it.

An upgrade from a prior native installation preserves its shared state/registry
in their retained original location while live peers exist. They are explicitly
recorded bindings, not copied fresh state to evade admission or recovery. Do not
delete that older directory because a newer backend is selected. Fresh installs
place state beneath the app-owned root. A later state relocation requires its own
quiescent, reviewed migration.

## Ownership and recovery

Four metadata frontends share the existing OS-owned admission locks. Native work
still acquires one shared lease lazily. Every actual root is its durable owner;
the early root job, independent pinned-parent watcher, original-pipe guard and
bounded EOF exit remain in effect. Parent observation does not share the thread
that may block behind a pipe reader. The retained job includes indirect children
and helpers; attached/user applications remain outside that job.

`process-generations/` records full process identities from bounded job samples,
including root and observed helpers. The primary suspended private worker is
durably bound and sampled before resume. Sampling is not a claim of a complete
kernel event history for arbitrarily short-lived helpers. Native process receipts
and operation uncertainty remain separate from lifecycle evidence.

Reconnect recovery preserves exact before-images and only retires a private claim
after its original owner, bound worker, members and retained generation actors
are all proven absent or replaced. Live or unverifiable peers, unbound intents,
cleanup receipts and legacy claims lacking generation evidence remain visible.
Departed attached/shared records only release the departed owner's reference;
they never authorize terminating the external application. No PID/name sweep,
limit increase, write replay, receipt acknowledgement or dirty-state inference is
part of recovery. Native recovery barriers and uncertain operation journals stay.

Windows image paths can differ between logical and physical/MSIX views. The app
first pins host, process creation and a live handle; aliases require OS file
identity. Equal names or copied executable bytes do not prove an alias. Failed
identity observations remain unknown and are reported. Alias-aware observations
do not broaden the framework's strict termination API.

## Validation boundary

Focused launch validation uses disposable caches and workspaces, real MCP
initialize/discovery/guidance/file-hash reads, exact process handles, EOF, failed
startup and retained-writer owner loss. Harmless Python/shell actors can exercise
the ownership layer without invoking FreeCAD or customer files. Source policy,
package checks and synthetic process evidence do not establish native geometry,
GUI dragging, shared-host or controller acceptance. Reuse retained native/domain
acceptance only when its relevant code/policy bytes remain unchanged. See
[validation](VALIDATION.md), [native modeling](NATIVE.md) and
[service management](SERVICE_MANAGEMENT.md).
