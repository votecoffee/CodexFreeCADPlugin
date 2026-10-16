"""BREP interference/clearance queries and motion samples on a hidden document copy."""

import math
import uuid

from .engine import CadError, number


def names_and_shapes(engine, doc, names):
    if not isinstance(names, list) or not 2 <= len(names) <= 50:
        raise CadError("Select between 2 and 50 solid objects")
    if any(not isinstance(x, str) for x in names) or len(set(names)) != len(names):
        raise CadError("Interference object names must be unique strings")
    result = []
    for name in names:
        obj = engine.obj(doc, name)
        # Shape placements on assembly links are already document-space because
        # supported root assemblies have identity placement.
        parent = obj.getParentGeoFeatureGroup()
        if parent is not None and (
            parent.TypeId != "Assembly::AssemblyObject" or not parent.Placement.isIdentity()
        ):
            raise CadError(
                "Use top-level objects or components in an identity-placement root assembly"
            )
        shape = engine.shape(doc, name)
        if not shape.Solids or not shape.isValid():
            raise CadError("Interference checks require valid BREP solids")
        result.append((name, shape, shape.optimalBoundingBox(False, False)))
    return result


def box_distance(a, b):
    return math.sqrt(
        sum(
            max(lo1 - hi2, lo2 - hi1, 0) ** 2
            for lo1, hi1, lo2, hi2 in (
                (a.XMin, a.XMax, b.XMin, b.XMax),
                (a.YMin, a.YMax, b.YMin, b.YMax),
                (a.ZMin, a.ZMax, b.ZMin, b.ZMax),
            )
        )
    )


def check(engine, doc, objects, clearance=0, volume_tolerance=1e-6):
    clearance, volume_tolerance = number(clearance), number(volume_tolerance)
    if clearance < 0 or volume_tolerance < 0:
        raise CadError("Clearance and overlap volume tolerance cannot be negative")
    shapes = names_and_shapes(engine, doc, objects)
    flagged = []
    broad_clear = 0
    counts = {"overlap": 0, "contact": 0, "insufficient_clearance": 0, "clear": 0}
    for index, (first, a, box_a) in enumerate(shapes):
        for second, b, box_b in shapes[index + 1 :]:
            lower_bound = box_distance(box_a, box_b)
            if lower_bound > clearance + 1e-7:
                counts["clear"] += 1
                broad_clear += 1
                continue
            common = a.common(b)
            if not common.isNull() and not common.isValid():
                raise CadError("Native intersection produced invalid geometry")
            volume = max(common.Volume, 0) if not common.isNull() else 0
            if volume > volume_tolerance:
                category, distance = "overlap", 0
            else:
                distance = a.distToShape(b)[0]
                category = (
                    "contact"
                    if distance <= 1e-7
                    else ("insufficient_clearance" if distance < clearance else "clear")
                )
            counts[category] += 1
            if category != "clear":
                flagged.append(
                    {
                        "object_a": first,
                        "object_b": second,
                        "status": category,
                        "overlap_mm3": volume,
                        "distance_mm": distance,
                    }
                )
    return {
        "objects": list(objects),
        "pair_count": len(shapes) * (len(shapes) - 1) // 2,
        "clearance_mm": clearance,
        "volume_tolerance_mm3": volume_tolerance,
        "counts": counts,
        "pairs": flagged,
        "broad_phase_clear_pairs": broad_clear,
        "scope": "Evaluated BREP geometry at this pose; contact is distinct from positive-volume overlap. No loads, friction or dynamics.",
    }


def sample(
    engine, doc, assembly, joint, start, end, steps, objects, clearance=0, volume_tolerance=1e-6
):
    from .assemblies import assembly as find_assembly
    from .assemblies import position
    from .motion import coordinate, moving_joints

    source_asm = find_assembly(engine, doc, assembly)
    if joint not in moving_joints(source_asm):
        raise CadError("Motion sample driver must be a movable joint in the assembly")
    if type(steps) is not int or not 2 <= steps <= 101:
        raise CadError("Motion sampling requires an integer step count between 2 and 101")
    start, end = number(start), number(end)
    names_and_shapes(engine, doc, objects)
    if any(name not in {x.Name for x in source_asm.Group} for name in objects):
        raise CadError("Motion samples must select components belonging to this assembly")
    if len(objects) * (len(objects) - 1) // 2 * steps > 5000:
        raise CadError("Motion sampling is limited to 5,000 pair-pose checks")
    engine.require_idle(doc, "sampling motion")
    original_active = engine.app.ActiveDocument
    clone = engine.app.newDocument("MotionCheck" + uuid.uuid4().hex[:12], hidden=True)
    frames = []
    try:
        copied = clone.copyObject(source_asm, True)
        clone.recompute()
        for i in range(steps):
            value = start + (end - start) * i / (steps - 1)
            position(engine, clone, copied, [{"joint": joint, "position": value}])
            clone.recompute()
            frame = check(engine, clone, objects, clearance, volume_tolerance)
            frames.append(
                {
                    "index": i,
                    "position": value,
                    "counts": frame["counts"],
                    "pairs": frame["pairs"],
                    "coordinates": {
                        name: coordinate(engine, clone, copied, obj)
                        for name, obj in moving_joints(copied).items()
                    },
                }
            )
    finally:
        engine.app.closeDocument(clone.Name)
        if original_active is not None:
            engine.app.setActiveDocument(original_active.Name)
    return {
        "assembly": assembly,
        "joint": joint,
        "start": start,
        "end": end,
        "steps": steps,
        "frames": frames,
        "overlap_frames": sum(x["counts"]["overlap"] > 0 for x in frames),
        "scope": "Discrete pose samples on a hidden native copy; source pose and undo history are untouched. Samples do not prove continuous collision-free travel.",
    }
