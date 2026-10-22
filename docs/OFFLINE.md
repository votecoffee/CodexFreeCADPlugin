# Standalone offline profile

The `direct-standalone-offline` candidate is a read-only FreeCAD file inspection connection. It provides four tools: `freecad_offline_status`, `get_offline_workflow`, `list_bundled_capabilities` and `inspect_fcstd_package`.

FCStd inspection captures at most 64 MiB of source bytes, verifies bounded ZIP payload CRC/SHA-256 and reads Document.xml object names/types. It accepts files only within its configured workspace. Archive paths, unsupported compression/encryption, XML declarations/entities, expanded byte counts and object counts are checked before returning metadata. No archive is extracted and no input file is written. These checks do not prove geometry validity, native recompute or FreeCAD acceptance.

Bundled capability schemas are static references. Handlers are never imported or invoked. This connection exposes no model edit/save/export, native FreeCAD, bridge attachment, external extension, outgoing MCP, shared host, shell, SCM or controller route. Environment variables such as `FREECAD_CMD` and extension/runtime paths do not add routes. Unsupported native/shared-host command-line arguments fail before server creation. Other application profiles retain their separate acceptance requirements.

## Prepare a candidate

Build the application wheel from committed source. Assemble a separate, audited runtime from that wheel, the reviewed framework `0.20.0`, MCP `2.3.0` and the exact dependency snapshot in `framework-host/requirements.lock`. Preserve wheel hashes and source/RECORD checks. Use a fresh local directory, without editable installations, symlinks, junctions or bytecode caches.

Generate a separate connection, using existing workspace and runtime directories:

```powershell
.\.venv\Scripts\python.exe -B -m codex_freecad.offline_setup --workspace models --runtime local\offline-candidate\runtime --output local\offline-candidate\connection
```

Generation writes a plugin, its own offline skill, a fixed release manifest and a hash-pinned bootstrap/closure. It does not start a service, install/enable the plugin or change selected runtime/cache/configuration. Existing setup/installer routes remain unchanged. Candidate review and runtime canary authorization are separate steps.

The plugin directly names the real base installation's paired **pythonw.exe** with `-I -S -B`; there is no virtualenv redirector, console Python, shell, Node wrapper or child worker. The generator checks its Windows GUI PE subsystem and matching architecture; console and redirector overrides are refused. A console Python root can acquire an OS console host before the app's job guard, even with `CREATE_NO_WINDOW`; that earlier candidate failed its zero-child canary and remains held.

The bootstrap verifies its minimal standard-library-only guard code and the windowless root image, then validates inherited stdin/stdout pipe handles. It binds strict UTF-8 text streams, reconstructing missing `sys.stdin`/`sys.stdout`/`sys.stderr` from duplicated inherited handles without allocating or attaching a console. CRT descriptors 0/1/2 remain available for normal SDK claims; stderr requires a retained file/pipe sink. Unsupported/missing handles fail closed. Harmless fixtures explicitly check non-ASCII input/output/stderr, real EOF and missing Python stream objects; a `--version` probe does not establish this contract.

Next the bootstrap obtains an admission slot and one-process Windows job/EOF-parent guard before hashing/importing the remaining dependencies. Unverified runtime changes and bytecode caches fail closed. Only known pywin32 search paths/bootstrap are selected; `.pth` files, environment Python paths and user site packages are not executed. The supported serving entry is the generated windowless connection; manual console and redirector roots fail before server creation.

## Lifetime and retained evidence

Four OS-locked frontend slots, one active read per frontend and a bounded retained session history limit admission. The surviving stdio root captures its own host/PID/creation/image identity and generation in a durable session record before manager/protocol work. It is not registered as a fictitious child resource. The root launches zero application processes; its Windows job denies child creation.

The in-process manager endpoint reports cached version/admission state and refuses restart. Normal shutdown closes registration and records session completion before hard exit. EOF/parent loss has a ten-second cleanup grace; root exit/crash releases OS slot/job handles. Abrupt death can leave an active historical identity/manager record, which is retained. There are no owned child resources for manager orphan termination. Existing attached/shared/dirty/uncertain native work is never loaded, adopted, replayed, cleared or terminated.

The parent-only watcher uses its own duplicate of the retained parent process handle and a separate thread. It never calls a pipe API. A synchronous [PeekNamedPipe can block in multithreaded code](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe), so sharing the EOF observer's thread could hide parent death while an external writer keeps the pipe open. The older combined observer failed that actual canary. Harmless source comparison fixtures hold the writer, block another thread on the same read pipe and observe parent death; they do not start MCP or engineering software. Partial thread-start failures retain correct handle ownership and fail closed.

Pure/stub checks and explicitly enabled harmless Python root fixtures test these source contracts. They do not establish actual MCP framing, installed cache loading, manager lifecycle or native operation. A disposable direct canary must separately check real startup, tools/read/schema refusal, source preservation, manager identity/status and EOF/owner death with the reviewed bytes. Native/headless/live/shared-host acceptance remains outside this profile.
