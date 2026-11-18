# Client status dispatch, late evidence and explicit different work

This implements the approved client-only follow-up to Step 5C. Firmware and
wire messages remain unchanged. There is no batch manager, inspection sender
or automatic batch abort/resume behavior.

## Public API

| API | Behavior |
| --- | --- |
| ProductionRun.read_status(timeout=1.0) | One read-only GET_STATUS, freshly correlated; returns query metadata and event |
| ProductionRun.observe(timeout=0.02) | Pumps heartbeats AND passively reconciles queued application evidence, even with a latched fault |
| ProductionRun.operation_evidence(op_no, boot_id=None) | Returns original retry outcome separately from confirmed-produced evidence; sends nothing |
| ProductionRun.assess_continuation(request, timeout=1.0) | Reports eligibility/reasons and fresh status; never arms or submits work |
| ProductionRun.produce_different(op_no, job_id, batch_id, part_id, timeout=1.0) | Explicit caller action; makes its OWN fresh assessment, then submits only that different part |
| StationDispatch.reconcile(item) | Validates retained frame evidence; no transmission, fault clearing or retry-budget changes |

Use a single synchronous reader. Do not call status/observe concurrently with
RetryController.execute or use another serial reader on the same port. The
dispatcher refuses while an operation is in flight. A station may itself be
busy when queried; read_status remains read-only and reports that condition.

### Read-only status and freshness

read_status keeps the EXISTING SessionGuard. It does not rediscover/rebind the
session, configure, produce, allocate an op_no or renew a retry budget. It
drains already-decoded old statuses/application frames through the observation/
reconciliation path, then sends a new GET_STATUS with a new ATR seq. It waits
under a finite monotonic timeout and handles interleaved heartbeat/late frames.

A qualifying response must have that query seq, valid STATUS fields and a
receive timestamp after the query and before its deadline. For the intended
boot its heartbeat counter cannot be older than the latest validated heartbeat.
Queued old status cannot qualify. Client ATR sequences are allocated once per
Python process, are not reused by new Client instances, and do not wrap.

A new boot may restart its heartbeat counter; its correlated fresh status can
be READ for observation without adopting that session or clearing RESTART.
Assessment will reject it for continuation of the old run. STATUS alone never
refreshes heartbeat liveness. If status cannot be confirmed, return/raise an
explicit timeout/error rather than assume idle. Timeouts clean their correlation
registration and do not send the production operation again.

### Outcome versus health

OperationUnresolved is a RetryStopped/RuntimeError, NOT a SessionFault.
RetryStopped.category distinguishes OPERATION_UNRESOLVED, OPERATION_REJECTED
and STATION_FAULT. StationOperationFault also remains a SessionFault. Existing
callers catching RetryStopped still work; callers that used `except SessionFault`
for every operation stop must now handle OperationUnresolved separately.

The separate SessionGuard remains the authority on availability/boot/fault.
An UNRESOLVED operation is not evidence the station is unavailable, not proof
that production failed, and not a batch-abort command. The normal run remains
disarmed after stopped work, even if the station is healthy.

### Passive late evidence

The ledger now has part_evidence and an append-only resolution_audit separate
from the original retry results. Reconciliation revalidates the full ATR/CRC,
JSON event and correlation metadata, then checks original boot/op number,
job/batch/part IDs, known attempt seq and PART_PRODUCED semantics (including
integer part ID and boolean replay flag). Unknown/mismatched/corrupt frames
are recorded as rejected evidence, not confirmations. Frames are not credited
just because JSON parsed.

A first valid late result appends PART_RESOLVED_LATE. The original timeout/
UNRESOLVED record, attempts, deadlines and spent budget remain byte-for-byte
unchanged in the ledger. Repeated original/replayed frames cannot add another
part confirmation. Known on-time parts use the same validation and count once.
Responses for stopped older operations can also be reconciled while a different
operation is waiting; they never satisfy the different operation's completion.

operation_evidence therefore can report BOTH:

```text
retry_outcome = UNRESOLVED
automatic_retry_allowed = False
confirmed_produced = True
```

This is later resolution of part certainty, not renewal of the retry operation.
confirmed_part_count counts only validated produced-part evidence. Legacy
RetryController.completion_count includes configuration operations and is not
a produced/inspected/batch count. No batch/inspection counters are implemented.

Same-session evidence can be recorded during a latched heartbeat timeout, but
it cannot clear that fault, grant send permission, configure or start anything.
Once a different boot has been observed, old-session frames are quarantined for
explicit historical review; they are not automatically credited to the new run.

### Eligibility and explicit action

An assessment requires all of:

- A genuinely different valid PRODUCE_PART request with a new acceptable number.
- Same intended boot and no observed session change.
- Fresh heartbeat availability, no blocking/latching station fault, and a NEW
  successful correlated read-only status round trip.
- Status IDLE, no active operation, positive applied configuration and, when
  known, the run's expected applied production time.
- Candidate op_no above accepted high_water. That mark does not prove a part
  completed and is never used to manufacture completion evidence.

An unresolved part cannot be recreated with new job_id/op_no: retained
(batch_id, part_id)-to-operation identity blocks it in both the retry controller
and continuation assessment. Assessment also refuses already-known completed
parts as different work. Do not rename the batch/part to evade this identity.

A positive assessment changes no configured/started permission, submits no
part and grants no lasting token. produce_different is the explicit caller
action and performs a NEW status check rather than trusting a previous positive
assessment. Thus an IDLE assessment followed by a BUSY state cannot authorize
work through a cached snapshot. There is no arbitrary status-cache lifetime.
Only that candidate is submitted; the normal run remains disarmed afterward.
The final firmware BUSY/session checks still apply if state changes after the
assessment. No automatic continuation, retry renewal or batch start occurs.

Restart/heartbeat faults still require the existing explicit recovery and
configuration/start flow. An isolated unresolved operation with healthy same-
session idle station can instead use the explicit different-work action without
reconfiguring or clearing the original uncertainty. Abort remains an operator
decision; batches with unresolved parts remain incomplete.

## Example

```python
from gateway_client import ProductionRun, OperationUnresolved, ContinuationBlocked

report = {"tx": [], "events": [], "rx_chunks_hex": []}
run = ProductionRun(port, report)
run.connect_or_recover()              # explicit initial connection/recovery
run.configure(1, "cfg:1", 1000)
run.start()
try:
    run.produce(2, "work:2", "batch-A", 2)
except OperationUnresolved:
    snapshot = run.read_status(timeout=1.0)  # no old-operation resubmission
    run.observe(0.1)                        # late evidence only; no rearming
    old = run.operation_evidence(2)
    candidate = {"type": "PRODUCE_PART", "op_no": 3, "job_id": "work:3",
                 "batch_id": "batch-A", "part_id": 3}
    eligibility = run.assess_continuation(candidate)
    # No work has started from assessment. The gateway/operator must choose:
    if eligibility["eligible"] and caller_explicitly_authorizes:
        try:
            run.produce_different(3, "work:3", "batch-A", 3)
        except ContinuationBlocked:
            pass                       # new fresh assessment can differ
```

The caller's authorization and batch/inspection management are intentionally
not implemented by this example. Send a part to inspection only from validated
confirmed-produced evidence. Neither STATUS nor heartbeat/availability can
substitute for its PART_PRODUCED result.

## Tests, scope and remaining limitations

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python pc_test/continuation_test.py --port COM3 --log results/continuation_hardware.json
```

Targeted hardware fixtures deliberately reset RAM for isolation and the
restart test; normal status/poll/reconciliation/retry logic never resets or
flashes the board. The late-result fixture releases a REAL station completion
that the test previously withheld from the operation controller. Its original
wire receipt time is retained and the later release is logged separately; it
does not claim actual physical UART delay. Busy and queued-old-status cases
use an explicitly logged diagnostic job and a synthetic stale status.

All software regressions run. Unchanged hardware suites are not rerun for this
follow-up; targeted new paths are exercised instead. Physical unplug/replug
remains NOT RUN. No firmware or message-interface changes are needed.

The PC ledger/session/sequence allocator are RAM-only. Freshness/correlation
and part-identity protection depend on retained process state; a new Python
process cannot reconstruct an old batch from STATUS. Explicit reconciliation
is required after loss of client state. Unknown operations, unregistered
diagnostic jobs and other-session historical frames are not automatically
confirmed. There is no persistent history, batch scheduler, inspection sender,
operator abort UI or automatic resumption here. A status check is a point-in-
time assessment, not a guarantee against a later fault or another writer.
