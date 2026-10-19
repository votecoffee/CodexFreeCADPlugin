# FreeCAD MCP host

Experimental app-owned host using `universal-codex-tools==0.13.0` as a normal pinned dependency. It imports `universal_tools.framework`; framework implementation code is not vendored. Universal Tools plugin installation and a universal daemon are not required.

MCP **2.3.0 is required** for this host and the CAD backend. The originally supplied framework 0.13.0 wheel pins MCP 1.30.0 and cannot satisfy this target. Integration is blocked until an updated framework wheel/version is selected and the dependency lock is regenerated. Do not downgrade MCP or use `--no-deps` to force the legacy framework into an incompatible environment. No public feed is assumed.

See the repository's [framework development guide](../docs/FRAMEWORK.md) for setup, immutable publications, standalone packaging, tests and remaining acceptance gaps.
