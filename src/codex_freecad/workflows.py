"""Small app-owned workflow reader; guidance is data, never authorization or executable code."""

GUIDES = {
    "overview": (
        "Choose freecad-live for the manually started GUI bridge or freecad-headless for a private "
        "background worker. Acquire that service and retain its context_id. Inspect explicit document "
        "and object IDs, then group dependent edits atomically with the inspected expected_revision. "
        "Discover extension schemas before use. Save explicitly before release. This workflow uses "
        "the app-owned host alone; the Universal Tools plugin is optional."
    ),
    "extensions": (
        "list_capabilities and describe_capability return the active native catalog revision. "
        "run_query accepts read-only capabilities; apply_operations accepts extension edits in its "
        "atomic transaction. reload_extensions loads trusted installed extensions without changing "
        "the fixed backend schemas. Refresh host capability metadata separately. Installation hints "
        "may differ from the active native generation."
    ),
    "recovery": (
        "Never replay an uncertain write. Inspect its original request receipt and actual app state. "
        "Lost-context and failed-write barriers require explicit app-admin reconciliation. A new "
        "request ID, backend revision or alternate route does not reconcile the old outcome. Saving "
        "and releasing a healthy context is required before backend publication; release loses "
        "unsaved headless documents. Live release disconnects the proxy and does not restore CAD."
    ),
}


def describe_workflow(topic="overview"):
    if topic not in GUIDES:
        raise ValueError("Unknown FreeCAD workflow topic")
    return {"schema_version": 1, "topic": topic, "guidance": GUIDES[topic]}
