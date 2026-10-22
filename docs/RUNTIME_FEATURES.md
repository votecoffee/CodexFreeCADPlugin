# Runtime guides and feature boundaries

The packaged `freecad-modeling` skill is a small bootstrap. It directs clients to discover `get_workflow`, acquire the intended service when hosted, and read current guidance before modeling. The canonical topics are `overview`, `extensions` and `recovery`. Generated references include installed extension hints and a read-only feature report. These are data and never grant engineering write approval.

## Read current guidance

Call `get_workflow` with `topic: "overview"`. The result contains a snapshot revision, content SHA-256 and a reference inventory. Read a listed reference by passing its `reference`, `expected_revision` and `expected_sha256`. A stale revision, changed hash or unknown reference fails; rediscover before continuing. Guide revisions, host tool catalog revisions, native extension catalog revisions and document revisions are separate identities.

The app-owned HTTP `/mcp` endpoint also implements `skills/list`, `skills/get` and `resources/read` using one nonempty framework `SkillCatalog`. It serves the exact same resource bytes as ordinary guide reads. Use a compatible Skills client, the local host's authentication and the returned resource manifests. The standalone stdio connection continues to use ordinary tools. It does not advertise Skills forwarding.

[OpenAI plugin skill imports](https://developers.openai.com/plugins/build/skills) are submission snapshots, not runtime fetching by Codex's native skill loader. Install/reload once when changing the packaged bootstrap or plugin metadata. This project does not claim native Codex activation of live protocol skills.

## Publish guide-only changes

An administrator can stage trusted local Markdown/JSON guidance while the host remains connected:

```powershell
python -m codex_freecad.workflows --publication .local/framework/application.json --source-package PATH_TO_REVIEWED_CODEX_FREECAD_PACKAGE --expected-revision CURRENT_GUIDE_REVISION
```

Use the installed runtime's Python. Omitting `--source-package` rebuilds from the current immutable backend publication. The source package supplies `standalone_skill.md` and `guidance/*.md`; the command generates extension/feature references from the selected publication. It writes a candidate under `guidance/desired.json`, without native dispatch. Read `guidance/result.json` for applied/rejected status and verify the new revision through the connected client. Filesystem edits alone do not publish.

The owner validates the entire candidate, expected revision, bounded resource inventory and skill metadata before switching either view. New/changed/removed references appear together, with a Skills resource notification. Invalid candidates preserve the prior guide. Packages are immutable by content revision. The selected guide survives host restart for the same source publication; a changed source publication initializes its own canonical guide. Guide-only publication preserves retained model state, backend PID, ownership and Undo. It cannot add tool schemas or reload native extension code.

## Accepted profiles and blocked features

`doctor` returns `feature_report` without contacting FreeCAD. The same report is discoverable as `references/features.json`. The 0.20 source target reports protocol features as implemented but unassessed until its MCP profiles are rerun. Earlier protocol evidence used the previous pin. Native geometry, GUI gestures and native Codex skill loading are separate acceptance layers.

| Feature | Selected behavior and evidence boundary |
| --- | --- |
| Process/resource ownership | Source-only and unassessed: bounded frontend leases, owner/worker jobs, suspended native launch, creation identities and detach-only live attachments. Pure stubs cannot establish native cleanup. |
| Durable ownership recovery | 0.20 reservations/bindings and protected attachments/references are integrated in source. Complete SDK-launcher registration, shared draining and native recovery remain blocked/unaccepted. No automatic cleanup based on sampled lease counts. |
| Runtime guidance and HTTP Skills | Shared SHA-256 bytes, connected-client add/update/remove, stale reads and failed-candidate preservation tested with disposable CAD providers. |
| Modern catalog watching | Explicit `--modern-discovery` with `auto`/modern only. A retained CAD backend publishes a changed tool list; an already connected client discovers it from a notification. Legacy remains the default. |
| Discovery cache | Private, bounded two-second hints. Three warm tool-list reads require one server roundtrip in the SDK fixture instead of three; a second connection has its own cache, and change notifications invalidate it. This measures discovery roundtrips, not native CAD speed. |
| CAD progress | `apply_operations` reports queued, dispatch and reply stages when requested. There is no fabricated geometry percentage. The returned `execution` status supplies a fallback when progress notifications are unavailable or coalesced. |
| Native cancellation | Blocked: no FreeCAD RPC/kernel stop handshake. A pre-dispatch cancellation checkpoint can prevent an effect. Once dispatched, a request may complete after caller cancellation; inspect receipts and model state before another write. Cancellation is not rollback. |
| Durable CAD Tasks | Blocked: no durable native job adapter, per-job document ownership or interrupted-job reconciliation. Generic routing does not advertise Tasks. |
| CAD artifact resources | Blocked: no owner-scoped immutable CAD artifact/receipt store. Existing exports and media tools retain their normal workspace/overwrite rules. Workflow resources contain guidance only. |
| Approval continuations | Outside current scope: document revisions, ownership, explicit overwrite and recovery safeguards remain authoritative. Metadata reads add no approval prompts. |
| Tray restart | Blocked: no surviving supervisor fences all callers, unsaved documents and uncertain writes. Explicit idle maintenance uses the installer startup fence. |
| Redis/OAuth/Apps | Outside the selected local profile. A single owning process retains CAD state. |

Protocol cancellation tests record both a cancelled queued request with zero provider effects and an in-flight synchronous provider effect after client cancellation. They do not establish native kernel interruption. Lost replies retain the original uncertain-write barrier; automatic retries and acknowledgment are unchanged.
