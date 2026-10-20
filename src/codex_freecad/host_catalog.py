"""Installation metadata for app-host discovery; never imports handlers or FreeCAD."""

import hashlib
import json

from .extension_runtime import Registry


def installation_catalog(extension_dirs=()):
    sources = Registry(extension_dirs, load=False).scan()
    revision = hashlib.sha256(
        json.dumps({key: item["sha256"] for key, item in sources.items()}, sort_keys=True).encode()
    ).hexdigest()
    result = {
        "schema_version": 1,
        "catalog_revision": revision,
        "capabilities": [
            {
                "id": extension + "." + name,
                "description": item["description"],
                "tags": ["FreeCAD", extension, item["kind"]],
                "discovery": {
                    "tool": "describe_capability",
                    "arguments": {"capability": extension + "." + name},
                },
            }
            for extension, source in sources.items()
            for name, item in source["manifest"]["capabilities"].items()
        ],
    }
    if len(result["capabilities"]) > 1000 or any(
        len(item["description"]) > 4096 for item in result["capabilities"]
    ):
        raise ValueError("Installation catalog exceeds host capability count/description limits")
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 512 * 1024:
        raise ValueError("Installation catalog exceeds the host's 512 KiB metadata limit")
    return result
