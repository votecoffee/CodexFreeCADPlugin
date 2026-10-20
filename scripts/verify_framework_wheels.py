"""Verify separate CAD/host wheels against source and a trusted framework wheel digest."""

import argparse
import base64
import csv
import hashlib
import io
import json
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path


def inspect_wheel(path):
    with zipfile.ZipFile(path) as bundle:
        records = [name for name in bundle.namelist() if name.endswith(".dist-info/RECORD")]
        if len(records) != 1 or len(bundle.namelist()) != len(set(bundle.namelist())):
            raise ValueError("Wheel needs one RECORD and unique members")
        rows = list(csv.reader(io.StringIO(bundle.read(records[0]).decode("utf-8"))))
        if {row[0] for row in rows} != set(bundle.namelist()):
            raise ValueError("Wheel RECORD does not cover every member")
        for name, digest, size in rows:
            if name == records[0]:
                continue
            data = bundle.read(name)
            expected = "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(data).digest()
            ).decode().rstrip("=")
            if digest != expected or int(size) != len(data):
                raise ValueError("Wheel member failed RECORD validation: " + name)
        metadata = records[0].removesuffix("RECORD") + "METADATA"
        return Parser().parsestr(bundle.read(metadata).decode("utf-8")), {
            name: bundle.read(name) for name in bundle.namelist()
        }


def verify(backend, host, framework, expected_framework_sha256, *, site_packages=None):
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(Path(framework).read_bytes()).hexdigest()
    if digest != expected_framework_sha256:
        raise ValueError("Framework wheel does not match the supplied trusted SHA-256")
    values = [inspect_wheel(path) for path in (backend, host, framework)]
    for (metadata, _), expected in zip(
        values, ("codex-freecad", "freecad-mcp-host", "universal-codex-tools"), strict=True
    ):
        if metadata["Name"] != expected:
            raise ValueError("Unexpected wheel distribution: " + metadata["Name"])
    configuration = tomllib.loads(
        (root / "framework-host/pyproject.toml").read_text(encoding="utf-8")
    )
    required = configuration["project"]["dependencies"]
    framework_pin = next(item for item in required if item.startswith("universal-codex-tools=="))
    expected_version = framework_pin.split("==", 1)[1]
    if values[2][0]["Version"] != expected_version:
        raise ValueError("Framework wheel version differs from the exact application pin")
    if "mcp==2.3.0" not in values[0][0].get_all("Requires-Dist", []):
        raise ValueError("Backend MCP SDK requirement changed")
    if set(values[1][0].get_all("Requires-Dist", [])) != set(required):
        raise ValueError("Host must use the exact normal framework dependency")
    if "mcp==2.3.0" not in values[2][0].get_all("Requires-Dist", []):
        raise ValueError("Framework wheel must require MCP 2.3.0; downgrades are not accepted")
    for (_, members), source, package in (
        (values[0], root / "src/codex_freecad", "codex_freecad"),
        (values[1], root / "framework-host/src/freecad_mcp_host", "freecad_mcp_host"),
    ):
        expected = {
            package + "/" + path.relative_to(source).as_posix(): path.read_bytes()
            for path in source.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix in {".py", ".json", ".md"}
        }
        actual = {name: data for name, data in members.items() if name.startswith(package + "/")}
        if actual != expected:
            raise ValueError(
                "Application wheel does not match its source code/resources: " + package
            )
        if any(name.startswith("universal_tools/") for name in members):
            raise ValueError("Application wheel must not vendor framework implementation")
    if site_packages is not None:
        site_packages = Path(site_packages).resolve()
        for (_, members), package in zip(
            values, ("codex_freecad", "freecad_mcp_host", "universal_tools"), strict=True
        ):
            expected = {k: v for k, v in members.items() if k.startswith(package + "/")}
            actual = {
                p.relative_to(site_packages).as_posix(): p.read_bytes()
                for p in (site_packages / package).rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}
            }
            if actual != expected:
                raise ValueError("Installed package differs from the audited wheel: " + package)
    return {
        "framework": expected_version,
        "framework_sha256": digest,
        "backend": values[0][0]["Version"],
        "host": values[1][0]["Version"],
        "mcp_requirement": "2.3.0",
        "source_and_record_verified": True,
        "installed_bytes_verified": site_packages is not None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-wheel", type=Path, required=True)
    parser.add_argument("--host-wheel", type=Path, required=True)
    parser.add_argument("--framework-wheel", type=Path, required=True)
    parser.add_argument("--framework-sha256", required=True)
    parser.add_argument("--site-packages", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.backend_wheel,
                args.host_wheel,
                args.framework_wheel,
                args.framework_sha256,
                site_packages=args.site_packages,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
