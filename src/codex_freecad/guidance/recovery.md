# Uncertain outcomes and recovery

Never replay an uncertain write. Inspect its original request receipt and actual app state before another mutation. A new request ID, backend revision, alternate connection or repeated approval does not reconcile the old outcome. Keep the original receipt and revision evidence.

Lost-context and failed-write barriers require explicit app-admin reconciliation after independently verifying the native outcome. Do not acknowledge, clear, release/reacquire or restore a context to bypass those barriers. A normal app error is distinct from a lost reply; neither proves that no partial effect occurred.

Save and release a healthy context before replacing its backend publication. Release loses unsaved headless documents. Live release disconnects its proxy; it does not restore CAD state. GUI documents and Undo history remain separate from headless histories. Stop when ownership or outcome is unresolved rather than guessing a safe retry.

The tray reports status only and cannot safely restart this app. Explicit host maintenance has its own idle/journal guards and startup fence; it does not authorize closing an unsaved FreeCAD GUI. Workflow and skill publication never grants execution permissions or changes native approval requirements.
