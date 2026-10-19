# FreeCAD MCP host

Experimental app-owned host using `universal-codex-tools==0.13.0` as a normal pinned dependency. It imports `universal_tools.framework`; framework implementation code is not vendored. Universal Tools plugin installation and a universal daemon are not required.

This package has its own environment because the framework pins MCP 1.30.0 while the CAD backend requires MCP 2.3.0. Do not install it into the main FreeCAD backend environment or FreeCAD's bundled Python. `requirements.lock` pins the reference host dependency closure. The framework wheel must come from a verified local build; no public feed is assumed.

See the repository's [framework development guide](../docs/FRAMEWORK.md) for setup, immutable publications, standalone packaging, tests and remaining acceptance gaps.
