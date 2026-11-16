# Step 5C bounded Python retries

Firmware and the wire interface are unchanged from Step 5B. This is a reusable
single-operation Python controller, not a batch scheduler, background worker
or persistent recovery service. No operation numbers are allocated by it.

Agreed batch-level policy and current API review: docs/gateway_handoff.md.
An isolated unresolved operation need not abort a batch, but different work
requires explicit same-boot reliable/idle assessment. The current wrapper's
disarming is a conservative submission gate, not an implemented batch abort.
Passive post-stop late-result reconciliation and explicit different-work
assessment/action were approved and are implemented; see docs/continuation.md.
RetryLedger now records separate part evidence/resolution audit. Its original
results and exhausted budgets stay unchanged. OperationUnresolved is separate
from SessionFault. An explicit different-work action, not heartbeat recovery,
can submit a new part after a new same-session healthy/idle assessment.

## Defaults and state transitions

All times use time.monotonic. Let t0 be sampled immediately before the first
transmission, and D be the known applied production_time_ms / 1000.

| Policy field | Default | Meaning |
| --- | ---: | --- |
| acceptance_timeout | 1 s | Acceptance wait ends at t0 + 1 |
| completion_slack | 1 s | Initial production completion deadline t0 + D + 1 |
| max_retries | 2 | At most 3 transmissions total |
| saved_result_wait | 1 s | Matching-response window following each saved-result request |
| production_overall_slack | 3 s | Absolute production deadline t0 + D + 3 |
| configuration_overall | 3 s | Absolute configuration deadline t0 + 3 |

Use RetryPolicy(...) to configure these values and pass it to RetryController
or ProductionRun. Defaults are logged. Invalid/nonfinite times and negative
or boolean retry budgets are rejected. Saved-result windows always clamp to
the absolute deadline. Policy changes never move a prior operation's deadline.

1. Send once and WAIT_ACCEPTANCE until t0+1. RECEIVED is only delivery.
2. ACCEPTED or OPERATION_RUNNING confirms acceptance. For production, wait
   until the ORIGINAL t0+D+1 deadline. A matching completion at any phase
   ends waiting immediately, even if acceptance was omitted.
3. On acceptance timeout or missing completion, transmit the identical logical
   request if budget remains. It asks the unchanged firmware for running status
   or its saved result; there is no new query message type.
4. Wait up to one second for a matching reply. A running reply before the initial
   completion deadline resumes that ORIGINAL wait. Running replies after it do
   not reset the saved-result window. They never move the absolute deadline.
5. Configuration has no production timer: its initial one-second window also
   covers the immediate configuration completion, then at most two bounded
   saved-result windows fit within its three-second overall limit.
6. Once all three transmissions are spent, observe only until the fixed overall
   deadline. No more transmissions, even if running responses keep arriving.
   A late original completion can still confirm the outcome before that deadline.

Terminal outcomes are COMPLETED, REJECTED, FAULT or UNRESOLVED. Restart,
heartbeat loss, operation conflict, invalid request, stale/result unavailable,
or any matching rejection stops retries immediately. I/O errors stop with
UNRESOLVED because an incomplete/failed write may still have delivered work.
Missing confirmation does NOT mean a part was not produced.

## Identity, correlation and completion accounting

The first attempt freezes a private JSON copy. All attempts keep exactly the
same boot_id, op_no, cmd_id/job_id, batch_id, part_id and requested settings.
Only ATR seq changes per transmission, as already permitted by Step 5A/B.
Each attempt's new seq is recorded. No retry allocates or repairs an op number.

Replies must match the intended session, operation and full application IDs,
with an ATR seq belonging to this logical operation's transmissions. Original
delayed completion can use the first seq; cached replay uses its retry seq.
Wrong/stale operation or unknown-seq replies are quarantined and logged, not
credited to the current operation. An inconsistent matching identity faults
the operation. A different-boot reply to one of its attempts stops as RESTART.
Heartbeats/status stay on the existing observation path and never become
acceptance or completion. Liveness continues to be checked during all waits.

RetryLedger holds request fingerprints, allowed sequences, stop outcomes and
confirmed-completion keys in PC RAM. ProductionRun retains it across explicit
reconnection. Calling execute again for an already stopped operation cannot
create a fresh retry budget/deadline. A known completed result can be returned
locally with zero transmissions and new_logical_completion=false. Conflicting
contents are rejected locally. Completion_count counts each (boot_id, op_no)
once within the ledger, not each original/replayed/duplicate frame.

The ledger is not persisted across Python process termination. Restarting the
PC program does not grant permission to rebind uncertain work or silently
start a new operation number. Operator reconciliation remains required; the
station's session fence and RAM history are unchanged.

An old configuration's historical result does not prove it is CURRENTLY
applied. ProductionRun reads STATUS after historical replay and does not arm
start if the actual current setting differs from the requested historical
setting. A genuinely new configuration/explicit start is then needed.

## Gateway usage

```python
from gateway_client import ProductionRun, RetryStopped
from retry import RetryPolicy

run = ProductionRun(port, report, policy=RetryPolicy())
run.connect_or_recover()                   # explicit discovery, not work recovery
run.configure(1, "cfg:1", 1000)
run.start()                                # explicit new start
try:
    outcome = run.produce(2, "job:2", "batch-1", 1)
    result = outcome["completion"]["event"]
except RetryStopped as error:
    # error.result records attempts, original deadlines and the honest outcome.
    # Stop issuing work. Observe/reconcile; never invent a new op_no as a retry.
    pass
```

An unresolved/rejected/faulted gateway operation disarms the run. Heartbeat
recovery does not rearm it. Recovery still requires explicit configuration
and start. Call observe while idle to process heartbeats; synchronous retry
waits already pump the receiver. This controller is single-threaded: do not
call execute concurrently or run multiple readers on the same port.

## Deterministic evidence and test limits

Software tests execute the actual retry state machine with a fake monotonic
clock and scheduled replies. They check deadlines/budget, RECEIVED-only,
running floods, terminal rejection, faults, stale-session replies, local
completion deduplication, shared-ledger stop behavior and gateway disarming.

retry_test.py applies named deterministic response omission AFTER the normal
receiver has processed heartbeat/status traffic. Every ignored application
frame, its complete decoded ATR bytes, identity, seq and observation time is
logged as IGNORED_RESPONSE. Heartbeats are never passed to the omission hook.
Test-injected copies of real running/completion frames and deliberate restart
or RX heartbeat suppression are recorded separately as test_injections.

Configuration replay test intentionally applies a newer configuration while
the old confirmation is withheld, then lets the OLD operation retry inside
its ORIGINAL three-second deadline. It verifies the cached old result does
not revert the newer time, including producing a part at that newer duration.
This interleaving is explicit test instrumentation, not an automatic client
action to recover uncertain work using a new operation number.

Non-duplication evidence uses station-sourced state/high_water, active operation
heartbeats, the preserved original completion seq and original timer deadline,
no second ACCEPTED on retransmission, and replayed=true cached results. It is
not inferred solely from counting PC completion messages. The unchanged C
history core and history hardware regressions give additional evidence.
There is no independent physical-part/execution counter in this virtual station;
the claims are limited to this available protocol/state/timer evidence.

Expected UNRESOLVED/FAULT/REJECTED outcomes in fault-injection scenarios are
PASS when they match the policy. Raw logs may contain the valid completion
the test intentionally withheld: the controller remains UNRESOLVED when it
was not allowed to use it. That is an honest response-loss simulation, not
evidence that production failed to occur.

JSON includes operation requests, original times, all deadlines, attempts,
transitions, responses, ignored/quarantined frames, station evidence and final
outcomes. CSV has one row per trace event with operation identity, attempt,
seq, elapsed time, deadlines and final outcome. Actual TX payload/wire hex
and received serial chunks remain in the normal PC client log.

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python pc_test/retry_test.py --port COM3 --log results/step5c_retries.json --csv results/step5c_retries.csv
```

The test fixtures explicitly reset RAM state between scenarios; retry logic
itself never resets the board. No firmware flash is needed. Physical USB
unplug/replug remains NOT RUN; heartbeat loss is controlled RX suppression.
