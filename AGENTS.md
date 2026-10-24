# Project workflow

- Keep live FreeCAD editing and headless FreeCADCmd modeling equally supported through the shared engine.
- Commit tested, coherent increments. Do not push without explicit authorization.
- Preserve input CAD files. Save/export inside the configured workspace and retain the existing explicit-overwrite/backup behavior.
- Keep native modeling code independent of host MCP/Pydantic dependencies. FreeCAD runs its bundled Python interpreter.
- Treat simultaneous open chats as normal demand. Follow `docs/CONNECTION_READINESS.md` for measured connection/commit/request budgets, real saved-route cold SDK discovery, original-handle EOF/owner-loss proof, preservation of live peers and separate host/native acceptance. Package tests or a two-client fixture alone do not establish availability.
- Add new CAD features through the installed extension registry and stable extension envelope; avoid changing MCP tool schemas for routine features. Extension imports must be side-effect free, handlers must honor query/edit roles, and saved features must use persistent native objects rather than generation-owned Python proxies.
- Verify reloads through one persistent MCP connection, including schema stability, backend PID, source/Undo preservation and failed-update recovery. Keep GUI testing opt-in and record manual checks separately.
- Prefer native persistent features and dependencies. Do not introduce arbitrary Python execution endpoints.
- Verify meaningful geometry changes with native tests, including recompute, rollback and save/reopen where applicable. Use the isolated GUI smoke script for live behavior; do not modify an existing user FreeCAD session for testing.
- Run `.venv\Scripts\pytest.exe -q`, `.venv\Scripts\ruff.exe check src tests examples scripts` and `.venv\Scripts\ruff.exe format --check src tests examples scripts` before a release. Record limitations separately from observed test results.
- Update the root README, public feature guides and changelog for new capabilities. Keep personal usage notes, workstation paths, raw reports and handoffs outside tracked files; use ignored `local/`, `work/` or `models/`. Store generated installation configuration in ignored `.local/`. Inspect staged content before committing. Package a committed, clean working tree and record its commit/hash evidence.
