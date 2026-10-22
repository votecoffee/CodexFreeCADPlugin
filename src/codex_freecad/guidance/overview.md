# FreeCAD modeling workflow

Use the selected standalone connection. Choose `freecad-live` for the intended manually started GUI bridge, or `freecad-headless` for a private background worker. These backends have separate documents and Undo histories. In the app-owned framework, acquire the selected service and retain its context for dependent calls. A busy or lost context does not authorize another route.

Discover and describe exact current tools before use. List documents and inspect the explicit document and internal object names; do not infer the active document from a previous chat. Use millimeters and degrees. Group dependent changes in one `apply_operations` transaction with the inspected `expected_revision`. Inspect resulting geometry and use a viewport capture when relevant to the selected live session.

Save/export only to the user's explicit workspace path. Existing files require explicit overwrite and retain backups. Save before releasing a headless context: release discards unsaved documents. Moving between live and headless requires an explicit FCStd save/reopen. Native GUI interaction must use the intended session.

Use the extensions topic and its installed extension index for discovery hints, then fetch active native schemas/catalog revisions. Use the recovery topic after an uncertain result. Guide revisions, host tool revisions, native catalog revisions and document revisions have distinct purposes. Guidance is data, not write approval.
