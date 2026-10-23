"""Opt-in CMD/PowerShell subprocess fixtures; no installation, native CAD or live config."""

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.resource_process,
    pytest.mark.skipif(os.name != "nt", reason="Windows CMD"),
]


def launch(path, *arguments):
    # Quote the executable and each argument using the same documented CMD path syntax.
    command = subprocess.list2cmdline([str(path), *arguments])
    shell = subprocess.list2cmdline([os.environ.get("ComSpec", "cmd.exe")])
    return subprocess.run(
        f'{shell} /d /s /c "{command}"',
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


@pytest.mark.parametrize(
    "name,preset",
    [("Install.cmd", "InstallOnly"), ("Run.cmd", "SkipInstall"), ("Install-and-Run.cmd", None)],
)
def test_cmd_forwards_quoted_arguments_and_exit_status(tmp_path, name, preset):
    checkout = tmp_path / "Checkout with spaces & [CAD]!"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / name, checkout / name)
    (scripts / "InstallAndRun.ps1").write_text(
        """param([string]$Workspace, [string]$FreeCADCmd, [string]$FrameworkWheel, [string]$FrameworkSha256, [switch]$InstallOnly, [switch]$SkipInstall)
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
@{workspace=$Workspace; executable=$FreeCADCmd; wheel=$FrameworkWheel; sha=$FrameworkSha256; install=[bool]$InstallOnly; run=[bool]$SkipInstall} | ConvertTo-Json -Compress
exit 23
""",
        encoding="utf-8",
        newline="\r\n",
    )
    workspace = str(tmp_path / "CAD models & [fixtures]! Ω")
    executable = str(tmp_path / "Program Files" / "FreeCADCmd.exe")
    result = launch(checkout / name, "-Workspace", workspace, "-FreeCADCmd", executable)
    assert result.returncode == 23, result.stderr
    data = json.loads(result.stdout)
    assert data["workspace"] == workspace and data["executable"] == executable
    assert data["install"] is (preset == "InstallOnly")
    assert data["run"] is (preset == "SkipInstall")


def test_installer_forwards_framework_artifact_arguments(tmp_path):
    checkout = tmp_path / "Artifact arguments with spaces"
    (checkout / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "Install.cmd", checkout / "Install.cmd")
    (checkout / "scripts/InstallAndRun.ps1").write_text(
        "param([switch]$InstallOnly,[string]$FrameworkWheel,[string]$FrameworkSha256)\n"
        "@{wheel=$FrameworkWheel;sha=$FrameworkSha256;install=[bool]$InstallOnly}|ConvertTo-Json -Compress\n",
        encoding="utf-8",
        newline="\r\n",
    )
    wheel = str(tmp_path / "Verified wheels/framework.whl")
    digest = "a" * 64
    result = launch(checkout / "Install.cmd", "-FrameworkWheel", wheel, "-FrameworkSha256", digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"wheel": wheel, "sha": digest, "install": True}


@pytest.mark.parametrize("name", ["Install.cmd", "Run.cmd", "Install-and-Run.cmd"])
def test_real_launcher_help_has_no_install_or_native_side_effects(name):
    result = launch(ROOT / name, "-Help")
    assert result.returncode == 0 and not result.stdout, result
    assert "Usage:" in result.stderr and "-Workspace" in result.stderr


def test_real_launcher_reports_argument_failure_before_setup():
    result = launch(ROOT / "Install-and-Run.cmd", "-InstallOnly", "-SkipInstall")
    assert result.returncode == 1
    assert "Use either -InstallOnly or -SkipInstall" in result.stderr


@pytest.mark.parametrize("case", ["wrong-hash", "wrong-version"])
def test_setup_refuses_unreviewed_framework_before_environment_creation(tmp_path, case):
    checkout = tmp_path / "Disposable checkout with spaces"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/Setup.ps1", scripts / "Setup.ps1")
    wheel = tmp_path / "framework fixture.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "universal_codex_tools-0.19.0.dist-info/METADATA",
            "Name: universal-codex-tools\nVersion: 0.19.0\n",
        )
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest() if case == "wrong-version" else "0" * 64
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(scripts / "Setup.ps1"),
            "-FrameworkWheel",
            str(wheel),
            "-FrameworkSha256",
            digest,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ, "CODEX_HOME": str(tmp_path / "unused isolated home")},
    )
    assert result.returncode != 0
    assert (
        "trusted SHA-256" in result.stderr
        if case == "wrong-hash"
        else "0.20.0 wheel" in result.stderr
    ), result.stderr
    assert not (checkout / ".venv").exists() and not (checkout / ".local").exists()
