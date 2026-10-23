# Standalone native profile

This explicit candidate uses the existing shared FreeCAD engine and tools. A headless connection
owns one lazy FreeCADCmd worker; live mode attaches only to the explicitly pinned existing bridge.
Never launch a user GUI, choose another route after failure, or terminate an attached process.
The accepted offline plugin remains a separate installation until native pilot acceptance.

Read this guide, `get_workflow`, the current capability descriptions and `freecad_status` first.
Use `review_native_target` before opening an FCStd or choosing a save/export target. It reports
the exact workspace path and SHA-256, or `absent`, without opening a native document. Native FCStd
loading is trusted code execution, not a ZIP sandbox; the first pilot uses generated disposable
files only. Inspect documents and pass `expected_revision` to edits, import and Undo. Save/export
also compare the latest inspected document revision and the reviewed target bytes. A stale target
is refused again by the native engine. Explicit overwrite still preserves a byte-identical backup.

Create a named document, apply one atomic operations batch, inspect valid geometry, review a new
FCStd target, save, review a new STEP/BREP/STL target and export explicit final object names. Reopen
only after reviewing the saved source. Use the returned revision and source/output hashes as
evidence. Save headless work explicitly before disconnecting; unsaved owned documents are not
automatically persisted. Live/headless documents and Undo histories are independent.

Up to four metadata frontends can initialize and discover tools without activating FreeCAD. The
first native call reserves one shared native slot until that connection closes. Other native
calls return busy before dispatch; metadata remains usable and there is no waiting work queue.
Save work before closing the owning connection. Failed backend cleanup retains the lease;
process death releases its OS lock without reconciling uncertain native effects.
Each native connection allows one active request and no automatic replay. Mutations have durable
dispatched/reply-received/uncertain receipts.
Any ambiguous dispatch or failed receipt persistence disables further native work. A fresh client
also refuses unresolved receipts in the same state directory. Preserve the original files,
receipts and resource barriers for inspection; deleting state or restarting is not reconciliation.
Read-only inspection remains allowed if the original transport can still answer. A native error
after dispatch is conservatively uncertain in this candidate, even when the engine may have
rolled the batch back; no rollback or no-effects claim is inferred from an exception string.

The adapter owns its Windows job, exact child creation handles and ledger generation. Its four
process budget includes the root, native worker and possible runtime helpers; it is not a memory
cap. Worker launch is suspended until containment and durable identity binding precede execution.
EOF first closes the client/owned worker, manager and resource session; the hard exit is deferred.
Independent parent-death and pipe guards remain active. Attachment cleanup is detach-only.

Source/package checks and harmless process fixtures do not establish FreeCAD recompute, geometry,
native file validity, GUI behavior or installed Codex activation. Coordinate an isolated native
pilot before promoting this candidate. Shared-host, arbitrary Python, controller and SCM routes
are not part of this profile.
