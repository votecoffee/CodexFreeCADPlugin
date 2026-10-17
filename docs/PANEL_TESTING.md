# Codex CAD panel and coupled gearbox

The new dock provides source-parameter editing, persistent joint couplings, playback, viewport dragging, BREP interference checks and sampled-pose navigation. The saved gearbox has four coupling rules: carrier = sun/4; each planet relative to the carrier = -3*sun/4. Driving the carrier also drives the sun through the inverse ratio. Its 15 linked components retain the editable native sources and 26 solid instances.

## Try the portable demo

1. Extract the entire ZIP into a writable folder. Keep `native` beside the model and macro.
2. Open FreeCAD 1.0.2. Run `OpenCoupledGearbox.FCMacro` through **Macro → Macros → Execute**. This opens the model and the Codex CAD dock in Motion mode, with dragging enabled. The FCStd alone does not open the panel.
3. Drag near the outside of the sun gear or a carrier arm. The sun, carrier and planets should move together. A grounded housing/base stays fixed. Release keeps the pose; Escape cancels; **Model → Undo last edit** restores the complete drag.
4. Alternatively, select `SunJoint`, enter 90 and click **Apply position**. `CarrierJoint` should read 22.5 degrees and each `PlanetJoint` should read -67.5 degrees relative to the carrier. The **Play** button advances the selected joint using Step per frame; Pause stops it.
5. In Checks, select two or more linked components in the tree to narrow the check. **Check current pose** separates overlap, contact and insufficient clearance. **Check motion range** evaluates discrete positions on a hidden copy, preserving your source pose and Undo. Choose a sample and click **Move to selected sample** to inspect it. Editing the model invalidates previous samples. Selecting a result highlights the pair.
6. Select a component and use **Model → Edit linked source parameters** to edit an unbound source dimension. Expression-driven or managed fields remain protected. Source edits update linked shapes; connector locations are explicit and do not automatically relocate to a changed hole.

Use the **Codex CAD** toolbar button to reopen a closed dock. The portable macro starts local tools; chat connection is an explicit button and requires the MCP server to use the same workspace. No API key or host Python package is needed for these local panel controls.

Couplings are native saved data interpreted by the Codex CAD controller and chat engine. Use **Drag parts in viewport** for coupled dragging; the standard Assembly workbench's separate drag mode does not enforce these saved ratios. Revolute dragging needs a view with the joint axis facing you; sliders need a side view. A camera alignment that cannot determine motion is rejected with a status message. The viewport callback and physical mouse gesture require manual GUI verification.

## Manual panel checks

From PowerShell in the repository root:

```powershell
.venv\Scripts\python.exe scripts\smoke_panel.py --interactive
```

This creates its own FreeCAD window/configuration and a small blue rotary arm with an orange sliding tool. It first checks panel coupling creation/removal, a source dimension edit and Undo, sampling/navigation, connection controls and callback registration. It prints a fresh `work\panel-smoke\<run>` folder. Then drag the blue arm near its outer end: rotating it 60 degrees should move the orange slider to 11 mm (`extension = 0.15*angle + 2`). Drag only within the arm's -135..135 degree limits and the tool's 0..25 mm limits. Escape should restore the starting pose, and Undo should restore the last complete drag. Closing this test window or pressing Ctrl+C in its PowerShell window ends the isolated run.

The automated headless tests cover the drag controller's native math, forward/inverse coupling, wrap crossing, transaction isolation, cancellation and Undo. They do not prove that a physical mouse click/pick/event sequence works. Record panel GUI and physical-drag results separately from automated headless results. The demo verification JSON records the actual headless geometry and save/reopen results. Discrete collision samples do not prove continuous collision-free travel, physical gear contact or load capacity.

## Extension reload check (v0.8)

The current isolated harness also updates its own test extension and reloads through the shared engine. It checks that the native dock is replaced, playback pauses, selectors and the native pose/revision remain intact, and the existing bridge instance and credential bytes are preserved. It then holds the arm for manual dragging checks. These GUI results must be recorded on the target installation. For routine updates after the initial v0.8 migration, use the dock's **Reload extensions** button or the generated `ReloadExtensions.FCMacro`; see [EXTENSIONS.md](EXTENSIONS.md) for the stable MCP workflow.
