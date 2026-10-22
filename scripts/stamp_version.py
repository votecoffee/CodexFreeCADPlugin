"""Choose one explicit New York release stamp; never call this during build/startup."""

import argparse
import json
import re
from pathlib import Path

from codex_freecad.versioning import release_from_utc, version_key


def stamp(root, instant):
    release = release_from_utc(instant)
    raw = (json.dumps(release, indent=2) + "\n").encode()
    changes = {}
    for package in (root / "src/codex_freecad", root / "framework-host/src/freecad_mcp_host"):
        if not package.is_dir():
            raise ValueError("Release package is missing")
        previous = package / "release.json"
        if previous.exists():
            old = json.loads(previous.read_bytes())
            if version_key(release["package_version"]) < version_key(old["package_version"]):
                raise ValueError("Release timestamp moves backward; choose a later checkpoint")
            if (
                release["package_version"] == old["package_version"]
                and release["stamped_utc"] != old["stamped_utc"]
            ):
                raise ValueError("Release timestamp collision; choose a distinct local time")
        changes[package / "release.json"] = raw
    for path in (root / "pyproject.toml", root / "framework-host/pyproject.toml"):
        text = path.read_text(encoding="utf-8")
        text, count = re.subn(
            r'^version = "[^"]+"',
            f'version = "{release["package_version"]}"',
            text,
            count=1,
            flags=re.M,
        )
        if count != 1:
            raise ValueError("Project version is missing")
        changes[path] = text.encode()
    skill = root / "src/codex_freecad/standalone_skill.md"
    text = skill.read_text(encoding="utf-8")
    header, body = text[4:].split("\n---\n", 1)
    header = header.split("\nmetadata:\n", 1)[0]
    header += f'\nmetadata:\n  version: "{release["package_version"]}"\n  display_version: "{release["display_version"]}"'
    changes[skill] = ("---\n" + header + "\n---\n" + body).encode()
    # Validate every target before replacing any file. This is an explicit source edit,
    # not a build hook; Git provides review/recovery for the complete checkpoint.
    for path, content in changes.items():
        path.write_bytes(content)
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--utc", required=True, help="Chosen UTC instant; no implicit now value")
    args = parser.parse_args()
    print(json.dumps(stamp(Path(__file__).resolve().parents[1], args.utc), indent=2))


if __name__ == "__main__":
    main()
