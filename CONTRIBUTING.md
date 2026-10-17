# Contributing to FreeCADMCPServer

Use [GitHub issues](https://github.com/votecoffee/FreeCADMCPServer/issues) for questions, reproducible bugs and feature proposals. For a change, describe the resulting behavior and relevant validation in a pull request.

## Set up and check changes

Follow [README installation](README.md#install), then run the commands in its [Development section](README.md#development). Native modeling tests require FreeCADCmd; identify skipped native checks explicitly. Run appropriate geometry, recompute, rollback and save/reopen checks for modeling changes. GUI and physical mouse behavior need separate [manual validation](docs/PANEL_TESTING.md).

Keep live and headless support in the shared engine. Native FreeCAD code must remain independent of the host MCP/Pydantic dependencies. Add routine CAD features through the [extension interface](docs/EXTENSIONS.md), preserving fixed MCP schemas and native persisted objects. See [AGENTS.md](AGENTS.md) for implementation conventions.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/codex_freecad/` | Shared engine, transports, schemas and installed extensions |
| `tests/` | Host, native and MCP regressions |
| `examples/` | Reusable sample scripts and operation payloads |
| `scripts/` | Setup, registration, smoke checks and release tooling |
| `docs/` | Public architecture, feature guides, validation procedures and changelog |
| `.agents/plugins/` | Portable marketplace metadata |
| `local/` (ignored) | Private notes, machine-specific records and local handoffs |
| `.local/` (ignored) | Generated installation configuration and FreeCAD macros |
| `models/`, `work/` (ignored) | CAD outputs, scratch files and raw validation reports |
| `.venv/`, `build/`, `dist/` (ignored) | Environment and build outputs |

## Keep public content reusable

- Keep personal usage instructions, workstation paths, conversation transcripts, customer models and raw local test reports outside tracked files. Use `local/` or a directory outside the checkout.
- Keep credentials and generated bridge state local. Do not commit `.env`, `.env.*` secret files or generated installation configuration. A sanitized `.env.example` may be tracked if needed.
- Use repository-relative commands and generic placeholders in documentation. Public examples must contain redistributable inputs and clear output paths.
- Preserve original CAD inputs. Save outputs into a configured workspace and retain explicit overwrite/backup behavior.
- Before committing, inspect `git status --short`, `git diff --check`, `git diff --cached` and any new files. Verify local files with `git check-ignore -v -- local/notes/example.md`. Ignore rules do not untrack files already committed; move or remove those files from the index before committing.
- Treat release assets as public too. Inspect generated guides, native reports, JUnit XML, screenshots and model metadata for machine paths or private content before sharing. Raw local reports may contain absolute paths even when the source tree is clean.

Do not rewrite published Git history as routine cleanup. If a secret is exposed, revoke it and coordinate remediation with the maintainer.

## Documentation and releases

Keep the root README focused on installation, usage and navigation, following [Standard Readme](https://github.com/RichardLitt/standard-readme). Put detailed feature documentation in `docs/` and runnable demonstrations in `examples/` or `scripts/`. Update the changelog for public behavior changes; keep session logs and per-machine results local.

Before a release, run the full test suite and Ruff checks, build from a clean committed tree, and inspect the release artifacts. Record the source commit, hashes, environment and actual validation scope in the release evidence. GUI checks, API calls and plugin installation must not be inferred from headless tests. Release packaging instructions are in [VALIDATION.md](docs/VALIDATION.md#release-packaging).
