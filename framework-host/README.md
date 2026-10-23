# FreeCAD MCP host

The shared library and a separate Windows management app live in
[CodexMCPBroker](https://github.com/votecoffee/CodexMCPBroker). This repository owns FreeCAD's
standalone MCP server, app-owned plugin and skills; no universal plugin is installed.

Experimental app-owned host using `universal-codex-tools==0.20.0` as a normal pinned dependency. It imports `universal_tools.framework`; framework implementation code is not vendored. FreeCAD retains its own plugin and native skills; the shared framework and independent manager do not deploy a universal plugin.

MCP **2.3.0 is required** for this host and the CAD backend. `requirements.lock` pins the source target runtime, including framework 0.20.0. Use a verified local wheel or explicit editable framework checkout; no public feed is assumed. Do not downgrade MCP or force SDK 1.x dependencies into this environment. Keep FreeCAD's bundled native Python independent of these host dependencies.

See the repository's [framework development guide](../docs/FRAMEWORK.md) for setup, immutable publications, standalone packaging, tests and remaining acceptance gaps.
