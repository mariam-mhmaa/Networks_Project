# Remaining reliability decisions

Last reviewed: 2026-11-18.

B-specific O01/O02/O04/O05/O06 choices are now approved/implemented under D012 and [member2-protocol.md](member2-protocol.md): finite initial timing profile, registered receipts, bounded history/boot/run fencing, original-context recovery and exact wire schemas. The historical options below remain for A/operator/full-system integration where not superseded by that contract.

The user approved three-stage deadlines and R01-R10 in [job-lifecycle.md](job-lifecycle.md). Recommendations below remain pending joint decisions. The B application/controller is implemented; this document does not claim the remaining A/operator integration is complete.

## Review findings

No user rule contradicts the official PDF. VII explicitly covers every command/job; III covers validated runtime configuration and B-generated matching verdicts; VIII requires at-most-once execution; IX requires stale/disconnection detection and safe behavior. Queue, runtime-duration, and system-state requirements IV-VI also constrain the final implementation.

The existing notes had six ambiguities, now corrected:

1. Execution and completion publication were not explicitly independent of gateway ACK reception. R01-R03 now make that mandatory.
2. Cached results were mentioned without prompt unsolicited transmission or cache-before-send ordering. R02 now requires both.
3. UNKNOWN after receipt was called lost state even though RECEIVED did not guarantee registered status. That inference is now conditional on O02.
4. One undifferentiated retry budget conflicted with proposed phase budgets. The invariant is one controller; numerical allocation is O01.
5. Inspection examples obscured command-specific terminal effects. R10 applies universally; those effects remain O03.
6. One active phase timer could be misread as discarding the work/absolute bound during recovery. Those limits remain effective while a query response window is active.

## O01 Timing anchors and finite recovery limits

Decide stage start points, permitted accepted-to-start delay/queueing, numerical allowances, per-phase attempt limits, response windows, bounded backoff, and the absolute lifetime formula from original submission. Define later evidence that skips an ACK, delayed first acceptance, blocked/partial writes, reconnect time, and result-versus-timeout equality.

Recommendation: one monotonic-clock record with versioned timeout events and an immutable absolute cap. Count every recovery transmission, including lost queries. Progress cannot replenish budgets. The previous one-second examples and two-plus-two candidate are not approved constants or measured optima. Set a finite software-test configuration before implementing; calibrate margins using actual hardware evidence later.

## O02 Meaning of RECEIVED and queryable registration

Today RECEIVED guarantees a trusted envelope/ID, not necessarily a queryable registry entry. A query can therefore race admission and return UNKNOWN legitimately.

Recommendation: reserve a bounded receipt record with identity and request fingerprint before sending RECEIVED; expose PENDING_VALIDATION; atomically convert to ACCEPTED or REJECTED. This closes duplicate-admission/status races. Decide registry-full behavior and semantic-invalid versus corrupted-frame handling. ACCEPTED always requires duplicate-protection registration before any execution, regardless of O02.

This is a proposed strengthening of the receipt contract and must be agreed before implementation.

## O03 Command effects, scheduling, and cancellation

Define completion and explicit outcomes for each operation:

| Operation | Decision required |
| --- | --- |
| Configure A/B | Which settings/version must be active and echoed; when can they change around active work? |
| Start | Is completion reached after device configuration and entering Running? How do child setup failures terminate Start? |
| Pause | Is new dispatch disabled while accepted work may finish, or must devices become quiescent? |
| Resume | Which state/device checks must pass before dispatch resumes? |
| Stop | Is completion batch-abort/dispatch-stop, or confirmed cancellation/idle on every device? |
| Produce | Exact part-ready result, timing, and resource admission. |
| Inspect | Active rule/version, matching verdict, and technical execution-error representation separate from FAIL. |
| Status query | Its own terminal evidence/result and bounded handling, distinct from target status. |

Recommendation: ACK reception never controls cancellation. Distinguish pre-execution rejection, failure during execution, explicit cancellation, and uncertainty. Decide busy/backpressure behavior and parent/child operation correlation. Enforce per-part scheduling/accounting as well as per-request deduplication: a fresh job ID for an already processed part must not silently create an extra production/inspection result. Never silently move uncertain work into another batch. The team guide's Pause/Stop policies remain proposals.

## O04 Restarts, cache retention, and capacity

Choose capacity/retention for pending receipts, accepted work, completed results, and rejected/control/query outcomes. Define resource reservation, full cache/outbox behavior, history cleanup, valid-scope closure, restart detection, and what survives power loss.

Recommendation for M1: receiver boot identity and valid-run context, no automatic replay of uncertain jobs across reboot, Fault/reconciliation, and no eviction of still-valid duplicate history. Reject execution for closed scopes before forgetting their records. Durable transparent automatic resume would be a different design requiring approval. Current caching commitment does not promise persistence across power loss.

An ID's issuer session identifies its creator, not the recipient boot instance. Binding a request to a boot instance must preserve the original request on retries; do not readdress uncertain old work to a new boot silently.

## O05 Freshness, late evidence, and counters

Define maximum result age without assuming synchronized clocks. Decide whether a late but fresh original result during bounded recovery may complete the normal batch, and whether post-Fault/Stop evidence may amend historical counts with an audit entry. It must never count for a new batch or automatically resume work.

Specify the exact deadline boundary, queued event ordering, conflicting terminal outcomes, and stale-result handling. Recommendation: retain provenance, original context, fixed monotonic bounds, immutable original terminal evidence, and separate later reconciliation. No PASS/FAIL is invented for uncertainty.

## O06 Message contracts and ownership across machines

Agree exact stage/progress/error schemas, query cmd_id/correlation plus separate target operation identity, and HTTP/WebSocket lifecycle mapping. A query of a completed operation must not confuse its own completion with the target's completion.

Agree one retry owner at each initiator: gateway for its issued operations, operator application for its issued controls, and no competing adapter/receiver application retransmission loops for the same operation. Define forwarding and newly derived child-operation ownership separately.

Finalize encoding, frame/ID sizes, completion publication priority/backpressure, cache/query outcomes, and reconnect/old-frame handling with teammates. Multiple distinct event records may potentially share a transport response; a single undifferentiated success flag is prohibited. Exact packaging remains a joint interface decision.

## Recommended order

Settle O02 first because it determines acceptance-recovery behavior. Then O03 establishes completion meanings needed for O01 timing profiles. Agree finite initial O01 bounds, choose O04-O05 restart/cache/freshness policy, and settle O06 wire contracts with the team. Numeric calibration can follow measured testing without silently changing approved behavior.
