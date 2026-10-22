# Standalone offline workflow

This connection inspects FCStd ZIP/XML metadata and bundled capability schemas. Begin with `freecad_offline_status`, then inspect an explicit FCStd path within the configured offline workspace. Pin the returned source SHA-256 with `expected_sha256` on later reads. Preserve original files.

FCStd inspection snapshots at most 64 MiB, bounds ZIP members and expanded bytes, verifies payload CRC/SHA-256 and reads Document.xml object names/types. It writes no files and never evaluates geometry, expressions, macros or saved Python proxies. ZIP/XML validity does not establish native recompute, geometry or FreeCAD acceptance.

Bundled capability schemas are reference data. This profile has no native invocation, edit, save, export, bridge, external-extension, shared-host, shell, SCM, controller or outgoing MCP transport. Environment variables cannot enable those routes. Native live and headless modes require their separately accepted connection profiles.

Four frontend slots and one active read per frontend bound admission. Windows lifetime containment permits only the root process. Closing input or losing the calling parent triggers bounded exit. No worker, external application or shared resource is attached, adopted or terminated. Root identity history is retained; abrupt exit can leave an active historical record. That record does not authorize manager termination or clearing uncertain work from another profile. Tray restart is unavailable; close the owning client connection.
