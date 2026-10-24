# Developing usable multi-chat connections

Apply the shared [connection readiness contract](https://github.com/votecoffee/CodexMCPBroker/blob/main/docs/server-development/connection-readiness.md).
Package installation, fresh protocol use, concurrent availability, host activation
and native CAD acceptance are separate evidence layers. Keep actual process
identities, settings backups, measurements and personal reports outside Git.

## Connection and native budgets

Multiple open chats are ordinary demand. The native standalone profile supports
16 simultaneous cold metadata connections, including a reconnect burst. Each new
root initially has a **128 MiB committed-memory job limit**, giving at most 2 GiB
for 16 metadata-only jobs. Measure private commit and job peak, not only working
set. These are enforceable Windows job limits, not an estimate of total system RSS.
See [Microsoft's job-memory contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).

Native work still requires the original shared **one-owner native lease**. Idle
metadata/guidance never takes it. Native admission removes the metadata memory
limit before calling the backend, retaining the original CAD memory policy and
four-process job bound. This release adds no native memory ceiling and does not
claim a global 2 GiB bound while native work or legacy generations exist. There
is no native waiting queue: competing native calls return a meaningful busy error.
Uncertain memory-policy readback retains admission and blocks dispatch/replay.

The connection pool is `metadata-frontdoors-v2`; earlier four-slot `frontends`
and `native-frontends` leases belong to their live legacy owners. Never clear,
reinterpret or bypass those owners' locks. During transition there can be at
most 16 new supervisors plus four legacy supervisors. Each native-profile job
has a four-process kernel bound: 80 processes is the conservative aggregate job
ceiling across 20 such jobs. The application policy permits one native owner,
normally at most 20 supervisors plus its three private descendants. External or
attached FreeCAD GUIs are excluded from owned-job counts and termination rights.
After old chats close naturally, normal demand uses only the 16 new connections.

`get_native_workflow` reports its own slot, occupancy, native capacity, configured
memory limit and observed job peak. Occupancy is a sampled OS-lock observation,
not a claim that native CAD is healthy. Excess connections refuse explicitly;
capacity is finite. Supporting more than the documented workload requires a new
measured design review, rather than a hidden cap increase.

## Diagnose before changing capacity

Match slot files to actual OS holders and retained process creation identities.
Check the pinned process handle, parent, current job observations and native
lease. An existing lock file alone is not a live owner. A live idle SDK frontend
is not a stale leak. Unknown ownership and uncertain native receipts stay unknown.
Do not terminate another chat, delete reservations, replay writes or launch CAD
to make a health probe pass.

Record the exact exhausted pool, selected/running versions, configured limit,
observed owners and safe next action. A successful two-client fixture does not
establish availability for the documented 16-chat workload. Strictly parse the
actual saved settings and test their unchanged command/args/cwd/environment with
the real SDK and the host's configured timeout.

## Required regression proof

- Cold initialize, full discovery, current guide and a trivial synthetic hash
  read; 16 overlapping clients, then bounded excess refusal and reconnect.
- Legacy leases and live old generations survive immutable selection updates.
  Metadata alone owns zero native leases and has no private child processes.
- Measure per-job committed-memory limits and peaks for every admitted client.
  A harmless allocation fixture proves limit refusal and native-policy readback;
  it does not establish native model acceptance.
- Idle EOF, EOF while startup waits for the bounded history lock, failed startup,
  busy native admission, and active harmless ownership close must release only
  exact private resources. Wait for lock acquisition only; never retry a body.
- Kill the exact private test parent with a valid pipe writer retained. Record
  the trigger, writer-handle validity, exit status and timestamps before asserts
  or safety cleanup. Retain every observed actor's original process handle and
  require its signaled state; a query error is not proof of exit.
- Preserve live peers, shared/attached references, before-images, uncertainty
  barriers and receipts across owner loss. Check native dispatch did not occur.
- Verify the installed immutable selection and saved-route behavior after
  publication. Then obtain actual host-chat tool discovery separately. Rebooting
  does not repair missing launchers, exhausted pools or retained uncertainty.

Use disposable roots and harmless Python actors for transport/resource tests.
Native geometry, live GUI work and customer jobs retain their own acceptance
requirements. Keep the framework/SDK pins unchanged during this repair.
