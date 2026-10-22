"""Canonical, hash-bound workflow data shared by ordinary tools and MCP skills."""

import argparse
import hashlib
import json
import re
from pathlib import Path

TOPICS = {name: f"references/{name}.md" for name in ("overview", "extensions", "recovery")}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(files):
    if not isinstance(files, dict) or not 4 <= len(files) <= 64:
        raise ValueError("Invalid workflow file inventory")
    total = 0
    for name, content in files.items():
        if not re.fullmatch(
            r"SKILL\.md|references/[a-z0-9][a-z0-9_.-]*\.(md|json)", name
        ) or not isinstance(content, str):
            raise ValueError("Invalid workflow resource")
        total += len(content.encode("utf-8"))
    if total > 2 * 1024 * 1024 or not {"SKILL.md", *TOPICS.values()} <= files.keys():
        raise ValueError("Workflow resource limits or required topics failed")
    inventory = {name: digest(content.encode("utf-8")) for name, content in sorted(files.items())}
    revision = digest(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode())
    return {
        "schema_version": 1,
        "id": "freecad-modeling",
        "revision": revision,
        "files": dict(files),
    }


def validate(value):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
        raise ValueError("Invalid workflow snapshot")
    result = snapshot(value["files"])
    if any(value.get(key) != result[key] for key in ("schema_version", "id", "revision")):
        raise ValueError("Workflow snapshot identity/hash mismatch")
    return result


def build_snapshot(extension_dirs=(), *, source_package=None, feature_config=None):
    from .host_catalog import installation_catalog
    from .runtime_features import feature_report

    source = Path(source_package or Path(__file__).parent)
    files = {"SKILL.md": (source / "standalone_skill.md").read_bytes().decode("utf-8")}
    files.update(
        {
            "references/" + path.name: path.read_bytes().decode("utf-8")
            for path in sorted((source / "guidance").glob("*.md"))
        }
    )
    files["references/extension-index.json"] = (
        json.dumps(
            {
                "scope": "installed-publication-hints; discover active native schemas before use",
                **installation_catalog(extension_dirs),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    files["references/features.json"] = (
        json.dumps(
            feature_report(**{"app_host": feature_config is not None, **(feature_config or {})}),
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    return snapshot(files)


def describe_workflow(
    topic="overview", *, reference=None, expected_revision=None, expected_sha256=None, current=None
):
    current = validate(current) if current is not None else build_snapshot()
    if expected_revision is not None and expected_revision != current["revision"]:
        raise ValueError("Stale workflow revision; rediscover the current guide")
    if reference is not None and expected_revision is None:
        raise ValueError("Pin the workflow revision before reading a reference")
    if topic not in TOPICS:
        raise ValueError("Unknown FreeCAD workflow topic")
    name = reference or TOPICS[topic]
    if name not in current["files"]:
        raise ValueError("Unknown workflow reference")
    raw = current["files"][name].encode("utf-8")
    if expected_sha256 is not None and expected_sha256 != digest(raw):
        raise ValueError("Stale workflow resource hash")
    return {
        "schema_version": 1,
        "id": current["id"],
        "revision": current["revision"],
        "topic": topic,
        "reference": name,
        "guidance": raw.decode("utf-8"),
        "sha256": digest(raw),
        "topics": list(TOPICS),
        "references": [
            {
                "id": key,
                "uri": "skill://freecad-modeling/" + key,
                "sha256": digest(value.encode("utf-8")),
                "size": len(value.encode("utf-8")),
            }
            for key, value in sorted(current["files"].items())
        ],
    }


def publication_inputs(path):
    definition = json.loads(Path(path).read_bytes())
    backend = next(
        row for row in definition["backends"] if row["service"]["id"] == "freecad-headless"
    )
    root = Path(backend["artifact"]["path"]).parent
    launcher = (root / "launcher.py").read_bytes()
    if digest(launcher) != backend["artifact"]["sha256"]:
        raise ValueError("Publication launcher changed")
    match = re.search(rb"hexdigest\(\) != '([0-9a-f]{64})'", launcher)
    closure = (root / "closure.json").read_bytes()
    if not match or digest(closure) != match[1].decode():
        raise ValueError("Publication closure changed")
    manifest = json.loads(closure)["files"]
    for name, expected in manifest.items():
        if (
            name.endswith(".md")
            and name.startswith("package/codex_freecad/")
            and digest((root / name).read_bytes()) != expected
        ):
            raise ValueError("Published guidance bytes changed")
    args = backend["service"]["transport"]["args"]
    extensions = [args[i + 1] for i, arg in enumerate(args) if arg == "--extensions"]
    return root / "package/codex_freecad", extensions


def main():
    from .framework_setup import atomic_json

    parser = argparse.ArgumentParser(
        description="Explicitly stage a guide-only publication; no native operation."
    )
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--source-package", type=Path)
    parser.add_argument("--expected-revision", required=True)
    args = parser.parse_args()
    source, extensions = publication_inputs(args.publication)
    definition = json.loads(args.publication.read_bytes())
    service = definition["backends"][0]["service"]
    config = {
        key: service[key]
        for key in ("protocol_mode", "watch_catalog", "discovery_cache_ttl_seconds")
        if key in service
    }
    candidate = build_snapshot(
        extensions, source_package=args.source_package or source, feature_config=config
    )
    atomic_json(
        args.publication.parent / "guidance/desired.json",
        {"expected_revision": args.expected_revision, "snapshot": candidate},
    )
    print(
        json.dumps({"staged_revision": candidate["revision"], "activation": "await host readback"})
    )


if __name__ == "__main__":
    main()
