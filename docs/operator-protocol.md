# Operator HTTP/WebSocket contract

Active Milestone 1 contract, 2026-11-18. This supersedes the proposal in
Member 3's original handoff, examples and mock gateway. The official PDF
remains the requirements authority; the team guide is a proposal.

## Run the integrated project

Use Python 3.11 or newer, from the repository root:

```powershell
python -m pip install -r gateway/operator/requirements.txt
python -B -m gateway.operator COM5 192.168.137.20 --state-file gateway.sqlite3
```

Replace COM5 and the IP with the identified A port and B address. Open
http://127.0.0.1:8080 in a browser. One server process owns both station links;
do not simultaneously run the older station CLIs on those links. The default
listener is local. Device Wi-Fi provisioning, physical USB/Wi-Fi validation,
raw transport captures and threshold calibration are separate hardware work.
The serial/TCP firmware is unchanged by this operator integration.

For an explicitly labelled SOFTWARE preview, with MSVC installed:

```powershell
python -B tools/run_operator_preview.py --state-file operator-preview.sqlite3
```

This uses the actual A/B C application code through native localhost peers.
It opens no physical COM port and has no automatic mock fallback. Optional
`--drop-first-production` with a fresh state file exercises unresolved-part
recovery. Stop the preview with Ctrl+C. The contributor mock remains a
standalone design artifact, not the integrated server.

## Jobs, the same batch, and a new batch

| Control | Current individual station jobs | Remaining work | Batch identity |
| --- | --- | --- | --- |
| Start | Configure both stations before dispatch | New target and queue policy | New batch and fresh durable part numbers |
| Pause | Already submitted work remains owned by its controller; accepted jobs finish | No new A or B dispatch; queued parts retained | Same batch |
| Resume | Requires fresh original-boot/current-run evidence and no unfenced uncertainty | Continues remaining original target | Same batch, IDs and results retained |
| Stop | Finish current jobs, then bounded recovery and confirmed scope closure | Does not inspect waiting inventory or start dependent work | Ends old batch; another Start creates a new one |
| Screen loss | Current accepted jobs finish | Automatic dispatch pause after lease expires | Explicit Resume after resynchronization |

Pause completion confirms dispatch gates, not that current station jobs have
already finished. Stop is not an emergency cancellation. If closure cannot
be established, the gateway retains Fault and exposes recovery. PASS/FAIL
counts always remain actual confirmed B results. Missing work is automatically
reported as INCOMPLETE, alongside unresolved, not-started and not-inspected
counts; these categories can overlap and must not be summed as disjoint totals.

While Paused and both stations are fresh/idle in the current run, Apply settings
confirms identified configurations on both stations before Resume. Past jobs
and their verdicts retain frozen settings. Queued jobs not yet submitted to B
use the updated rule/timing. A partial configuration failure holds Fault;
it never silently resumes. Continue is also blocked after a partial
configuration change; end this batch before starting work under newly confirmed
settings. Batch target, capacity and full policy remain fixed.
The examiner can initially choose batch size 1-64, times 1-600000 ms, N from
1 to 2147483647, K from -2147483648 to 2147483647, capacity 1-64, and Wait/Fault.

## Mutations and correlation

All controls use HTTP POST `/api/{action}` with JSON, up to 4096 bytes.
Actions: `start`, `pause`, `resume`, `stop`, `configure`, `reconcile`,
`continue`, `recover_a`, `recover_b`, `close_orphans`.

Every request has exactly `schema_version:1`, `gateway_id`, `operator_id`,
`cmd_id`, plus the fields below. IDs use `[A-Za-z0-9_:-]`, length 1-96.

| Action | Additional fields |
| --- | --- |
| start | batch_size, production_time_ms, inspection_time_ms, N, K, queue_capacity, full_policy (`block` or `fault`) |
| configure | batch_id, batch_size (unchanged), production_time_ms, inspection_time_ms, N, K |
| All other actions | batch_id (null for close_orphans without a gateway-owned batch) |

The browser issues action/issuer/random-session/per-action-counter identities.
The gateway registers a request before reporting receipt. A matching HTTP 202
ack has schema_version, gateway_id, cmd_id, command, accepted:true,
phase:accepted, message, completion_window_ms. Acceptance is separate from
completion and Start completion is separate from batch completion. Registered
rejections retain the original identity and ack. Invalid envelope, stale boot,
missing controller lease and identity conflicts may be rejected before admission.

Same ID and contents return the cached ack without execution. Changed contents
or action under the same ID return ID_CONFLICT. Read-only GET
`/api/commands/{cmd_id}` returns the current phase/result and observed local
received_at, accepted_at, completed_at, absolute_at timestamps (gateway-loop
monotonic seconds; they are not wall-clock times or station ACK timestamps).
Phases are received, accepted, completed, rejected and unresolved. A failed
accepted workflow becomes unresolved/Fault, never a fabricated pre-execution
rejection. Recent 100 results are in snapshots; all admitted IDs are retained
for this gateway boot, with a 10000-record admission bound and no eviction.

The browser sends at most twice, with identical serialized contents, each
response window at most four seconds and an absolute send limit of 8.5 seconds.
Reload does not replay saved mutations. Exhaustion uses read-only lookup.
Server controls have immutable finite completion limits: 35 seconds normally,
65 for Continue/old-scope closure, and maximum configured station duration plus
90 seconds for Stop. Progress and lookups do not renew original budgets.
Underlying station operations keep the approved three-stage bounded controller.

## Full status and operator liveness

GET `/api/status` and WebSocket `/ws/status` publish the same complete status
schema. WebSocket emits approximately every 200 ms; it does not carry controls.
Browser reconnect performs GET synchronization, orders buffered newer snapshots,
rejects duplicate/older sequence numbers under one boot, and freezes stale data.
There is no optimistic work completion or client-calculated verdict.

Snapshots include gateway_id/status_seq, simulation, Idle/Running/Paused/Fault,
fault reason, applied settings, batch identity/target/outcome/elapsed_ms,
confirmed counters, actual assigned parts and immutable result evidence,
queue inventory/capacity/reservations, A/B freshness/busy/phase/estimated remaining
time/boot, recent command results, pending control, recovery and edit readiness.
Unassigned target slots have no fabricated part ID. A countdown reaching zero
only displays "Awaiting gateway completion"; it never changes counters.

After each advancing valid snapshot, the browser sends only:

```json
{"type":"alive","operator_id":"OP-example","gateway_id":"GW-example","status_seq":12}
```

One operator lease owns controls; other panels can view. The initial lease is
five seconds (`--operator-stale-seconds`); duplicate sequence acknowledgements
do not renew it. Browser data becomes stale after 3.5 seconds without an
advancing snapshot. Lease expiry gates new work and reconnect never resumes
it automatically. These are initial engineering values pending hardware tests.
Same-origin browser controls/WS are enforced; authentication/TLS remain the
project's later security scope. The server uses one process, without reload or
multiple workers that could create competing device owners.

## Recovery, history and evidence

Check results uses identified read-only station lookup. Continue remaining
requires fresh same-boot/current-run idle evidence and approved per-job
retirement/fencing before reuse. Unknown work never becomes FAIL or replacement
work. End incomplete batch performs the Stop workflow. Recover restarted A/B
explicitly binds a proven different idle boot; close the old batch before Start.

A gateway restart creates a new gateway identity and does not replay old HTTP
requests or restore execution automatically. Retained station runs appear as
Fault, with explicit Close old station runs available only when both stations
are fresh/idle. Closing these scopes does not reconstruct missing old results.
The new session's empty batch is not a claim that the previous batch completed.
Keep the same SQLite state file: durable numeric part allocation and detailed
request/outcome/accounting/control events survive. Do not delete it to bypass
recovery. The screen's batch-evidence JSON and browser-log download supplement
this ledger; they do not replace required raw serial/network hardware captures.

## Validation limits

75 existing native station/controller/transport tests, 12 operator/native-peer
HTTP/WS tests and nine Node frontend/protocol/render checks passed (96 total).
Visual browser inspection remains blocked by the unavailable browser access
host; no desktop/mobile screenshot or physical-board result is claimed.
See verification/operator and verification/station-integration for evidence.
