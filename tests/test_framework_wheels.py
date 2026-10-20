import base64
import csv
import hashlib
import importlib.util
import io
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "framework_wheel_checks", ROOT / "scripts/verify_framework_wheels.py"
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def wheel(path, name, version, dependencies, members=None):
    members = dict(members or {})
    directory = name.replace("-", "_") + "-" + version + ".dist-info/"
    members[directory + "METADATA"] = (
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
        + "".join(f"Requires-Dist: {dep}\n" for dep in dependencies)
        + "\n"
    ).encode()
    stream = io.StringIO()
    writer = csv.writer(stream)
    for filename, content in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        writer.writerow([filename, "sha256=" + digest, len(content)])
    writer.writerow([directory + "RECORD", "", ""])
    members[directory + "RECORD"] = stream.getvalue().encode()
    with zipfile.ZipFile(path, "w") as bundle:
        for filename, content in members.items():
            bundle.writestr(filename, content)
    return path


def source_members(source, prefix):
    return {
        prefix + "/" + path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".json", ".md"}
    }


@pytest.fixture
def wheels(tmp_path):
    config = tomllib.loads((ROOT / "framework-host/pyproject.toml").read_text())
    dependencies = config["project"]["dependencies"]
    framework_version = next(
        dep.split("==")[1] for dep in dependencies if dep.startswith("universal-codex-tools==")
    )
    backend = wheel(
        tmp_path / "backend.whl",
        "codex-freecad",
        "0.9.0",
        ["mcp==2.3.0"],
        source_members(ROOT / "src/codex_freecad", "codex_freecad"),
    )
    host = wheel(
        tmp_path / "host.whl",
        "freecad-mcp-host",
        config["project"]["version"],
        dependencies,
        source_members(ROOT / "framework-host/src/freecad_mcp_host", "freecad_mcp_host"),
    )
    return tmp_path, backend, host, framework_version


def test_verified_framework_wheel_must_preserve_mcp23(wheels):
    root, backend, host, framework_version = wheels
    framework = wheel(
        root / "framework.whl", "universal-codex-tools", framework_version, ["mcp==2.3.0"]
    )
    digest = hashlib.sha256(framework.read_bytes()).hexdigest()
    assert checks.verify(backend, host, framework, digest)["source_and_record_verified"]


def test_legacy_framework_and_wrong_digest_are_rejected_before_install(wheels):
    root, backend, host, framework_version = wheels
    framework = wheel(
        root / "legacy.whl", "universal-codex-tools", framework_version, ["mcp==1.30.0"]
    )
    with pytest.raises(ValueError, match="trusted SHA-256"):
        checks.verify(backend, host, framework, "0" * 64)
    digest = hashlib.sha256(framework.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="downgrades are not accepted"):
        checks.verify(backend, host, framework, digest)


def test_changed_wheel_member_is_rejected_by_record(wheels):
    _, backend, _, _ = wheels
    with zipfile.ZipFile(backend) as bundle:
        members = {name: bundle.read(name) for name in bundle.namelist()}
    members["codex_freecad/server.py"] += b"\n# Changed after build\n"
    with zipfile.ZipFile(backend, "w") as bundle:
        for name, content in members.items():
            bundle.writestr(name, content)
    with pytest.raises(ValueError, match="RECORD validation"):
        checks.inspect_wheel(backend)


def test_installed_package_readback_rejects_changed_bytes_and_extra_files(wheels):
    root, backend, host, framework_version = wheels
    framework = wheel(
        root / "framework.whl",
        "universal-codex-tools",
        framework_version,
        ["mcp==2.3.0"],
        {"universal_tools/__init__.py": b"# framework fixture\n"},
    )
    site = root / "site-packages"
    for package in (backend, host, framework):
        _, members = checks.inspect_wheel(package)
        for name, content in members.items():
            if ".dist-info/" not in name:
                target = site / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    digest = hashlib.sha256(framework.read_bytes()).hexdigest()
    assert checks.verify(backend, host, framework, digest, site_packages=site)[
        "installed_bytes_verified"
    ]
    extra = site / "freecad_mcp_host/extra.py"
    extra.write_text("# unexpected installed source")
    with pytest.raises(ValueError, match="Installed package differs"):
        checks.verify(backend, host, framework, digest, site_packages=site)
    extra.unlink()
    (site / "codex_freecad/server.py").write_text("# changed installed source")
    with pytest.raises(ValueError, match="Installed package differs"):
        checks.verify(backend, host, framework, digest, site_packages=site)
