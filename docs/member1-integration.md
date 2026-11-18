# Member 1 integration

The A–gateway subsystem is implemented on main under D013–D017. The user's
2026-11-18 approval finalized the remaining bounds, recovery profile and
identified retirement behavior. No A-specific behavior question blocks this
implementation. Numerical heartbeat/deadline values remain initial settings
for hardware calibration. Whole-system operator Pause/Stop and Member 3 UI
integration remain separate decisions/work.

## Active implementation

- A firmware: `member1/production-a/firmware/main/main.c`, `serial_service.c`
  and the contributed `protocol.c` implement USB UART0 at 115200 8N1 with
  SLIP/ATR/CRC. Test ID zero carries the integrated JSON contract. Nonzero
  test IDs retain XOR-a5 regression behavior. Max JSON payload is 1024 bytes.
- `shared/station` owns strict parsing, canonical request fingerprints,
  queryable receipt records, independent timers, immutable outcomes, full-run
  history, explicit boot/run fences and RETIRE. A and B compile this same
  implementation; their transport adapters and result types remain distinct.
- `gateway/production` owns A's client/validator, one serial I/O worker, and
  the integrated `BatchGateway`. The existing operation controller owns every
  application deadline/retry/query. ATR sequences label attempts; cmd/job IDs
  retain logical identity across retries. The old synchronous retry client is
  preserved as contributor history and is not nested under the gateway.
- A returns `produced: true`, never an inspection verdict. Only matching,
  validated A completion releases that same numeric part/batch to B. B alone
  calculates PASS/FAIL using its frozen examiner-supplied settings.

## Approved contract

Opaque IDs accept 1–96 ASCII letters/digits/underscore/colon/hyphen. Keep the
shared origin/session/action counter format. No application op_no or required
ID suffix remains. A has a fresh 32-hex boot identity from enabled physical
entropy before Wi-Fi/RF use; old work is never rebound automatically to it.

One run supports up to 64 distinct job records, including retained rejections
and unknown-job retirement fences. Sixteen configuration/closure records
reserve the final slot for CLOSE. Eight query snapshots use a monotonic
query_no fence. A separate 64-record retirement pool prevents ordinary
configuration capacity from being consumed by a retirement per target part.
Full history refuses admission; no still-valid outcome/fence is evicted.
An explicitly acknowledged idle CLOSE invalidates the old scope; the next
CONFIGURE opens run_no + 1. Receiver history is RAM-only and boot-scoped.

Production time is runtime-configurable in 1–600000 ms. part_id is a gateway-
allocated positive uint32, persisted in SQLite and unchanged through A/B.
These numeric bounds are our agreed validation limits, not numbers specified
by the PDF. Each accepted job freezes its applied duration/config_version.
Reconfiguration during an active job returns retained BUSY; an idle
configuration must complete before dependent work is sent.

A has one active job and no hidden accepted-job queue. The gateway reserves
inspection waiting space before production, applies the configured block/Fault
full policy, and runs A/B concurrently on different parts. Waiting for queue
space occurs before starting a job and never stretches its configured duration.

The initial operation profile is receipt 1 s, acceptance 1 s from first
delivery evidence, completion configured duration + 2 s from first acceptance
evidence, at most two original-request retransmissions before acceptance and
two read-only recovery queries with 1 s response windows, and an absolute
duration + 10 s limit from first submission. Later progress cannot reset
anchors/budgets or invent missing ACK observation timestamps. Explicit later
lookup/control is recorded separately from the exhausted original operation.

A initially emits a heartbeat every 1 s and becomes stale at 5 s without a
fresh increasing heartbeat. Serial I/O failure is independent evidence and can
hold dispatch earlier. Duplicate heartbeats and ordinary replies do not refresh
A liveness. B retains its initial 500 ms / 1.5 s profile. Calibration will tune
these initial numbers with real USB/Wi-Fi load; bounded recovery and explicit
continuation remain invariants. Physical drivers can still toggle control lines
when opening a port despite requested DTR/RTS settings; boot fencing detects
that event instead of assuming reconnect preserved the boot.

## Guarded continuation and closure

Bounded unresolved work causes a Fault/dispatch hold. Known queued parts on
healthy B can finish while A is held. No unconfirmed A production is inspected.
The operator-facing core offers explicit lookup, Continue remaining, and
incomplete closure; reconnect alone never resumes dispatch.

Continue remaining establishes fresh same-boot/current-run idle readiness,
does a read-only lookup and, where needed, an identified RETIRE command. A
completed target returns its real outcome; an active target returns BUSY and
continues. A safely unknown target receives retained original-ID and part
fences. A known rejection remains immutable and receives a part fence.
Unknowns are never recreated under new IDs to fake the original target count.
Reservation release occurs only after A's fence is acknowledged. Delayed
original or fresh-ID execution for a fenced part cannot produce/inspect it.
Retirement has its own cached result and bounded controller; QUERY is read-only.

Known receipt/acceptance followed by UNKNOWN is inconsistent history, not
proof of nonexecution. Guarded continuation refuses it. Explicit incomplete
closure fences both old scopes once inactive, without requiring the missing
result/root cause. A genuine restart can be bound explicitly with
`bind_restarted_station` only to a different fresh idle boot with no open run;
this requires incomplete closure before another batch. It never replays old
requests on the new boot. Partial closure keeps Fault and confirmed station
closure evidence; later explicit lookup recovers a missing close reply.

Snapshots always retain target, produced, inspected, PASS, FAIL, unresolved,
unstarted and not-inspected counts. Example: target 10, nine inspected = six
PASS + three FAIL + one unresolved means INCOMPLETE with those actual totals.
The GUI must display these computed facts, not request a manual INCOMPLETE
label. A live batch may run with isolated unresolved work; that uncertainty
does not become FAIL or permanently block other target parts/future batches.

## Run and verify

Install `gateway/production/requirements.txt`, then from the repository root:

```powershell
python -B -m gateway.production COM5 B_CURRENT_IP --parts 6 --production-ms 100 --inspection-ms 150 --rule-n 3 --rule-k -1 --queue-capacity 2 --full-policy block --state-file batch-test.sqlite3
```

COM5 is an example only: identify A's actual port and B's current address.
The command uses real station clients; it does not simulate A production.
It runs a normal batch and closes both scopes; on a Fault it retains evidence
and requires explicit recovery through the core API/operator integration.
It does not silently reset/flash boards or abandon an open run.

Software verification (native MSVC C11 /W4 /WX, real C application and Python):

```powershell
python -B tools/verify_station_integration.py
```

Results and source hashes are in `verification/station-integration/`: 75
passing tests (53 B/controller/transport, 19 A/integrated/CLI, three serial-worker).
The native serial harness replaces only UART byte I/O with a local socket;
it compiles A's actual CRC/SLIP/service and the shared application/parser.
B's native harness compiles its actual TCP service and same application.
This proves software behavior, not USB electronics, RF timing or GUI behavior.
Contributor results/old pc_test application helpers remain historical evidence
for commit 58622a0 and are not integration test results for the new contract.

ESP-IDF v6.1.1 builds are recorded in
`verification/station-integration/firmware-builds.json`. Source staging preserves
the repository hierarchy so A/B relative shared-source references resolve.
Use an explicit absolute build directory (or cd to the project first).
The A main task requires 8192 stack bytes. B build credentials are nonsecret
placeholders and must be configured locally before a hardware exercise.
No physical port was opened, board flashed/reset, or hardware PASS claimed.

Before hardware approval, test startup/reconnect/boot identity, UART sustained
TX and timer independence, heartbeat/stale windows under both speed ratios,
unplug/replug, duplicate/late frames, A/B restart, queue full policy, retained
results/retirement and incomplete-to-new-batch recovery. Capture actual USB
and TCP traffic; include heap/stack headroom and load when calibrating numbers.
Member 2's assigned tester should use the updated main firmware for RETIRE.
