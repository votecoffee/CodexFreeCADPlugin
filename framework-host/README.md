# FreeCAD MCP host

Experimental app-owned host using `universal-codex-tools==0.18.0` as a normal pinned dependency. It imports `universal_tools.framework`; framework implementation code is not vendored. Universal Tools plugin installation and a universal daemon are not required.

MCP **2.3.0 is required** for this host and the CAD backend. `requirements.lock` pins the reference host runtime, including framework 0.18.0. Use a verified local wheel or explicit editable framework checkout; no public feed is assumed. Do not downgrade MCP or force SDK 1.x dependencies into this environment. Keep FreeCAD's bundled native Python independent of these host dependencies.

See the repository's [framework development guide](../docs/FRAMEWORK.md) for setup, immutable publications, standalone packaging, tests and remaining acceptance gaps.
