# Standalone native preparation

The native profile uses the existing shared FreeCAD engine. It restores the modeling, assembly,
hole/fastener, engineering extension, recompute, save and export tools that the separate offline
ZIP/XML profile intentionally omits. It can attach to an explicitly selected existing live bridge;
it does not start or terminate a user GUI. Source and package preparation are not native acceptance.

## Prepare a candidate

Build a clean committed backend wheel and extract the reviewed exact backend, framework 0.20.0,
MCP 2.3.0 and other pinned dependencies into an immutable runtime, with wheel RECORD verification.
Use a fresh output directory and an existing disposable workspace:

```powershell
python -m codex_freecad.native_setup --workspace C:\CadPilot\models `
  --runtime C:\CadPilot\runtime --output C:\CadPilot\candidate `
  --native-target "C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe"
```

This reads/hashes the explicit executable; it does not run it. For a later opt-in live pilot, select
`--mode live --native-target C:\CadPilot\bridge.json`, using a reviewed bridge descriptor from an
already open, isolated GUI. Its backend must report the exact candidate package version. Never
reuse a user session for an automated test. Native Python has no MCP/Pydantic dependency.

The output contains a standalone plugin, native skill, fixed generated launcher and complete
runtime hash closure. Python uses the paired real `pythonw.exe -I -S -B`; no console redirector,
external Python path or shared-host hop is needed. Native worker extension directories are explicit
and empty by default, while bundled extension features remain available. Existing native skills,
receipts and offline installations stay in place. Generation performs no plugin installation.
The native entry is staged in the private worker generation: embedded Python can compile an entry
before executing it, so importing the package's worker file directly could create caches inside
the immutable runtime. The staged entry disables bytecode before importing backend code. Bytecode
environment policy and cache prefix are explicit; inherited host Python search/home/startup paths
are removed. The generated entry hash and backend worker hash remain in its bootstrap manifest.

## Dispatch and recovery

Read `get_native_workflow` and `get_workflow`, inspect schemas and the document, and retain its
revision. Use `review_native_target` before open/save/export; save/export also require the current
inspected document revision. The engine rechecks the source/output hash immediately before native
open or write preparation. New targets use the `absent` hash sentinel. Existing overwrite requires
explicit opt-in and keeps the existing byte-preserving backup. This is optimistic concurrency, not
a claim of atomic filesystem exclusion against unrelated writers throughout the native operation.

Mutations persist dispatched/reply-received/uncertain receipts. An unresolved receipt blocks new
mutations even in a new connection. Do not delete state, retry a write or manufacture a success
receipt. App-owned resource barriers remain separate from operation receipts: verifying that a
private process exited does not establish whether its last native write completed.
Read-only inspection is still permitted when the original transport responds. This first candidate
conservatively treats any post-dispatch error as uncertain, including native batch errors; it does
not infer a verified rollback from an error string. An explicit native recovery pilot must establish
the original result before resuming writes. Receipt inspection and state preservation are available;
automatic reconciliation or acknowledgement is deliberately absent.

Up to four metadata frontends can initialize, list tools, read guides and review file targets in
one state directory without reserving native capacity. The first native call acquires the same
single `native-pilot` lease used by earlier releases. A competing native call returns a busy error
before backend dispatch or receipt creation; it does not close that frontend or queue a retry.
The known native-capacity refusal uses the SDK's explicit tool-error path so the caller receives
the busy explanation. Other exceptions retain the SDK's error handling and redaction.
The owning connection retains its lease and native documents between calls. Save work and close
that connection to release capacity. Failed backend cleanup retains the lease; process death
releases its OS lock while existing process containment and uncertain receipts remain in force.
Do not create separate state roots to bypass the shared worker limit.

Each admitted native frontend permits one active request. Its root job limits the entire tree to
four processes and retains the independent parent-death and pipe guards. Each owned native worker
is assigned its private job and durably bound before resuming. The budget permits a worker and
runtime helpers, subject to actual pilot inspection; it is not a kernel memory cap. Closing an
attachment only releases its reference. Ordinary EOF defers process exit until native client,
manager and owner cleanup completes. Failed cleanup yields uncertain history and exit 1.

## Smallest useful coordinated pilot

After independent package review and a scheduled per-app native slot:

1. Use one isolated cached candidate connection, an empty disposable workspace and a pinned
   FreeCADCmd image. Capture root, worker and any helper creation handles, tree/job counts, loaded
   images, memory and the durable ledger. Preserve the accepted offline plugin unchanged.
2. Create a document and a simple parametric solid, inspect revision/validity/volume, change a
   dimension in one atomic batch, recompute, and verify the changed result. Reject an invalid batch
   and verify rollback through actual native inspection.
3. Review an absent FCStd target, save it, review an export target and export an explicit shape.
   Record artifact hashes; close/reopen the saved FCStd and verify dimensions and shape validity.
   Change a reviewed source/output externally and verify stale-hash rejection/backup preservation.
4. Exercise ordinary EOF, busy EOF, controlled private root/worker loss and retained-writer parent
   loss. Verify exact process generations, no surviving owned helpers, truthful manager/receipt
   state and preserved unknown effects. Do not terminate or reconcile foreign histories.
5. Only after acceptance, promote the explicit native profile. Defer isolated GUI parity testing
   until a separate opt-in live slot; retain the existing shared engine and tools for equal support.

No controller, customer project, user-native document or shared-host operation is part of this
pilot. Pure/stub tests and harmless Python process fixtures cover software contracts only. Real
FreeCAD geometry, loaded-module provenance and native lifecycle behavior still require the pilot.
