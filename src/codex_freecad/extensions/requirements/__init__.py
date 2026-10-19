"""Saved, opt-in design requirements on native property containers."""

import hashlib
import json

from codex_freecad.engine import CadError

from . import rules

VERSION = 1
PROPERTIES = {"RequirementSchemaVersion", "RequirementRulesJson", "RequirementObjects"}


def requirement_set(engine, doc, name):
    obj = engine.obj(doc, name)
    if obj.TypeId != "App::FeaturePython" or not PROPERTIES <= set(obj.PropertiesList):
        raise CadError("Select a saved design requirement set")
    if obj.RequirementSchemaVersion != VERSION or obj.Proxy is not None:
        raise CadError("Unsupported requirement set version or executable proxy")
    return obj


def write(engine, doc, obj, definitions):
    rules.validate(definitions)
    linked = [engine.obj(doc, name) for name in rules.targets(definitions)]
    if any(item.Document != doc or item == obj for item in linked):
        raise CadError("Requirements must target other objects in the same document")
    obj.RequirementSchemaVersion = VERSION
    obj.RequirementRulesJson = json.dumps(definitions, sort_keys=True, separators=(",", ":"))
    obj.RequirementObjects = linked
    for prop in PROPERTIES:
        obj.setEditorMode(prop, 1)
    return {"name": obj.Name, "rule_count": len(definitions), "objects": [x.Name for x in linked]}


def create_set(engine, doc, arguments):
    rules.validate(arguments["rules"])
    obj = engine.add(doc, "App::FeaturePython", arguments["name"])
    obj.addProperty("App::PropertyInteger", "RequirementSchemaVersion", "Design requirements")
    obj.addProperty("App::PropertyString", "RequirementRulesJson", "Design requirements")
    obj.addProperty("App::PropertyLinkList", "RequirementObjects", "Design requirements")
    return write(engine, doc, obj, arguments["rules"])


def update_set(engine, doc, arguments):
    return write(engine, doc, requirement_set(engine, doc, arguments["set"]), arguments["rules"])


def evaluate(engine, doc, arguments):
    obj = requirement_set(engine, doc, arguments["set"])
    try:
        definitions = rules.validate(json.loads(obj.RequirementRulesJson))
    except (ValueError, TypeError) as exc:
        raise CadError("Invalid saved requirement definitions") from exc
    expected = rules.targets(definitions)
    links = obj.RequirementObjects
    actual = sorted(item.Name for item in links if item is not None and item.Document == doc)
    link_error = (
        None
        if expected == actual and len(links) == len(actual)
        else "Requirement source links changed; update the set"
    )
    return {
        "set": obj.Name,
        "definition_sha256": hashlib.sha256(obj.RequirementRulesJson.encode("utf-8")).hexdigest(),
        **rules.evaluate(engine, doc, definitions, link_error),
        "scope": "Explicit limits on evaluated native geometry/properties at this pose. Clearance checks distinguish positive-volume overlap from contact. Requirements are opt-in checks, not an automatic document policy, tolerance certification or strength analysis.",
    }


def enforce(engine, doc, arguments):
    doc.recompute()
    report = evaluate(engine, doc, arguments)
    if not report["all_passed"]:
        failed = [
            row["id"] + " (" + row["status"] + ")"
            for row in report["rules"]
            if row["status"] != "pass"
        ]
        raise CadError("Design requirements not satisfied: " + ", ".join(failed))
    return report
