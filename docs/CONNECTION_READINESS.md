# Developing usable multi-chat connections

Apply the shared [connection readiness contract](https://github.com/votecoffee/CodexMCPBroker/blob/main/docs/server-development/connection-readiness.md).
Package installation, fresh protocol use, concurrent availability, host activation
and native CAD acceptance are separate evidence layers. Keep actual process
identities, settings backups, measurements and personal reports outside Git.

## Connection and native budgets

Multiple open chats are ordinary demand. The native standalone design budgets
**24 steady metadata connections and a full 24-connection reconnect overlap**.
All 48 connections use the same `metadata-frontdoors-v2` OS-lock pool, including
owners running release 26.1024.101538. Slots 0–15 retain their **128 MiB** job
commit limit; slots 16–47 use **96 MiB**. The complete metadata-only reservation
is **5 GiB** (16 × 128 + 32 × 96 MiB). The first 24 slots reserve 2.75 GiB.
This reduces the reservation per added slot, not the SDK's measured private commit.
Measure actual normal and transition totals, peaks and host available commit,
not only working set. These are Windows job limits, not estimates of system RSS.
See [Microsoft's job-memory contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).

Native work still requires the original shared **one-owner native lease**. Idle
metadata/guidance never takes it. Native admission removes the metadata memory
limit before calling the backend, retaining the original CAD memory policy and
four-process job bound. This release adds no native memory ceiling and does not
claim a global 5 GiB bound while native work or older legacy generations exist. There
is no native waiting queue: competing native calls return a meaningful busy error.
Uncertain memory-policy readback retains admission and blocks dispatch/replay.

The same pool and indices account for existing 26.1024.101538 and new owners;
never create another pool to hide their overlap. Earlier four-slot `frontends`
and `native-frontends` leases belong to their live legacy owners. Never clear,
reinterpret or bypass those owners' locks. During transition there can be at
most 48 pool supervisors plus four older legacy supervisors. Each native-profile
job has a four-process kernel bound: **208 processes** is the conservative
aggregate job ceiling across 52 such jobs (192 across the 48 pool jobs alone).
Application policy permits one native owner: normally at most 48 supervisors plus
its three private descendants, or 52 plus three during older legacy transition.
These policy totals are not global kernel ceilings. External or
attached FreeCAD GUIs are excluded from owned-job counts and termination rights.
After older legacy chats close naturally, all demand uses the shared 48 slots.

`get_native_workflow` reports its own slot, occupancy, native capacity, configured
memory limit and observed job peak. It also reports sampled unavailable slot indices,
their tiered reservation and the full configured reservation. The sampled occupied
reservation is a metadata budget, not a measured aggregate memory limit when a
native owner has restored its original policy. Occupancy is an OS-lock observation,
not a claim that native CAD is healthy. Excess connections refuse explicitly;
capacity is finite. Supporting more than the documented workload requires a new
measured design review, rather than a hidden cap increase.

Short framework registry transactions have a separate **5-second admission
deadline**. App-owned adapters serialize registry publication/reads and entry
to the original framework ledger lock. They keep the original ledger format,
path checks and native operation bodies. Only known lock-acquisition contention
can wait; publication, transaction and native bodies execute once. Unexpected
errors and uncertain outcomes propagate without replay. HTTP shutdown and backend
close calls are outside the publication lock; their ledger transactions retain
metadata admission. A simultaneous disconnect burst must
pass; sequential EOF alone does not establish this requirement. Live older
generations retain their original implementation and locks.
Private registry directories require the current user's ownership and the
user/SYSTEM ACL policy, pinned by filesystem identity. Existing correct ACLs are
read without recursive rewrites; foreign owners or ACLs refuse on first use.
New Windows directories receive the private owner/DACL in the kernel creation
call itself; there is no mkdir-then-path-ACL repair interval or replacement of
an existing target. A foreign object substituted before the first pin is refused
without permission or payload changes. Later replacement or permission drift refuses;
native data, receipts and transaction bodies are not repaired or replayed.

## Diagnose before changing capacity

Match slot files to actual OS holders and retained process creation identities.
Check the pinned process handle, parent, current job observations and native
lease. An existing lock file alone is not a live owner. A live idle SDK frontend
is not a stale leak. Unknown ownership and uncertain native receipts stay unknown.
Do not terminate another chat, delete reservations, replay writes or launch CAD
to make a health probe pass.

Record loaded/resumable chat demand, explicit headroom and reconnect demand before
choosing a finite steady/overlap target. Record the exact exhausted pool,
selected/running versions, configured limit,
observed owners and safe next action. A successful two-client fixture does not
establish availability for the documented 24-steady/24-reconnect workload. Strictly parse the
actual saved settings and test their unchanged command/args/cwd/environment with
the real SDK and the host's configured timeout.

## Required regression proof

- Cold initialize, full discovery, current guide and a trivial synthetic hash
  read; 48 overlapping clients, then bounded excess refusal and reconnect.
- Include 16 compatible old owners plus 32 new connections in the SAME pool,
  and prove an old observer's 16-slot view does not cause new accounting to omit them.
  Measure actual per-root private commit and process counts across steady and full
  overlap phases, including the test harness and preserved live peers separately.
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
