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
| `.local/` (ignored) | Private validation, coordination, legacy retained bindings and preparation records |
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

The shared framework and separate Windows management app live in
[CodexMCPBroker](https://github.com/votecoffee/CodexMCPBroker). Keep FreeCAD's standalone server,
plugin and skills independently usable; shared dependencies do not add a universal plugin.

Use byte reads for TOML preflight so universal-newline conversion cannot hide malformed CR.
Generate TOML with `toml_io.encode_toml` and `write_bytes`; it emits explicit CRLF on Windows
without double translation. Validate Unicode/multiline values, exact LF/CRLF bytes and unrelated
settings in disposable fixtures. When editing an existing file, pass its original `source_bytes`
to preserve its BOM, and retain whether a final newline was present. Do not test publication
against a developer's live Codex config.
Normal plugin registration delegates to the Codex CLI with an explicit `CODEX_HOME` when testing.

Root `Install.cmd`, `Run.cmd` and `Install-and-Run.cmd` share `scripts/InstallAndRun.ps1`.
Production connections use the app-owned [stable entry/cwd and retained runtime](docs/STABLE_LAUNCHER.md),
independent of this checkout and disposable plugin caches. Keep the framework at its reviewed
pin; the optional manager and application server remain independently installed. Do not publish
source-bound preview configurations or patch immutable Codex caches. Installer and running
version observations must remain separate, including active peers during a pointer update.
The opt-in `tests/test_launchers.py` uses copied launchers and a sentinel PowerShell target to
exercise argument forwarding, quoted paths and nonzero exit propagation. Real-launcher checks
use help or invalid arguments that return before setup; they do not install or start FreeCAD.

Keep the root README focused on installation, usage and navigation, following [Standard Readme](https://github.com/RichardLitt/standard-readme). Put detailed feature documentation in `docs/` and runnable demonstrations in `examples/` or `scripts/`. Update the changelog for public behavior changes; keep session logs and per-machine results local.

Before a release, run the full test suite and Ruff checks, build from a clean committed tree, and inspect the release artifacts. Record the source commit, hashes, environment and actual validation scope in the release evidence. GUI checks, API calls and plugin installation must not be inferred from headless tests. Release packaging instructions are in [VALIDATION.md](docs/VALIDATION.md#release-packaging).
