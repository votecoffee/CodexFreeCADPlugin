"""MCP stdio entry point. All stdout belongs to the MCP SDK."""

import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.types import ImageContent, ToolAnnotations
from pydantic import Field

from . import __version__
from .client import HeadlessClient, LiveClient
from .schemas import Edit

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
EDIT = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)


def create_server(client):
    @asynccontextmanager
    async def lifespan(server):
        try:
            yield
        finally:
            client.close()

    server = MCPServer(
        "FreeCAD",
        version=__version__,
        lifespan=lifespan,
        instructions="Inspect the document and dimensions before editing. Use internal object names, "
        "millimeters and degrees. Pass the inspected revision into edits to detect manual changes. "
        "Group dependent operations into one atomic batch. Inspect result geometry and capture the "
        "live view to verify. Save only to an explicit workspace path. Never retry an ambiguous "
        "timeout write without inspecting the model. Live and headless servers own separate sessions.",
    )

    @server.tool(annotations=READ)
    def freecad_status() -> dict:
        """Check FreeCAD version, backend, workspace, documents and supported operations."""
        return client.call("status")

    @server.tool(annotations=READ)
    def list_documents() -> list[dict]:
        """List documents open in this backend. Live and background sessions are independent."""
        return client.call("list_documents")

    @server.tool(annotations=WRITE)
    def new_document(name: str, label: str | None = None) -> dict:
        """Create an unsaved document with a unique internal name; no file is written."""
        return client.call("new_document", name=name, label=label)

    @server.tool(annotations=WRITE)
    def open_document(path: str) -> dict:
        """Open a trusted FCStd file inside the CAD workspace, preserving its bytes until saved."""
        return client.call("open_document", path=path)

    @server.tool(annotations=READ)
    def inspect_document(document: str) -> dict:
        """Read the feature tree, validity, bounds in mm, volume in mm^3 and current revision."""
        return client.call("inspect_document", document=document)

    @server.tool(annotations=READ)
    def inspect_object(document: str, object_name: str) -> dict:
        """Read an object's type, parameters, dependencies, constraints and shape measurements."""
        return client.call("inspect_object", document=document, object_name=object_name)

    @server.tool(annotations=READ)
    def inspect_assembly(document: str, assembly: str) -> dict:
        """Read native assembly components, grounding, local joint frames, positions and limits.

        Use create_assembly/add_component/ground_component/create_joint to assemble solids.
        Revolute joints rotate about local +Z in degrees; sliders translate along +Z in mm.
        Use set_joint_positions for one or several coordinated absolute joint coordinates.
        Returned angles wrap to [-180, 180]. Positioning does not check interference or dynamics.
        """
        return client.call("inspect_assembly", document=document, assembly=assembly)

    @server.tool(annotations=READ)
    def check_interference(
        document: str,
        objects: Annotated[list[str], Field(min_length=2, max_length=50)],
        clearance: Annotated[float, Field(ge=0)] = 0,
        volume_tolerance: Annotated[float, Field(ge=0)] = 1e-6,
    ) -> dict:
        """Check selected BREP solids for overlap, contact and insufficient clearance in mm.

        Returns flagged pairs, overlap volumes and category counts. Contact does not imply
        positive-volume interference. Clear pairs can be rejected using bounding-box distance.
        """
        return client.call(
            "check_interference",
            document=document,
            objects=objects,
            clearance=clearance,
            volume_tolerance=volume_tolerance,
        )

    @server.tool(annotations=READ)
    def sample_motion(
        document: str,
        assembly: str,
        joint: str,
        start: float,
        end: float,
        steps: Annotated[int, Field(ge=2, le=101)],
        objects: Annotated[list[str], Field(min_length=2, max_length=50)],
        clearance: Annotated[float, Field(ge=0)] = 0,
        volume_tolerance: Annotated[float, Field(ge=0)] = 1e-6,
    ) -> dict:
        """Sample a driven joint range and check interference/clearance on a hidden model copy.

        Persisted affine joint couplings are honored. Source pose and undo history are preserved.
        Limited to 5,000 pair-pose checks. Discrete samples do not prove continuous collision-free travel.
        """
        return client.call(
            "sample_motion",
            document=document,
            assembly=assembly,
            joint=joint,
            start=start,
            end=end,
            steps=steps,
            objects=objects,
            clearance=clearance,
            volume_tolerance=volume_tolerance,
        )

    @server.tool(annotations=READ)
    def inspect_sketch(document: str, object_name: str) -> dict:
        """Read sketch-local geometry, zero-based geometry/constraint indices, datum names/values and solver state.

        Rectangles expose their width, height and origin dimensions. Geometry coordinates are local
        XY in mm; use the sketch Placement for its document plane. Native arc/Angle parameters are
        radians; datum strings include units. Use returned constraint indices with set_datum.
        """
        return client.call("inspect_sketch", document=document, object_name=object_name)

    @server.tool(annotations=READ)
    def inspect_topology(
        document: str,
        object_name: str,
        kind: Literal["edges", "faces", "vertices"] = "edges",
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> dict:
        """Read numbered edges/faces/vertices, measurements, positions, curve/surface types and revision.

        Page through large shapes using next_offset. EdgeN/FaceN names refer to this exact shape;
        inspect again after geometry changes before using those names in a feature or measurement.
        Mesh objects require explicit mesh_to_solid conversion before BREP topology inspection.
        """
        return client.call(
            "inspect_topology",
            document=document,
            object_name=object_name,
            kind=kind,
            offset=offset,
            limit=limit,
        )

    @server.tool(annotations=READ)
    def measure_distance(
        document: str,
        object_a: str,
        object_b: str,
        subelement_a: str | None = None,
        subelement_b: str | None = None,
    ) -> dict:
        """Measure minimum BREP distance in mm between two objects or their EdgeN/FaceN/VertexN parts.

        Returns nearest points. Overlap, containment or touching may return zero; this is not a
        collision, wall-thickness or assembly-clearance certification. Meshes need solid conversion.
        """
        return client.call(
            "measure_distance",
            document=document,
            object_a=object_a,
            object_b=object_b,
            subelement_a=subelement_a,
            subelement_b=subelement_b,
        )

    @server.tool(annotations=WRITE)
    def import_model(
        document: str, path: str, name: str, expected_revision: str | None = None
    ) -> dict:
        """Import STEP/STP or BREP as one shape, or STL as a mesh, into an existing document.

        Workspace-confined, source-preserving and undoable. Geometry is a static snapshot; this
        does not reconstruct source design history, assembly structure or colors. STEP uses native
        unit conversion; STL/BREP coordinates are interpreted in mm. Closed meshes can be converted
        using the mesh_to_solid operation. For atomic import-plus-edit, use apply_operations.
        """
        return client.call(
            "import_model",
            document=document,
            path=path,
            name=name,
            expected_revision=expected_revision,
        )

    @server.tool(annotations=EDIT)
    def apply_operations(
        document: str,
        operations: Annotated[list[Edit], Field(min_length=1, max_length=100)],
        expected_revision: str | None = None,
    ) -> dict:
        """Apply one undoable transaction; rollback the whole batch on errors or invalid geometry.

        Supports primitives/helices, dimensions, placements, booleans, bodies, XY sketches (lines/circles/arcs/rectangles),
        sketch constraints and datums, pads, pockets, file import, closed-mesh solid conversion,
        native Part fillets/chamfers, revolutions, native link-array linear/circular patterns,
        pattern updates, named numeric parameters, arithmetic expressions, native lofts/mirrors/sweeps
        and deletion without dependents. Expressions use same-document numeric references,
        units, pi and arithmetic only; remove one explicitly before assigning its driven value.
        Lofts use ordered top-level single-wire profiles; mirrors return only reflected geometry.
        Sweeps use ordered single-wire sections and a single-wire spine or inspected path_edges;
        position/rotate profiles before sweeping. Surface, Frenet and corner controls are explicit.
        Patterns include the original, retain
        separate solids, link native source dimensions and sample its placement on creation/update.
        Pattern steps/axes/centers use document coordinates before any pattern-object Placement.
        Sketch placement is edited separately. All numeric lengths are mm and rotations degrees.
        Constraint args follow FreeCAD's Sketcher.Constraint signature; Angle constraint values
        are radians. Use explicit 'deg' units with set_datum. Names refer to internal object names.
        """
        return client.call(
            "apply_operations",
            document=document,
            operations=[op.model_dump(mode="json", exclude_none=True) for op in operations],
            expected_revision=expected_revision,
        )

    @server.tool(annotations=EDIT)
    def undo_document(document: str, expected_revision: str | None = None) -> dict:
        """Undo the most recent FreeCAD transaction, including a recent manual edit in live mode."""
        return client.call("undo_document", document=document, expected_revision=expected_revision)

    @server.tool(annotations=EDIT)
    def save_document(document: str, path: str, overwrite: bool = False) -> dict:
        """Save FCStd in the workspace; overwrites require true and create a byte-preserving backup."""
        return client.call("save_document", document=document, path=path, overwrite=overwrite)

    @server.tool(annotations=EDIT)
    def export_model(document: str, objects: list[str], path: str, overwrite: bool = False) -> dict:
        """Export named final objects to STEP, STL or BREP; preserve a backup on explicit overwrite."""
        return client.call(
            "export_model", document=document, objects=objects, path=path, overwrite=overwrite
        )

    @server.tool(annotations=READ)
    def get_selection() -> list[dict]:
        """Read selected objects and faces/edges in the live GUI. Unavailable in background mode."""
        return client.call("get_selection")

    @server.tool(annotations=WRITE)
    def set_view(
        document: str,
        orientation: Literal[
            "isometric", "top", "bottom", "front", "rear", "left", "right"
        ] = "isometric",
        fit_all: bool = True,
    ) -> dict:
        """Set a standard live viewport orientation and optionally fit all visible geometry.

        Use before capture_view to inspect a specific side. Live GUI only; no model geometry changes.
        """
        return client.call("set_view", document=document, orientation=orientation, fit_all=fit_all)

    @server.tool(annotations=WRITE, structured_output=False)
    def capture_view(document: str, width: int = 1200, height: int = 900) -> ImageContent:
        """Capture the live viewport as an image and save a PNG in the CAD workspace (64–2048 px).

        Requires the live GUI. Background modeling has no viewport.
        """
        result = client.call("capture_view", document=document, width=width, height=height)
        return ImageContent(data=result["data"], mime_type="image/png")

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "headless"], required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--freecad-cmd")
    args = parser.parse_args()
    client = (
        HeadlessClient(args.workspace, args.freecad_cmd)
        if args.mode == "headless"
        else LiveClient(args.state_file or args.workspace / ".codex-freecad-live.json")
    )
    create_server(client).run(transport="stdio")


if __name__ == "__main__":
    main()
