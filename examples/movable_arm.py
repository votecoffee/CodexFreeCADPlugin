"""Build a linked rotary arm with a sliding tool using either integration backend."""

import math


def positions(angle, extension):
    return {
        "op": "set_joint_positions",
        "assembly": "ArmAssembly",
        "positions": [
            {"joint": "Shoulder", "position": angle},
            {"joint": "Extension", "position": extension},
        ],
    }


def build(client, document="MovableArm"):
    client.call("new_document", name=document)
    result = client.call(
        "apply_operations",
        document=document,
        operations=[
            {"op": "create_box", "name": "Base", "length": 30, "width": 20, "height": 4},
            {"op": "create_box", "name": "Arm", "length": 40, "width": 6, "height": 6},
            {"op": "create_cylinder", "name": "Tool", "radius": 3, "height": 12},
            {"op": "create_assembly", "name": "ArmAssembly"},
            *[
                {
                    "op": "add_component",
                    "assembly": "ArmAssembly",
                    "name": name + "Link",
                    "source": name,
                }
                for name in ("Base", "Arm", "Tool")
            ],
            {
                "op": "ground_component",
                "assembly": "ArmAssembly",
                "name": "Ground",
                "component": "BaseLink",
            },
            {
                "op": "create_joint",
                "assembly": "ArmAssembly",
                "name": "Shoulder",
                "kind": "revolute",
                "component_a": "BaseLink",
                "component_b": "ArmLink",
                "frame_a": {"position": [15, 10, 10]},
                "frame_b": {"position": [0, 3, 3]},
            },
            {
                "op": "create_joint",
                "assembly": "ArmAssembly",
                "name": "Extension",
                "kind": "slider",
                "component_a": "ArmLink",
                "component_b": "ToolLink",
                "frame_a": {"position": [40, 3, 3], "axis": [0, 1, 0], "angle": 90},
                "frame_b": {"position": [0, 0, 6]},
            },
            positions(0, 0),
            {
                "op": "set_joint_limits",
                "assembly": "ArmAssembly",
                "joint": "Shoulder",
                "minimum": -135,
                "maximum": 135,
            },
            {
                "op": "set_joint_limits",
                "assembly": "ArmAssembly",
                "joint": "Extension",
                "minimum": 0,
                "maximum": 25,
            },
            positions(55, 14),
        ],
    )
    return {
        "document": result["document"]["name"],
        "objects": ["BaseLink", "ArmLink", "ToolLink"],
        "expected_volume_mm3": 30 * 20 * 4 + 40 * 6 * 6 + math.pi * 3**2 * 12,
    }
