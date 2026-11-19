# Gateway–ESP32 B protocol v1

Implemented on 2026-11-18 after D012 approval. This is the current B contract;
historical proposal sections elsewhere do not override it. The full Member 1 /
operator integration is separate.

## Transport and context

B is a Wi-Fi station and TCP server (default port 5001). One connection owns
the server until it disconnects; another connection cannot replace it.
Each frame is a four-byte unsigned big-endian payload length followed by
1–1024 bytes of UTF-8 JSON. The prefix excludes itself. Requests are flat
objects; duplicate keys, malformed UTF-8/JSON, embedded NUL, and invalid
envelopes close the connection without inventing an acknowledgement ID.
Unknown fields on an otherwise trustworthy envelope produce a retained
INVALID_REQUEST rejection when admission can reserve its record.

Every request includes v=1, type, boot_id, batch_id and run_no, plus cmd_id for
commands or job_id for INSPECT. IDs and batch IDs are opaque ASCII
[A-Za-z0-9_:-], 1–96 characters. IDs are never rewritten. Gateway-originated
IDs use ACTION-GW-full_UUID4_session-per_action_counter, with minimum six-digit
counter padding. One allocator is shared through the B client.

boot_id is B's fresh random 128-bit boot identity, rendered as 32 lowercase
hexadecimal characters. It is distinct from the ID issuer session. run_no is
a positive uint32 fence scoped to that boot. A first valid CONFIGURE opens
exactly current_run_no+1 after the prior run is closed. Further configuration
uses the current run/batch. New runs use a new batch_id. Closed/retired scopes
cannot execute work again. Cached terminal replies for the most recently
closed run may be replayed until the next valid run opens.

The gateway learns current context from an unsolicited HEARTBEAT on connection.
No discovery command executes work. B emits heartbeats every 500 ms when the
bounded transmitter has room; the gateway treats 1.5 seconds without a valid
heartbeat as stale and stops new dispatch. Initial connection discovery has
three bounded one-second attempts, separated by 30 ms. Operation reconnects
are requested only by their operation controller and consume its bounds.

A valid heartbeat from the same receiver boot clears an obsolete transport
failure from an earlier connection. Failed/invalid greetings do not establish
freshness; a detected boot change remains latched until explicit recovery.
Reconnection does not reset operation identities, execution history or budgets.

## Requests

| type | Additional fields | Effect |
| --- | --- | --- |
| CONFIGURE | inspection_time_ms, N, K | Validate/apply settings and return actual settings/config_version. Reject BUSY during inspection. |
| INSPECT | part_id, config_version | Accept one inspection; require the expected applied configuration. |
| QUERY | target_id, query_no | Snapshot an existing command/job or return target:null (UNKNOWN). Never creates/starts the target. |
| CLOSE | none | Require idle, close the run, return result.closed=true. |

inspection_time_ms is 1–600000; N is 1–2147483647; K is
−2147483648–2147483647; part_id is 1–4294967295. Values must be JSON numbers
representing integers, never booleans. config_version is a positive uint32
assigned by B. query_no is a positive, monotonically increasing uint32 within
the receiver boot; heartbeat reports query_high_water for reconnect.

Example configuration (IDs shortened only for readability):

```json
{"v":1,"type":"CONFIGURE","cmd_id":"cfg-example","boot_id":"0123456789abcdef0123456789abcdef","batch_id":"batch-example","run_no":1,"inspection_time_ms":100,"N":3,"K":-1}
```

B computes FAIL exactly when (int64(part_id)+K) modulo N is zero; otherwise
PASS. Only B computes the production verdict. A job freezes applied settings
and version at acceptance. Timers continue through Wi-Fi/TCP loss and blocked
transmission. The firmware polls at 20 ms, so the configured duration is a
minimum with scheduler granularity, not a hard real-time promise.

## Replies and retained evidence

Normal requests produce RECEIVED, ACCEPTED, COMPLETED: three replies total.
Each echoes its original ID, action, boot_id, batch_id and run_no; inspection
replies also identify part_id. A record exists before RECEIVED. Rejection
produces REJECTED/error and never starts work.

COMPLETED includes result for CONFIGURE/INSPECT/CLOSE. result contains the
original identity/context, state, applied settings/version, and elapsed_ms;
inspection adds the explicit verdict, while CLOSE adds closed:true. A QUERY
completion carries its own cmd_id/query_no/target_id and a separate target
snapshot. Target state is RECEIVED, IN_PROGRESS, REJECTED, or COMPLETED.

Duplicate execution requests return existing STATUS/result/rejection. A
canonical SHA256 fingerprint ignores object-key order and formatting; a
changed request under the same ID produces ERROR/ID_CONFLICT and preserves
the original record. A fresh ID cannot inspect an already accepted part in
the same run. Rejected operations remain rejected; changing/reissuing work
requires a new ID.

Completion is cached before nonblocking publication. If the four-frame TX
queue is full/disconnected, an unsent outcome remains pending in its record.
This is deferred initial transmission, not an autonomous acknowledgement/
retry protocol. Once queued, recovery is owned by the gateway. TCP reconnect
resets framing/TX state only, never application history or inspection timers.

There are 64 job records (including distinct rejected inspection requests),
16 configuration/close records (one slot reserved for CLOSE), and eight
query snapshots. Job/configuration outcomes remain through the run, including
closure until the next valid run. Query snapshot eviction retains a monotonic
high-water fence: an evicted old query is refused, never reevaluated. Pending
query transmissions are not evicted. No accepted record is evicted to admit
work. HISTORY_FULL refuses admission before RECEIVED/acceptance; it is not a
product verdict. A run supports up to 64 accepted inspections if distinct
rejected jobs have not consumed those slots. Exhausted initial configuration
admission history requires explicit maintenance/restart, not silent eviction.

History is RAM-only. Receiver reboot invalidates old boot-scoped requests.
It does not establish whether a previously accepted job completed. The
gateway enters Fault and never silently readdresses/reexecutes old work.

## Gateway operation controller

The approved initial profile is configurable:

| Limit | Value |
| --- | --- |
| Receipt | 1 second per initial/retransmitted request response window |
| Acceptance | 1 second from first delivery evidence |
| Completion | configured execution duration + 2 seconds from first acceptance evidence |
| Request retransmissions before acceptance | at most 2, preserving identical original bytes |
| Read-only recovery queries | at most 2, each with a unique query command ID |
| Query response window | 1 second |
| Absolute cap | configured duration + 10 seconds from initial controller submission |

Commands use zero configured execution duration. A query never recursively
starts more recovery queries. Attempt budgets and the absolute cap do not
reset on reconnect, duplicate ACKs, PENDING_VALIDATION, or IN_PROGRESS.
Only the first evidence establishes a phase anchor. A valid later stage can
establish earlier facts without inventing observed ACK timestamps. The
controller distinguishes COMPLETED, REJECTED and UNRESOLVED.

Results must match boot, run, batch, action, original ID, part and applied
configuration. Inspection results must include PASS/FAIL and a plausible
elapsed duration. Accepted results arrive within the original absolute cap;
later evidence is for explicit reconciliation, never a new run's counts.
Conflicting terminal evidence stops dispatch, preserves the original outcome,
and requires explicit reconciliation. No timeout/technical error becomes FAIL.

## Gateway queue and integration API

gateway.inspection.InspectionGateway owns inspection state and accounting.
Queue capacity (1–64) and full policy (block or fault) are required explicit
settings. The standalone test example chooses capacity two/block; it does
not silently fix the whole project's policy.

Call reserve_part BEFORE issuing production on A. It reserves waiting space
and allocates a durable globally increasing numeric part ID in SQLite.
Use that part ID throughout production, inspection and results. Call
produced(ticket) only after the actual matching production completion;
duplicate callbacks are harmless. Already reserved production completions
are retained during Fault, but no new inspections dispatch.

One worker sends one inspection at a time. SQLite/evidence file work runs in
worker threads; those threads never read sockets or retry operations. A Fault
is rechecked after persistence and before submission. Valid results count
once. Unresolved work stops dispatch. reconcile(job_id) is read-only and
does not resume; resume_after_reconciliation is explicit and requires fresh,
same-boot idle/run evidence. close_incomplete explicitly queries unresolved
work and seals an idle run before another batch. Unknown results remain
unknown in history. shutdown is terminal cleanup, not an operator Pause.

Gateway restart does not transparently restore execution. The SQLite ledger
preserves IDs/evidence and the part counter; if B still has an open run,
start_run refuses a new batch. Inspect the recorded context, query it
read-only, and explicitly close/reconcile. A new B boot requires reviewing
the old run as incomplete. Full operator Start/Pause/Resume/Stop and A serial
integration remain separate tasks; do not equate inspection completion with
an already demonstrated whole-system batch.

## A integration extension: identified RETIRE

The 2026-11-18 integration adds RETIRE while preserving existing v1 TCP
CONFIGURE/INSPECT/QUERY/CLOSE behavior. Both firmware profiles now compile
`shared/station`. The B source wrapper preserves its existing C harness API.

RETIRE has the common v/type/cmd_id/boot_id/batch_id/run_no fields and
target_id plus positive uint32 part_id. It reserves a record before RECEIVED,
then completes with a cached target outcome or returns retained BUSY for
an active target. A known completed target returns its real inspection result;
a known rejected target remains unchanged but receives a part fence. A safely
unknown target reserves a job tombstone with REJECTED/RETIRED and a part fence.
Neither the old ID nor a new ID for that part can trigger execution. The
target_id cannot equal RETIRE's own cmd_id. Target context conflicts reject.

Retirement commands have a separate 64-record pool, retained through explicit
idle closure. Tombstones consume the existing 64 job-record capacity. Extra
control attempts may exhaust the bounded pool and must not evict history.
The gateway then uses explicit incomplete-run closure instead of unsafe reuse.

For the 1024-byte limit, a retirement result carries its own normal identity,
state, elapsed_ms, target_id and part_id plus a compact target outcome. The
target repeats action/state/settings/configuration/elapsed/verdict or error,
but inherits job_id/batch_id/run_no/part_id from the enclosing result. It does
not repeat those fields on the wire. The gateway expands them after validating
the enclosing identity. QUERY of RETIRE returns the same immutable snapshot.
The result does not repeat RETIRE's unrelated current settings/version.

Gateway `InspectionGateway.isolate` performs explicit lookup/control before
same-batch continuation. It refuses UNKNOWN after known receipt/acceptance,
conflicting evidence, a different boot, or an active target. Retired unknowns
remain unresolved in reporting. `resume_after_reconciliation` can proceed
when all remaining unknowns have acknowledged fences. Whole-run incomplete
closure remains the fallback. No recovery progress renews the original budget.
Current verification supersedes the earlier 50-test count; see
`verification/station-integration/summary.json`. Hardware tests remain separate.
