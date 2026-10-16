"""Compatibility entry point for the reloadable native viewport controller."""

import importlib

from .panel import implementation


def __getattr__(name):
    if name != "JointDrag":
        raise AttributeError(name)
    return importlib.import_module(implementation().__name__ + ".viewport").JointDrag
