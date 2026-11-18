# Gateway handoff policy and client API review

Date: 2026-11-16 (Africa/Cairo). The approved client-only follow-up is now
implemented. Firmware and wire messages are unchanged; no batch manager exists.

## Current supported API

See [the API contract and example](continuation.md). The four review questions
below now have supported client paths:

| Requirement | Implemented behavior |
| --- | --- |
| Separate uncertainty from availability | OperationUnresolved is distinct from SessionFault; original stopped outcome/budget remains immutable |
| Read-only fresh status | ProductionRun.read_status dispatches interleaved heartbeats/results and correlates a new finite-time GET_STATUS |
| Late completion evidence | observe/read_status reconcile validated known-operation PART_PRODUCED once; separate audit records later resolution without rewriting UNRESOLVED |
| Explicit different work | assess_continuation reports eligibility only; produce_different explicitly rechecks fresh health/idle status before submitting that different part |

Status, heartbeats and high-water marks never prove a particular part completed.
The normal run remains disarmed after uncertainty. Same-session availability
does not clear a latched fault or grant continuation permission. Restart/lost-
heartbeat faults still require explicit recovery/configuration/start.

Retain the PC ledger and immutable batch/part-to-operation association. Both
assessment and retry submission block re-identifying an unresolved part.
The gateway must not rename batch/part IDs to evade that protection. The ledger
is RAM-only; a fresh Python process cannot reconstruct uncertain work from
station status. Unknown/other-session historical results require explicit
review, not automatic confirmation. No inspection routing, batch counters,
abort UI, persistence or batch scheduling was added.

Verification: 48 software tests and five targeted hardware groups PASS. Firmware
hashes are unchanged; no build/flash. COM3 independently reopened and closed.
Physical idle and production unplug/replug checks have now been performed;
see [acceptance.md](acceptance.md) for actual results, operator-timing and fixture
limits, and remaining physical same-session NOT RUN coverage. COM3 is closed.
The current contract below remains unchanged by that acceptance work.

## Agreed gateway policy

- Retry exhaustion leaves the ORIGINAL operation UNRESOLVED. Its original
  retry budget stays exhausted; no new deadline or budget is granted.
- An isolated unresolved operation does not automatically abort the batch.
- The gateway may continue DIFFERENT parts only in the same boot session,
  with reliable communication and positively confirmed idle/available station.
- Never recreate the unresolved operation OR its part under new identifiers.
  Retain its original boot_id, op_no, job_id/cmd_id, batch_id and part_id.
- Send only CONFIRMED produced parts for inspection. Delivery, acceptance,
  running status, an accepted high-water mark or idle status is not production
  completion evidence.
- Lost heartbeats, restart or uncertain availability pause NEW production.
- Reconnection alone does not automatically resume a faulted run.
- Abort is an explicit operator decision.
- A batch containing unresolved parts is INCOMPLETE. Report separate confirmed
  production, inspection and unresolved counts; do not count uncertainty as
  confirmed production, failed production or a normally completed batch.

These are requirements for the future gateway. Batch state/counts, inspection
routing, operator abort and cross-part scheduling are not implemented here.
An exception/disarmed client is not, by itself, a command to abort a batch or
cancel firmware work. An accepted station job may still complete while the PC
has an unresolved result or has paused further submissions.


The superseded static API review is archived in [gateway_api_review_historical.md](gateway_api_review_historical.md). Current contract/examples: [continuation.md](continuation.md). Final commands, acceptance evidence and scope: [acceptance.md](acceptance.md).

