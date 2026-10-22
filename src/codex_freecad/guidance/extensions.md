# Extension workflow

Read `references/extension-index.json` with its returned workflow revision and SHA-256 when installed feature hints are needed. It is generated from app-owned publication metadata without importing handlers. It can differ from the live bridge or active native generation.

Call `list_capabilities`, then `describe_capability` for the selected capability. Use current exact arguments and native `catalog_revision`. Read-only features use `run_query`; edits use an `extension` operation inside the atomic `apply_operations` batch, with explicit document and inspected document revision. Metadata and guide content do not authorize edits.

Routine installed feature updates use `reload_extensions`, followed by native capability discovery. Refresh host capability hints separately. Failed reloads retain the prior working generation; do not claim new functionality loaded without readback.

Captured backend code/extension roots are immutable. New code requires an explicit backend publication and refresh after saving/releasing affected work. Source-file edits alone do not update a worker. Live backend replacement does not reload the separately running GUI bridge. Guide-only publication uses a separate data snapshot and does not replace native workers or Undo histories.
