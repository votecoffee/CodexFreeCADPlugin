# Project workflow

- Keep live FreeCAD editing and headless FreeCADCmd modeling equally supported through the shared engine.
- Commit tested, coherent increments frequently. The user performs the actual push to origin; do not push unless the user explicitly changes that instruction.
- Preserve input CAD files. Save/export inside the configured workspace and retain the existing explicit-overwrite/backup behavior.
- Keep native modeling code independent of host MCP/Pydantic dependencies. FreeCAD runs its bundled Python interpreter.
- Prefer native persistent features and dependencies. Do not introduce arbitrary Python execution endpoints.
- Verify meaningful geometry changes with native tests, including recompute, rollback and save/reopen where applicable. Use the isolated GUI smoke script for live behavior; do not modify an existing user FreeCAD session for testing.
- Run `.venv\Scripts\pytest.exe -q`, `.venv\Scripts\ruff.exe check src tests examples scripts` and `.venv\Scripts\ruff.exe format --check src tests examples scripts` before a release. Record limitations separately from observed test results.
- Update README, changelog and validation records for new capabilities. Package a committed, clean working tree and record its commit/hash evidence.
