"""Copy the dependency-free native runtime and its installed extensions for demos."""

import shutil
from pathlib import Path

MODULES = (
    "__init__",
    "engine",
    "assemblies",
    "motion",
    "interference",
    "viewport",
    "panel",
    "bridge",
    "client",
    "worker",
    "features",
    "parameters",
    "patterns",
    "sketches",
    "extension_runtime",
    "extension_schema",
    "native_package",
)


def copy_native_package(destination):
    source = Path(__file__).resolve().parent
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in MODULES:
        shutil.copy2(source / (name + ".py"), destination / (name + ".py"))
    shutil.copytree(
        source / "extensions",
        destination / "extensions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
