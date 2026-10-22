# Application versioning

Every application checkpoint uses one fixed **YY.MMDD.HHmmss** timestamp in **America/New_York**. The current display identity is **26.1022.184257**, chosen at `2026-10-22T22:42:57Z` (`2026-10-22T18:42:57-04:00`). Both application packages carry identical checked-in `release.json` manifests. Builds and application startup read these files; they never calculate a new version from the current clock.

The backend, app-owned host, MCP `serverInfo`, native status, generated plugin, native skill metadata, installer selection records and manager reporting use that checkpoint. CLI commands `codex-freecad --version` and `freecad-mcp-host --version` exit before client creation, runtime verification or service startup.

## Display and package forms

The fully padded display form is retained for humans. Python package metadata, wheel filenames and strict numeric SemVer plugin/cache identities remove leading zeros from each component. Compare integer components rather than raw strings.

| Surface | Current checkpoint | Leading-zero example |
| --- | --- | --- |
| Human display, CLI, MCP serverInfo | `26.1022.184257` | `26.0101.000001` |
| PEP 440 / numeric SemVer package identity | `26.1022.184257` | `26.101.1` |
| Four-part assembly/file mapping | `26.1022.1842.57` | `26.101.0.1` |

This Python application has no .NET binaries. The four-part compatibility mapping is `YY.MMDD.HHmm.ss`, with numeric components below 65535; helper tests do not establish assembly loading or .NET runtime acceptance. A .NET consumer should retain the full display identity in product/informational metadata.

Framework `universal-codex-tools==0.20.0` and MCP `2.3.0` are independently reviewed dependency pins. They are unchanged by application stamping. Framework status retains its existing `version` field; application status adds `app_version` and `app_package_version`. Manager component values use canonical package identities, with the padded application version in its message. Plugin identity remains `freecad-modeling@freecad-development`.

## Choose a checkpoint explicitly

With development dependencies installed, supply one chosen UTC instant:

```powershell
.\.venv\Scripts\python.exe scripts\stamp_version.py --utc 2026-10-22T22:42:57Z
```

The command validates all targets before writing both manifests, both static project versions and skill metadata. It is a developer source edit, never a build hook. Review and commit the complete change. Repeating the same instant is idempotent. Windows development uses `tzdata` for the IANA timezone database; reading the fixed manifest requires only the standard library and no timezone lookup.

The two-digit year covers 2000–2099. The timestamp validates calendar dates and clock ranges. During the autumn DST transition local times repeat and move backward: the stamper rejects duplicate identities from different instants and backward version changes. Choose a later local checkpoint; retain existing artifacts and receipts unchanged. Do not rewrite history to match a new version.

## Verification and deployment

Focused tests cover padding, numeric ordering, valid dates, DST boundaries, four-part limits, package mirrors, portable native manifests and generated plugin metadata. Wheel auditing checks RECORD hashes, source bytes, canonical metadata and identical backend/host release manifests. Inspect/import built packages and run their `--version` commands before deployment.

Package and source checks do not establish native FreeCAD behavior, engineering MCP lifecycle acceptance or acceptance by Codex's plugin loader. Those require their own released runtime validation. Preserve prior runtimes, cache versions, installer receipts and recovery journals when installing an accepted checkpoint; keep machine-specific mappings and evidence in ignored local storage.
