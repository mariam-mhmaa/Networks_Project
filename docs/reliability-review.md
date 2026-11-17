# Reliability design review

Date: 2026-11-17

Status after user review on 2026-11-17: Three-stage deadlines and R01-R10 are confirmed in [job-lifecycle.md](job-lifecycle.md), the authoritative behavioral baseline for this topic. This document retains research and candidate mechanisms. Numerical budgets, precise timing, receipt registration, boot/retention mechanisms, command effects, and freshness remain pending O01-O06 in [reliability-open-decisions.md](reliability-open-decisions.md). Nothing has been implemented or hardware tested. The official PDF remains the authority; external protocols/defaults do not override it.

## Corrections after explicit user confirmation

- Receiver execution never waits for gateway ACK reception. Cache terminal results and promptly publish completion without waiting for a query or prior ACK transmission.
- Apply the contract to all commands/jobs; inspection is an example, not the scope limit.
- One controller means one decision owner per original operation and recovery exchanges, not one undifferentiated numerical counter or one physical controller across all devices.
- UNKNOWN after acceptance indicates lost state/context. UNKNOWN after mere receipt depends on O02; without guaranteed queryable registration it can be an admission race.
- Preserve fixed work/absolute bounds during recovery while a short response window is active. Progress cannot renew them indefinitely.
- Recommendations below that depend on unresolved mechanisms/formulas remain candidates, not newly approved implementation decisions.

## Finding

Timer count alone does not establish correctness. A professional design needs explicit operation states, evidence, timing anchors, bounded recovery, duplicate-record retention, restart handling, and safe late-message behavior. Both two-phase and three-phase timeout designs can satisfy the PDF if they cover these behaviors.

For our already agreed explicit RECEIVED/ACCEPTED/COMPLETED exchange, recommend three stage-specific time limits managed by one operation controller. Only the current normal phase is actionable; independent acknowledgement handlers must not each start their own retry loops. Keep a fixed overall recovery horizon as an additional bound. Heartbeat/liveness checks are independent of operation deadlines.

This recommendation is specific to this custom application protocol; it is not a claim that RFC 7252, RPC, or an industrial standard requires three application ACK packets or timers.

## Coverage against the official PDF

| Requirement | Reliability consequence |
| --- | --- |
| II: unique parts and complete batches | Correlate every result with its job, part, and batch; count once; never count uncertainty as a verdict. |
| III: live validated inspection configuration on B | Configuration commands have identities and application confirmation. Inspection result is produced on B and matched to the original job. |
| IV: bounded inspection queue | Protocol recovery cannot bypass queue admission or create extra jobs. Keep waiting and active work separate. |
| V: configurable operation times | Completion limits derive from actual configured durations and permitted startup delay, with measured margins. |
| VI: four system states and batch completion | Per-operation states remain internal. Unresolved/device faults stop issuing new work; never report a complete batch with unresolved parts. |
| VII: identities, three events, timeouts, bounded retries | Preserve complete operation IDs; record sending separately from remote delivery; retain distinct delivery/acceptance/completion evidence and explicit outcomes; use bounded phase-aware recovery. |
| VIII: at-most-once execution | Atomically register accepted work before starting; duplicate requests return existing status/results; retain history for all still-valid requests. |
| IX: disconnection/staleness and safe behavior | Monitor heartbeat age, detect receiver restarts, fence old scopes, validate result freshness, and prevent late messages from reviving a faulted or closed batch. |
| XI: simple simulation | Retain timer/counter software manufacturing; reliability belongs in explicit, testable communication/state components. |
| M1 items 1-2 | Use required SLIP/ATR/CRC/sequence serial and length-prefixed TCP; application recovery must not bypass framing/integrity checks. |
| M1 items 4-6 | Correlate operator commands and asynchronous status; retain evidence in logs/captures and verify normal/failure cases on hardware. |
| M2 migration | Transport adapters must preserve the same application identity/evidence semantics. Benchmark ATR echoes have separate test semantics and must not be confused with production job execution. |

## Normal exchange and phase limits

Initial request carries immutable operation identity and semantic contents. Proposed device contracts also identify the intended receiver boot instance and current run/batch scope; exact envelope fields require team agreement.

1. Await delivery evidence. A delivery time limit bounds how long the gateway waits for RECEIVED or a conclusive later response. Expiry is delivery uncertainty, not proof of nondelivery.
2. Once receipt is confirmed, await acceptance or rejection. The acceptance limit bounds validation/admission. Repeated receipts do not restart it. A station must not hide an unbounded work queue behind acceptance.
3. Once accepted, await completion. A candidate station-job formula is first valid acceptance confirmation time + configured operation duration + allowed startup/communication margin, constrained by a fixed whole-operation bound. The stage is approved; the exact anchors/formula remain O01 because delayed first evidence must not create a new excessive lifetime.

Use one gateway monotonic clock. Do not subtract unrelated device clocks. Completion timing for configuration and control commands is defined by their actual effects, not the production/inspection duration.

Completion must mean the specified work completed. For example, applying settings must confirm those settings are active; a Start command's completion is a defined control outcome, separate from eventual batch completion. These command-specific semantics remain to be approved. Inspection PASS/FAIL is a product verdict, distinct from an execution/protocol error.

REJECTED is terminal for that submitted request: record why it was declined and do not blindly retry invalid parameters. Busy/backpressure handling returns to the scheduler under the agreed scheduling policy rather than an unconstrained communication retry.

## Later evidence and event races

- ACCEPTED without RECEIVED establishes delivery, with the evidence source recorded.
- Valid COMPLETED without intermediate ACKs establishes the original operation's completed outcome; retain the fact that the individual ACKs were not observed and do not invent their timestamps.
- Match operation, source/receiver instance, action, part, batch, and semantic contents before applying a reply.
- A repeated or late earlier-stage ACK does not regress state, renew deadlines, or create new work.
- A timer callback carries the expected operation state/deadline generation. Recheck the operation record before taking action; a queued timeout for an already completed operation is obsolete.
- A delayed completion received during an explicitly bounded recovery interval is classified as late and can reconcile only its original unresolved operation under the freshness policy. After Fault or closure it is audit/reconciliation evidence, not permission to resume or a new result for a later batch.

## Phase-aware recovery

Before receipt/acceptance is known, an execution request may be retransmitted only with the original ID, original contents, same intended receiver boot instance, and still-valid run scope. The receiver must atomically check/register the ID before any effect. A repeated request returns existing status/result and cannot start a second execution.

Once delivery is confirmed but acceptance is missing, prefer a read-only status lookup for the original operation. Once acceptance is confirmed and completion is missing, use read-only status/result retrieval rather than resending an execution-bearing instruction by default.

Status reads carry their own correlation identity and explicitly reference the original operation ID. They cannot create, enqueue, restart, or accept work as a side effect. Their receipt/processing/result evidence is logged distinctly; their bounded request-response retry handling cannot recursively create another recovery loop.

Possible answers:

- Received, awaiting validation: keep admission recovery bounded; do not grant unlimited extensions.
- Accepted/in progress: update evidence; never restart the fixed work deadline. Beyond the deadline, remaining recovery is limited reconciliation, not a fresh full execution allowance.
- Completed: validate/retrieve cached result; count at most once.
- Rejected: preserve reason and terminate this request.
- Unknown after confirmed acceptance: lost state/context inconsistency, not permission to run again. After mere receipt apply O02: without guaranteed queryable registration, UNKNOWN can be a legitimate admission race.
- Receiver boot changed: stop automatic execution resends, enter Fault, and reconcile explicitly.

Read-only status recovery is confirmed by R09. The exact operation-lookup wire contract remains O06; no query schema is approved yet.

## Retry ownership and limits

One gateway operation controller owns application recovery. Do not add separate serial/TCP adapter retry loops or recursive query retries. TCP's native byte retransmissions are distinct from application attempts and do not certify application completion.

A single owner does not require a single undifferentiated numerical budget. The previous suggestion of two total retries could consume all recovery opportunities before a later missing result.

Proposed starting configuration, not an instructor requirement or measured optimum:

- At most two recovery attempts before acceptance, choosing an original-ID retransmission if delivery is unknown or a status read if delivery is known.
- Reserve at most two status/result retrieval attempts after acceptance/completion timeout.
- Thus at most four application recovery exchanges for an original operation, excluding its original submission. Each query transmission counts; a lost query cannot invoke a separate uncounted retry policy.
- Each exchange has a bounded response wait. Use a documented bounded delay/backoff between attempts and an absolute operation/recovery cap. Device faults, explicit rejection, expiry, or user Stop can terminate attempts sooner.
- Duplicate/progress messages never replenish a budget. Read-only recovery cannot renew the original execution deadline.

Actual wait durations, margins, backoff, heartbeat thresholds, and numeric attempt limits must be measured and tested on the selected serial/network setup. There is no research basis for declaring a universal one-second timeout or exactly two attempts optimal for this hardware.

## Receiver history and restarts

Uniqueness of IDs does not itself prevent execution twice. Each receiving application requires an operation registry containing request identity, semantic request contents/fingerprint, admission state, and terminal outcome. Register atomically before starting work. Reject a repeated ID with different semantic contents.

Retain valid operation history through the batch and its documented recovery horizon. Do not evict a still-valid accepted ID and later treat the same ID as new. If capacity is exhausted, stop admitting new work safely rather than lose duplicate protection. Once a scope closes, reject execution requests for it so cache cleanup cannot make an old request executable again. Configuration/control histories need an equally explicit scope/retention rule.

For M1, propose detecting every device boot instance and binding work to it. If an ESP32 reboots and loses volatile history, requests addressed to the old boot instance are rejected. Do not readdress an uncertain old job to the new boot with a fresh ID. This permits safe faulting without claiming automatic recovery or exactly-once completion across crashes. Persisting histories for transparent crash recovery would be a separate, more demanding design decision.

Gateway restart likewise must not automatically replay uncertain execution requests. Reconcile active devices and scopes before allowing a new run. Receiver-boot handling and scope closure are proposed additions requiring team agreement.

## Independent safe-state behavior

Heartbeat/disconnect detection is active throughout every phase. A confirmed missing device or changed boot instance can trigger Fault before an operation timeout/retry budget expires. Stop issuing new work and preserve confirmed results. Fault does not physically stop a disconnected ESP32; already accepted work may finish.

After recovery exhaustion or an invalid/expired receiver context, mark unresolved outcomes uncertain and enter Fault. Never substitute a FAIL verdict or report successful batch completion. Recovery reads may support diagnosis, but no automatic resume or reassignment of uncertain work is permitted without the separately agreed recovery procedure.

## Required verification scenarios

These are planned checks, not passed tests.

| Scenario | Expected evidence/behavior |
| --- | --- |
| Normal job | Distinct delivery, acceptance, completion and matching B verdict. |
| Drop receipt ACK, deliver acceptance | Advance using later evidence; no unnecessary execution retry. |
| Drop acceptance ACK, deliver completion | Apply valid original result once; missing ACK recorded honestly. |
| All initial replies missing | Same-ID bounded resend while context is valid; no duplicate execution. |
| Receipt confirmed, validation stalls | Acceptance limit and bounded status lookup; no infinite wait. |
| Normal long configured inspection | No premature failure based on a fixed short completion wait. |
| Completion lost, result cached | Read-only recovery obtains original result, no new inspection. |
| Still-working replies after deadline | No renewed execution allowance or replenished budget. |
| Repeated or out-of-order stage replies | No state regression or extra counts. |
| Timeout queued just before result handling | Current state recheck prevents obsolete timeout action. |
| Same ID, different contents | Reject/log conflict; no execution. |
| Receiver reboot after acceptance | Boot mismatch/Fault; no silent re-execution. |
| Disconnect during job | Independent liveness handling and safe fault behavior. |
| Expired/old batch result | Log as stale/historical; never count as a new batch result. |
| History capacity/retention boundary | No valid duplicate record silently discarded. |
| Queue full and active production | Recovery cannot create extra parts or bypass capacity accounting. |
| Stop during pending/recovering job | No new work; preserve partial/uncertain outcomes; late replies cannot resume. |
| Operator Start retry | Same command identity cannot create multiple batches. |

## Research basis

- Official project description, pages 2-3 and 5: operation identity, runtime configuration, three events, at-most-once execution, stale/disconnected handling, and M1 evidence.
- RFC 7252 sections 4.2, 4.5, 5.2.2: bounded retransmission, duplicate handling, later responses establishing delivery despite lost ACKs, and separation of acknowledgements from a later application response. These concepts are adapted; CoAP is not being substituted for required M1 transports. https://www.rfc-editor.org/rfc/rfc7252.html
- RFC 5531 section 5: absence of a reply does not prove non-execution, including TCP; transaction IDs and remembered requests support at-most-once behavior. https://www.rfc-editor.org/rfc/rfc5531.html
- AWS Builders' Library, Timeouts, retries, and backoff with jitter: latency-informed timeout selection, bounded retries/backoff, and retry ownership at one layer. https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- AWS Builders' Library, Making retries safe with idempotent APIs: stable client IDs, request semantic equivalence, retention for late requests, and same-ID/different-parameters rejection. https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- Google AIP-151: operation identity and status/result retrieval for work that continues after an initial response; start-time errors differ from execution errors. This is an architectural analogy, not adoption of Google's API schema. https://google.aip.dev/151
