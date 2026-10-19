---
name: freecad-modeling
description: Inspect and edit FreeCAD models through this application's direct or experimental framework connection, including live and headless workflows.
---

Use one explicitly selected FreeCAD connection for the workflow. Live and headless backends have separate documents and Undo histories. Do not switch connections or replay a write after an uncertain outcome.

For the experimental app framework front door, search for `get_workflow`, describe the returned native tool, acquire the selected FreeCAD service and read its `overview` topic through `call_read_tool`. Retain that context for dependent calls. Search and describe current domain tools before invoking them. Writes require unique request IDs; document revisions and extension catalog revisions remain separate from host tool revisions.

For the direct plugin, use its existing FreeCAD tools. Inspect the named document before edits; use internal object names, millimeters and degrees. Group dependent edits into one atomic batch and pass the inspected revision. Discover extension schemas with `list_capabilities` and `describe_capability` before use.

Save or export only to an explicit workspace path. Existing files require explicit overwrite and retain backups. After a lost reply, inspect the original receipt and model state; no automatic retries or fallback routes. Save before releasing a headless context because its unsaved documents close with the worker. Native GUI actions require the user's intended FreeCAD session and remain separate from headless validation.

Framework use does not require the Universal Tools plugin. If the user selected the optional broker connection, use that connection's current discovery and ownership workflow instead. Neither this skill nor model-supplied approval-mode arguments waive app safeguards. Native skill/schema updates require plugin update and Codex reload; backend catalog refresh does not reload this skill.
