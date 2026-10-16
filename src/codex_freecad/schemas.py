"""Model-facing operation schemas, kept outside FreeCAD's embedded Python."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Box(Operation):
    op: Literal["create_box"]
    name: str
    length: float = Field(gt=0, description="Length along X in millimeters")
    width: float = Field(gt=0, description="Width along Y in millimeters")
    height: float = Field(gt=0, description="Height along Z in millimeters")
    label: str | None = None


class Cylinder(Operation):
    op: Literal["create_cylinder"]
    name: str
    radius: float = Field(gt=0)
    height: float = Field(gt=0)
    label: str | None = None


class Sphere(Operation):
    op: Literal["create_sphere"]
    name: str
    radius: float = Field(gt=0)
    label: str | None = None


class Body(Operation):
    op: Literal["create_body"]
    name: str
    label: str | None = None


class Line(Operation):
    type: Literal["line"]
    start: tuple[float, float]
    end: tuple[float, float]
    construction: bool = False


class Circle(Operation):
    type: Literal["circle"]
    center: tuple[float, float]
    radius: float = Field(gt=0)
    construction: bool = False


class Arc(Operation):
    type: Literal["arc"]
    start: tuple[float, float]
    mid: tuple[float, float]
    end: tuple[float, float]
    construction: bool = False


class Rectangle(Operation):
    type: Literal["rectangle"]
    origin: tuple[float, float]
    width: float = Field(gt=0, strict=True)
    height: float = Field(gt=0, strict=True)
    constrained: bool = Field(
        default=True, description="Add closure, H/V, width/height and origin dimensions"
    )
    construction: bool = False


SketchGeometry = Annotated[Line | Circle | Arc | Rectangle, Field(discriminator="type")]


class Sketch(Operation):
    op: Literal["create_sketch"]
    name: str
    geometry: list[SketchGeometry] = Field(min_length=1, max_length=1000)
    body: str | None = None
    label: str | None = None


class Constraint(Operation):
    op: Literal["add_constraint"]
    object: str
    type: Literal[
        "Coincident",
        "Horizontal",
        "Vertical",
        "Distance",
        "DistanceX",
        "DistanceY",
        "Radius",
        "Diameter",
        "Equal",
        "Parallel",
        "Perpendicular",
        "Tangent",
        "Angle",
    ]
    args: list[int | float] = Field(
        min_length=1,
        max_length=6,
        description="FreeCAD Sketcher.Constraint positional arguments after its type; geometry indices are integers",
    )


class Datum(Operation):
    op: Literal["set_datum"]
    object: str
    constraint_index: int = Field(ge=0)
    value: str = Field(description="Quantity with explicit units, e.g. '12 mm' or '30 deg'")


class Extrusion(Operation):
    op: Literal["pad", "pocket"]
    name: str
    body: str
    sketch: str
    length: float = Field(gt=0)
    label: str | None = None


class Boolean(Operation):
    op: Literal["boolean"]
    name: str
    kind: Literal["cut", "fuse", "common"]
    base: str
    tool: str
    label: str | None = None


class Property(Operation):
    op: Literal["set_property"]
    object: str
    property: str
    value: str | int | float | bool = Field(
        description="Scalar or unit-bearing quantity. Expressions and file properties cannot be assigned."
    )


class Placement(Operation):
    op: Literal["set_placement"]
    object: str
    position: tuple[float, float, float] = Field(description="Absolute translation in millimeters")
    axis: tuple[float, float, float] = (0, 0, 1)
    angle: float = Field(default=0, description="Absolute rotation in degrees about axis")


class Delete(Operation):
    op: Literal["delete_object"]
    object: str


class ImportModel(Operation):
    op: Literal["import_model"]
    name: str
    path: str = Field(description="STEP/STP, BREP or STL file inside the CAD workspace")


class MeshToSolid(Operation):
    op: Literal["mesh_to_solid"]
    name: str
    mesh: str
    tolerance: float = Field(
        default=0.01, gt=0, description="Mesh sewing tolerance in mm; up to 20,000 facets"
    )
    label: str | None = None


class EdgeTreatment(Operation):
    op: Literal["fillet", "chamfer"]
    name: str
    base: str
    edges: list[str] = Field(
        min_length=1,
        max_length=500,
        description="Current base EdgeN names from inspect_topology; re-inspect after shape changes",
    )
    size: float = Field(gt=0, description="Fillet radius or equal-distance chamfer size in mm")
    label: str | None = None


class SetEdgeTreatment(Operation):
    op: Literal["set_edge_treatment"]
    object: str
    edges: list[str] = Field(
        min_length=1,
        max_length=500,
        description="Edges of this feature's BASE object, not its result",
    )
    size: float = Field(gt=0, description="Replacement radius or equal-distance chamfer size in mm")


class AddSketchGeometry(Operation):
    op: Literal["add_sketch_geometry"]
    object: str
    geometry: list[SketchGeometry] = Field(min_length=1, max_length=1000)


class Revolve(Operation):
    op: Literal["revolve"]
    name: str
    source: str
    center: tuple[float, float, float] = (0, 0, 0)
    axis: tuple[float, float, float] = (0, 0, 1)
    angle: float = Field(
        default=360, ge=-360, le=360, description="Nonzero revolution angle in degrees"
    )
    solid: bool = True
    label: str | None = None


class LinearPattern(Operation):
    op: Literal["linear_pattern"]
    name: str
    source: str
    count: int = Field(
        ge=2, le=200, strict=True, description="Total instances including the original"
    )
    step: tuple[float, float, float] = Field(
        description="Nonzero translation per instance in document mm"
    )
    label: str | None = None


class CircularPattern(Operation):
    op: Literal["circular_pattern"]
    name: str
    source: str
    count: int = Field(ge=2, le=200, strict=True)
    center: tuple[float, float, float] = (0, 0, 0)
    axis: tuple[float, float, float] = (0, 0, 1)
    angle: float = Field(
        default=360,
        ge=-360,
        le=360,
        description="Full +/-360 circle excludes duplicate endpoint; a partial span includes both endpoints",
    )
    label: str | None = None


class SetLinearPattern(Operation):
    op: Literal["set_linear_pattern"]
    object: str
    count: int = Field(ge=2, le=200, strict=True)
    step: tuple[float, float, float]


class SetCircularPattern(Operation):
    op: Literal["set_circular_pattern"]
    object: str
    count: int = Field(ge=2, le=200, strict=True)
    center: tuple[float, float, float] = (0, 0, 0)
    axis: tuple[float, float, float] = (0, 0, 1)
    angle: float = Field(default=360, ge=-360, le=360)


class Parameter(Operation):
    name: str
    type: Literal["length", "angle", "number", "integer"]
    value: StrictFloat | StrictInt | StrictStr
    description: str = Field(default="", max_length=1000)


class Parameters(Operation):
    op: Literal["create_parameters"]
    name: str
    parameters: list[Parameter] = Field(min_length=1, max_length=100)
    label: str | None = None


class Expression(Operation):
    op: Literal["set_expression"]
    object: str
    property: str = Field(
        description="Numeric property, Placement.Base.x/y/z or Constraints[index/name]"
    )
    expression: str = Field(
        min_length=1,
        max_length=1000,
        description="Arithmetic (+ - * / ^), parentheses, units, pi and same-document numeric properties; no functions or external documents",
    )


class ClearExpression(Operation):
    op: Literal["clear_expression"]
    object: str
    property: str = Field(description="Remove expression while retaining its last evaluated value")


class Loft(Operation):
    op: Literal["loft"]
    name: str
    profiles: list[str] = Field(
        min_length=2,
        max_length=50,
        description="Distinct top-level single-wire profiles in section order",
    )
    solid: bool = True
    ruled: bool = False
    label: str | None = None


class SetLoft(Operation):
    op: Literal["set_loft"]
    object: str
    profiles: list[str] = Field(min_length=2, max_length=50)
    solid: bool | None = None
    ruled: bool | None = None


class Mirror(Operation):
    op: Literal["mirror"]
    name: str
    source: str = Field(description="Top-level source; mirrored geometry excludes the original")
    point: tuple[float, float, float] = (0, 0, 0)
    normal: tuple[float, float, float] = (1, 0, 0)
    label: str | None = None


class SetMirror(Operation):
    op: Literal["set_mirror"]
    object: str
    point: tuple[float, float, float] = (0, 0, 0)
    normal: tuple[float, float, float] = (1, 0, 0)


class Sweep(Operation):
    op: Literal["sweep"]
    name: str
    profiles: list[str] = Field(
        min_length=1,
        max_length=50,
        description="Ordered top-level single-wire sections; place sections relative to the path before sweeping",
    )
    path: str = Field(
        description="Top-level spine object containing a single wire, or an object with selected path_edges"
    )
    path_edges: list[str] = Field(
        default_factory=list,
        max_length=500,
        description="Optional current EdgeN selections; empty uses the entire single-wire path",
    )
    solid: bool = True
    frenet: bool = False
    transition: Literal["transformed", "right_corner", "round_corner"] = "transformed"
    label: str | None = None


class SetSweep(Operation):
    op: Literal["set_sweep"]
    object: str
    profiles: list[str] = Field(min_length=1, max_length=50)
    path: str
    path_edges: list[str] = Field(
        default_factory=list,
        max_length=500,
        description="Replacement selection; empty uses the entire path",
    )
    solid: bool | None = None
    frenet: bool | None = None
    transition: Literal["transformed", "right_corner", "round_corner"] | None = None


class Helix(Operation):
    op: Literal["create_helix"]
    name: str
    pitch: float = Field(gt=0, description="Axial pitch per revolution in mm")
    height: float = Field(gt=0, description="Axial height in mm, at most 10,000 turns")
    radius: float = Field(gt=0, description="Starting helix radius in mm")
    angle: float = Field(
        default=0, gt=-90, lt=90, description="Conical taper angle in degrees; zero is cylindrical"
    )
    left_handed: bool = False
    label: str | None = None


Edit = Annotated[
    Box
    | Cylinder
    | Sphere
    | Body
    | Sketch
    | Constraint
    | Datum
    | Extrusion
    | Boolean
    | Property
    | Placement
    | Delete
    | ImportModel
    | MeshToSolid
    | EdgeTreatment
    | SetEdgeTreatment
    | AddSketchGeometry
    | Revolve
    | LinearPattern
    | CircularPattern
    | SetLinearPattern
    | SetCircularPattern
    | Parameters
    | Expression
    | ClearExpression
    | Loft
    | SetLoft
    | Mirror
    | SetMirror
    | Sweep
    | SetSweep
    | Helix,
    Field(discriminator="op"),
]
