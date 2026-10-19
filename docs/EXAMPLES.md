# Examples and demonstrations

Run these commands from the repository root after [setup](../README.md#install). Use a fresh output name or folder for each run. Most examples default to headless FreeCADCmd; commands that launch a GUI are identified below.

## Mounting plate

```powershell
.\.venv\Scripts\python.exe examples\direct_client.py
```

This creates `models\PlateDemo.FCStd` and `models\PlateDemo.step`. It refuses to overwrite existing output files; use a new `--name` on subsequent runs. Add `--mode live` to run the same example in the connected FreeCAD window.

## Edge finishing

`python examples\finish_plate.py --workspace models --name FinishedDemo` demonstrates topology-selected corner fillets, a chamfered hole, FCStd/STEP output and STEP reimport. Use the project's `.venv\Scripts\python.exe`; add `--mode live` to use the open FreeCAD window.

## Turned flange and patterns

`python examples\turned_flange.py --workspace models --name TurnedDemo` creates a constrained profile, revolved flange, six patterned bolt holes and a three-instance row, with native volume checks and FCStd/STEP output. It also supports `--mode live`.

## Parametric loft and mirror

`python examples\parametric_transition.py --workspace models --name ParametricDemo` creates two fully constrained circular profiles driven by named parameters, a native loft and its mirror. It verifies the two-solid analytic volume, saves FCStd/STEP and supports `--mode live`. Its disconnected boolean union keeps both solids in one final feature without joining material across the gap.

## Sweeps and helices

`python examples\swept_parts.py --workspace models --name SweptDemo` creates a hollow pipe elbow and a four-turn helical solid, driven by named section radii and coil height. It checks the two-solid analytic volume within 1e-5 relative tolerance and saves FCStd/STEP. Add `--mode live` for the open FreeCAD backend.

## Cutaway planetary gearbox demo (opens a GUI)

```powershell
.\.venv\Scripts\python.exe scripts\build_planetary_demo.py --workspace models\PlanetaryDemo
```

This creates an editable colored FreeCAD assembly, colored STEP export, exploded FreeCAD presentation and three native viewport previews. It uses 18-tooth sun/planet gears, three planets at a 36 mm orbit radius, a 54-tooth internal ring, a front-quarter cutaway, a three-arm carrier, coaxial shafts, washers and socket-head fasteners: 26 solid instances over a 152 mm base plate. Native PartDesign involute profiles remain editable in the feature history. The shared modeling engine creates the downstream sweeps, booleans, chamfer, patterns and expressions.

The runner starts its own isolated FreeCADCmd and GUI processes, leaving existing user sessions alone. It needs the built-in PartDesign gear utility included with the validated FreeCAD 1.0.2 installation. Use a new workspace for rebuilding; `--render-only` restyles/renders an existing generated model. Native errors are captured in the workspace's `.runtime` directory rather than relying on FreeCAD's exit code alone.

Open `PlanetaryGearbox-Showcase.FCStd` for the editable model. Its `Design` object controls gear width, housing height and cutaway angle. The exploded file contains presentation snapshots with separated component placements; it is a static layout rather than a motion-constrained assembly. Gear-profile creation and presentation styling use FreeCAD's installed native APIs in this example; they are not new generic MCP operations.

`codex_freecad.client.HeadlessClient` and `LiveClient` are also application APIs for your own code. See `examples\direct_client.py` and `examples\mounting_plate.json`.

## Hardware demo

Build editable holes, a flange, bolts, nuts and washers using FreeCADCmd only:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_hardware.py --workspace work\hardware-demo
```

The new output folder contains FCStd/STEP models and a native verification report. See [HOLES_FASTENERS.md](HOLES_FASTENERS.md) for capability arguments and editing behavior.

## Movable and coupled assemblies

[examples/movable_arm.py](../examples/movable_arm.py) demonstrates a rotary arm and sliding tool using either backend. From an existing static gearbox generated above, build a jointed model and playback controls:

```powershell
.\.venv\Scripts\python.exe scripts\build_movable_demo.py --source models\PlanetaryDemo\PlanetaryGearbox.FCStd --workspace models\MovablePlanetary
```

Then add saved ratios and the native panel launcher without opening a GUI:

```powershell
.\.venv\Scripts\python.exe scripts\build_coupled_demo.py --source models\MovablePlanetary\PlanetaryGearbox-Movable.FCStd --workspace models\CoupledPlanetary
```

The coupled builder uses FreeCADCmd only. The movable builder renders animation frames through an isolated GUI. Open the generated macros manually for playback and viewport dragging. Keep the adjacent `native` folder with the portable macros. See [assembly semantics](TOOLS.md#movable-assemblies) and [panel checks](PANEL_TESTING.md).

## BOM, thickness studies and dimensioned drawings

```powershell
.\.venv\Scripts\python.exe examples\engineering_plate.py --workspace work\engineering-demo
```

This creates an editable drilled plate, a three-instance linked row, a native BOM spreadsheet, frozen 4/6/8 mm thickness variants and a native TechDraw sheet. Independent formulas check the drilled plate volume at every sampled thickness. Outputs include FCStd, STEP, a dimensioned SVG, BOM CSV, study JSON and an artifact-hash verification report.

The default run uses FreeCADCmd and opens no GUI. Add `--mode live` with the connected bridge's workspace to use an existing FreeCAD window. Choose a fresh `--name` for repeat runs; existing output files are preserved. [Engineering capabilities](ENGINEERING.md) describe refresh rules and limits. The sheet supplies overall extents; it does not specify manufacturing tolerances or hole-location/diameter dimensions.

## Optional OpenAI Responses API example

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api]'
# Set OPENAI_API_KEY in this process using your normal local secret-management workflow.
.\.venv\Scripts\python.exe examples\api_agent.py --model YOUR_MODEL --prompt 'Create a 40 mm cube and save Cube.FCStd'
```

The app-managed tool loop passes schemas obtained from the same MCP server to the Responses API and routes model requests back through the same validation. It includes the 23 text-result tools; viewport images are available through MCP directly. It uses the model you name, makes paid API calls when run, and has a bounded tool loop. API schema/result conversion has a local test; paid API execution is not covered by the local test suite.
