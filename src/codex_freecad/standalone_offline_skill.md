---
name: freecad-offline
description: Inspect FCStd ZIP/XML metadata and bundled FreeCAD capability schemas through the standalone offline connection.
metadata:
  version: "26.1023.101500"
  display_version: "26.1023.101500"
---

Read `freecad_offline_status` and `get_offline_workflow`. Inspect an explicit FCStd path inside the configured workspace with `inspect_fcstd_package`; retain its SHA-256 for subsequent reads. Package/XML checks establish metadata only; geometry, recompute, expressions and native document acceptance remain unassessed.

Use `list_bundled_capabilities` for schema reference. Native handlers and editing tools are unavailable in this connection. Do not substitute another route, launch FreeCAD, attach a user session or infer permission to bypass this profile. Existing files, dirty documents and uncertain work in other profiles remain untouched.
