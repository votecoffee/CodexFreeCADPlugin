# Feature roadmap

These priorities build on the shared live/headless engine, reloadable capabilities, native geometry and source-preserving previews. The table distinguishes available features from proposed work.

| Priority | Workflow | Status and intended result |
| --- | --- | --- |
| 1 | Saved design requirements | Available in the current checkout. Store explicit fit, envelope, property, volume and mass limits; evaluate previews and reject a batch with a final enforcement operation. See [engineering requirements](ENGINEERING.md#saved-design-requirements). |
| 2 | Tolerance and fit studies | Proposed. Vary several dimensions over explicit ranges and report clearance, interference and requirement failures on isolated copies. Identify sampled configurations and sampling limits; do not label sampled extrema as a proven worst case. |
| 3 | Geometry selection by intent | Proposed. Resolve a face, edge or hole by geometry, position, direction and dimensions. Bind selections to revisions and reject ambiguous matches. |
| 4 | Visual change reports | Proposed. Show added/removed material in separate colors, with before/after geometry, requirement changes and source revisions. Retain native snapshots for review without changing the source design. |
| 5 | Reproducible design history | Proposed. Keep workspace-local structured edit records, reasons, input hashes and verification evidence so a change can be reviewed and replayed. Exclude credentials and workstation-specific paths from portable reports. |

Community projects already provide valuable inspection, regression, CAM and engineering tools; for example, [blwfish's tool reference](https://github.com/blwfish/freecad-mcp/blob/main/TOOLS.md) includes fixture comparison and an inspector, while [TESSA's reference](https://github.com/tessalabs-space/freecad-mcp/blob/main/docs/TOOL_REFERENCE.md) covers parametric studies and analysis preparation. This project focuses on connecting its capabilities through reproducible previews, explicit requirements and transactional edits.
