"""Read-only implementation boundaries; native/host acceptance remains separate."""


def feature_report(
    *, protocol_mode="legacy", watch_catalog=False, discovery_cache_ttl_seconds=0, app_host=True
):
    return {
        "schema_version": 1,
        "features": {
            "durable_resource_ownership": {
                "state": "blocked",
                "detail": "Awaiting the published shared ownership-ledger API. App-local jobs/handles are not durable recovery evidence. Shared last-owner cleanup and crash reconciliation are not accepted.",
            },
            "process_lifetime": {
                "state": "unassessed",
                "detail": "Source-only hardening: explicit host startup, eight frontend slots, Windows job ownership and EOF/parent-exit guards. Runtime process-tree/shutdown acceptance is pending.",
            },
            "runtime_guidance": {
                "state": "enabled-and-tested",
                "detail": "Hash-pinned get_workflow and references; data is not write approval.",
            },
            "mcp_skills": {
                "state": "enabled-and-tested" if app_host else "outside",
                "detail": "App-owned HTTP profile; stdio uses guide tools. Native Codex loading is unassessed.",
            },
            "catalog_watch": {
                "state": "enabled-and-tested" if watch_catalog else "blocked",
                "detail": "Explicit retained modern/auto profile only; legacy requires refresh.",
                "protocol_mode": protocol_mode,
            },
            "discovery_cache": {
                "state": "enabled-and-tested" if discovery_cache_ttl_seconds else "blocked",
                "detail": "Connection-scoped opt-in discovery; absent hints disable caching. Invocation rechecks policy/schema.",
                "ttl_seconds": discovery_cache_ttl_seconds,
            },
            "cad_progress": {
                "state": "enabled-and-tested",
                "detail": "Request dispatch/reply phases, not geometry percentages. Native/GUI acceptance is unassessed.",
            },
            "native_cancellation": {
                "state": "blocked",
                "detail": "Synchronous FreeCAD RPC/kernel calls have no native stop handshake. Queued cancellation can prevent dispatch; in-flight cancellation does not prove stop or rollback.",
            },
            "cad_tasks": {
                "state": "blocked",
                "detail": "No durable CAD job adapter, per-job document ownership or interrupted-outcome reconciliation. Generic routing is not Task-enabled.",
            },
            "approval_continuations": {
                "state": "outside",
                "detail": "Existing revision/overwrite/ownership safeguards remain. Metadata reads do not need new approval prompts.",
            },
            "cad_artifact_resources": {
                "state": "blocked",
                "detail": "Workspace exports/media remain ordinary tools. No owner-scoped immutable CAD artifact/receipt store authorizes resources yet.",
            },
            "tray_restart": {
                "state": "blocked",
                "detail": "No surviving supervisor fences every chat, unsaved models and unresolved effects.",
            },
            "remote_replicas_ui": {
                "state": "outside",
                "detail": "OAuth, Redis replicas and MCP Apps are not selected. One process owns retained native state.",
            },
        },
    }
