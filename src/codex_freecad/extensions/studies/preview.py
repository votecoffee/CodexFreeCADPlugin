"""Numeric change previews with native material differences and revision-bound edits."""

import math

from codex_freecad.engine import CadError

from . import check_recompute, hidden_copy, measure, numeric_driver, validate_outputs


def scalar(obj, prop):
    value = getattr(obj, prop)
    return value.Value if hasattr(value, "Value") else value


def selected_shapes(engine, doc, names):
    shapes = [engine.shape(doc, name).copy() for name in names]
    if sum(len(shape.Edges) for shape in shapes) > 5000:
        raise CadError("Change previews support at most 5,000 selected shape edges")
    return shapes


def difference_volume(left, right):
    difference = left.cut(right)
    if difference.isNull():
        return 0.0
    if not difference.isValid():
        raise CadError("Native material difference produced invalid geometry")
    volume = difference.Volume if difference.Solids else 0.0
    if not math.isfinite(volume) or volume < 0:
        raise CadError("Native material difference produced an invalid volume")
    return volume


def preview(engine, doc, arguments):
    names = arguments["objects"]
    changes = arguments["changes"]
    validate_outputs(engine, doc, names)
    keys = [(item["object"], item["property"]) for item in changes]
    if len(set(keys)) != len(keys):
        raise CadError("Preview changes must identify distinct object properties")
    parameters = []
    for item in changes:
        driver = numeric_driver(engine, doc, item["object"], item["property"])
        parameters.append(
            {
                "object": driver.Name,
                "property": item["property"],
                "property_type": driver.getTypeIdOfProperty(item["property"]),
                "before": scalar(driver, item["property"]),
                "requested": item["value"],
            }
        )
    operations = [{"op": "set_property", **item} for item in changes]
    requirement_sets = arguments.get("requirement_sets", [])
    if len(set(requirement_sets)) != len(requirement_sets):
        raise CadError("Preview requirement sets must be unique")

    def requirements(target):
        return [
            engine.registry.invoke(engine, target, "requirements.evaluate", {"set": name}, "query")[
                "result"
            ]
            for name in requirement_sets
        ]

    source_revision = engine.revision(doc)
    density = arguments.get("density_kg_m3")
    with hidden_copy(engine, doc) as clone:
        check_recompute(clone)
        before = [measure(engine, clone, name, density) for name in names]
        before_shapes = selected_shapes(engine, clone, names)
        requirements_before = requirements(clone)
        # Use the exact same operation order and guards as the proposed source edit.
        for index, operation in enumerate(operations):
            try:
                engine.operation(clone, operation)
                check_recompute(clone)
            except Exception as exc:
                raise CadError(f"Preview change {index} failed: {exc}") from exc
        after = [measure(engine, clone, name, density) for name in names]
        after_shapes = selected_shapes(engine, clone, names)
        requirements_after = requirements(clone)
        for row in parameters:
            row["after"] = scalar(engine.obj(clone, row["object"]), row["property"])
        objects = []
        for old, new, old_shape, new_shape in zip(
            before, after, before_shapes, after_shapes, strict=True
        ):
            added = difference_volume(new_shape, old_shape)
            removed = difference_volume(old_shape, new_shape)
            delta = new["volume_mm3"] - old["volume_mm3"]
            tolerance = max(old["volume_mm3"], new["volume_mm3"]) * 1e-7 + 1e-6
            if abs(added - removed - delta) > tolerance:
                raise CadError("Native material difference failed volume consistency check")
            row = {
                "object": old["object"],
                "before": old,
                "after": new,
                "delta_volume_mm3": delta,
                "delta_area_mm2": new["area_mm2"] - old["area_mm2"],
                "added_volume_mm3": added,
                "removed_volume_mm3": removed,
            }
            if density is not None:
                row["delta_mass_kg"] = new["mass_kg"] - old["mass_kg"]
            objects.append(row)
    if requirement_sets:
        operations += [
            {
                "op": "extension",
                "capability": "requirements.enforce",
                "arguments": {"set": name},
                "catalog_revision": engine.registry.active.revision,
            }
            for name in requirement_sets
        ]
    return {
        "document": doc.Name,
        "parameters": parameters,
        "objects": objects,
        "requirements": {
            "set_count": len(requirement_sets),
            "before": requirements_before,
            "after": requirements_after,
            "all_passed_after": all(item["all_passed"] for item in requirements_after),
        },
        "apply_arguments": {
            "document": doc.Name,
            "expected_revision": source_revision,
            "operations": operations,
        },
        "scope": "Native numeric edits evaluated on a hidden dependency copy. Material differences cover only selected solids in model coordinates; overlapping selections are not a union. Source parameters and Undo are preserved. Applying is a separate revision-guarded edit, not an automatic action.",
    }
