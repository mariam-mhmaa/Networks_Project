# Command and job lifecycle

Last reviewed: 2026-11-17.

Status: The user explicitly confirmed the three-stage deadline architecture and R01-R10 below. This is the approved behavioral baseline. Precise timing, numerical limits, command effects, receipt registration, restart/cache mechanisms, freshness, and wire schemas remain open in [reliability-open-decisions.md](reliability-open-decisions.md). The operation-controller/inspection application is not implemented or hardware verified. Member 2's separately host-tested transport foundation is recorded in D010; it is not proof of this lifecycle contract.

## Approved user rules

| Rule | Approved invariant |
| --- | --- |
| R01 | ESP32s execute accepted jobs independently of whether the gateway receives their acknowledgements. |
| R02 | Cache the terminal outcome and promptly transmit completion/results immediately on finishing; retain them for recovery. |
| R03 | Missing delivery/acceptance ACKs never gate accepted execution or completion transmission. |
| R04 | Valid later-stage evidence establishes earlier facts without inventing missing ACK observations/timestamps. |
| R05 | Execution retransmissions preserve original identity and semantic contents; duplicates never cause duplicate execution. |
| R06 | Recovery has finite attempt limits, response windows, and an absolute time limit. |
| R07 | PENDING_VALIDATION, IN_PROGRESS, and repeated ACKs cannot indefinitely extend deadlines or replenish budgets. |
| R08 | One operation controller owns timeout/recovery decisions for the original operation and its recovery exchanges; no competing application retry loops. |
| R09 | Status queries are read-only and cannot create, admit, restart, or execute the target operation. |
| R10 | These invariants apply to every command/job, including operator controls, configuration, production, and inspection. |

Rules R04-R08 implement official VII-VIII; R09 supports safe recovery under VIII-IX; R10 follows VII's explicit universal scope and III's inspection-configuration requirement. R01-R03 strengthen the execution contract consistently with V and VII. No user rule contradicts the PDF. Three separate deadline stages and three custom-link reply packets remain team design choices rather than literal packet/timer counts mandated by the PDF.

## Independent receiver execution and prompt completion

The gateway controller tracks what the gateway knows; it does not authorize each next step of an already accepted ESP32 job. After local validation and atomic duplicate-protection registration, execution progresses according to the receiver's scheduling contract. It never waits for RECEIVED/ACCEPTED to reach the gateway, a gateway confirmation, a socket flush, or a status query. A blocked ACK send must not block execution/timer handling.

On finishing, update the terminal operation record and cache its immutable result before, or atomically with, publishing it to the transmitter. Promptly attempt an unsolicited completion send without waiting for previous ACK transmission or a recovery query. A racing duplicate/query must see a coherent pending or terminal record, not a gap allowing execution twice.

"Immediately" means prompt nonblocking transmission scheduling after the outcome is available, not guaranteed physical delivery during disconnection or a hard real-time guarantee. Failed/blocked transmission leaves the cached outcome available under the agreed retention policy. Cache reservation, capacity, transmission priority, and crash durability remain open. This clarification implements R02; it does not weaken the requirement to transmit promptly.

ACK loss alone never cancels accepted work. Explicit Stop/Fault/cancellation, a receiver restart, and execution errors are different conditions; their effect on active work remains a joint decision. An execution error must not become a fabricated inspection FAIL verdict or be mislabeled as a pre-execution rejection.

## Distinct events

Every command and job records delivery, application acceptance, and completion separately, as required by the official project PDF requirement VII and Milestone 1 item 5. These are operation-level events, separate from system states Idle, Running, Paused, and Fault.

For the custom serial and TCP application links, use explicit `RECEIVED`, `ACCEPTED`, and `COMPLETED` replies in the normal successful case. These are three replies total, including the final completion/result, rather than three acknowledgements plus a fourth result. Separate receipt packets are a team design choice, not a packet-count requirement in the PDF. Operator HTTP/WebSocket delivery and lifecycle representation will be specified separately.

- `RECEIVED`: the receiving application obtained a complete message with a trustworthy readable operation identifier. Structural integrity checks precede trusting the identifier. This does not commit the receiver to executing the operation. Whether it also guarantees a queryable receipt-registry entry is O02; do not silently assume that guarantee.
- `ACCEPTED`: the receiver validated the operation, recorded its commitment, and agreed to act. Application acceptance does not mean an inspected part received a PASS verdict.
- `COMPLETED`: the work finished; report an explicit result plus the original command/job identity and relevant batch/part references.
- `REJECTED`: the receiver explicitly declined the operation and reports the original identity and reason. A rejected operation must not start work.

A successful local send is recorded as sending, not proof of remote application receipt. An invalid/corrupted envelope with no trustworthy identifier is discarded/logged rather than acknowledged using an unreliable ID.

## Evidence and missing replies

Maintain one pending-operation record containing stage evidence, timing, result, and retry accounting. Delivery, acceptance, and completion remain distinct recorded facts; they are not a mandatory chain of separately observed ACKs that must all arrive before any later response can be processed.

- If `RECEIVED` is absent but a matching valid `ACCEPTED` arrives, delivery is confirmed by acceptance.
- If only receipt is confirmed, wait for acceptance within its applicable deadline; then resolve uncertainty if acceptance or a conclusive later outcome remains missing.
- If `ACCEPTED` is absent but a matching valid `COMPLETED` arrives, process the result once and record that the completion establishes prior acceptance. Do not fabricate an observed acceptance ACK or its original timestamp.
- A valid pre-execution `REJECTED` establishes delivery and rejection, not acceptance or an inspection FAIL verdict.
- If acceptance is confirmed but completion is absent, use a completion deadline that accounts for the configured operation duration and communication allowance.
- If no response arrives, apply the bounded request-level retry policy when the relevant deadline expires.
- A late earlier-stage ACK must not regress a completed/rejected operation or restart its work-duration timer.

The three deadline stages are approved: delivery evidence, application acceptance, and execution completion. Normal stage timers advance with valid evidence. Query-response windows during recovery do not erase the original work limit or fixed absolute horizon. Exact anchors, formulas, attempt budgets, and numerical values are O01; earlier one-second examples and two-plus-two budgets are not approved constants. In particular, a delayed first acceptance/status reply cannot grant a lifetime beyond the original absolute bound.

Gateway decisions use one local monotonic clock. Device-local elapsed durations may be reported with provenance; do not subtract unsynchronized device clocks. Fast commands may record multiple distinct events in one scheduler turn without artificial delay.

A timeout callback rechecks the current operation state and expected timer generation before acting. An obsolete queued timeout cannot resend an already completed request. A conflicting terminal result/changed verdict is reported as an inconsistency rather than overwriting the original result. Deadline-boundary event ordering and late-result counting are O05.

Validate identity, expected device, action, part/batch context, and result semantics before applying evidence. Duplicated completion replies must not double-count inspected parts or verdicts.

## Uncertain outcomes and duplicate requests

A timeout/disconnection means missing evidence; it does not prove work never started or that inspection returned FAIL. Distinguish a completed result, an explicit rejection, and an uncertain outcome.

Retransmit the same semantic request with the same original ID when the agreed recovery policy calls for a retry. A receiver recognizing that ID returns existing status while the job is pending, its stored completion when finished, or its stored rejection. It must not execute duplicate work. Exactly how repeated replies represent current status will be set in the external message contracts.

If a receiver restarts and loses its operation history, at-most-once behavior cannot be inferred from ID uniqueness. Detect the restart and resolve it under the separately agreed safe recovery policy; do not silently rerun uncertain work.

Use one coordinated bounded recovery policy per original operation rather than independent retry loops for its stages. One decision owner does not require one undifferentiated numerical retry count; exact phase allowances and a total cap are O01. Fresh status never grants unlimited work-duration extensions or retries.

After confirmed acceptance with missing completion, recovery uses read-only status/result retrieval. After receipt but before acceptance, lookup behavior depends on O02. UNKNOWN after known acceptance signals lost state/context inconsistency; after mere receipt it can be a legitimate admission race unless queryable registration before RECEIVED is guaranteed. UNKNOWN never triggers target execution automatically.

Queries have their own correlation/command identity and separately reference the original operation ID. Their own bounded processing cannot recursively create an uncounted query-recovery loop; recovery query transmissions consume the parent operation's applicable budget/horizon. Exact wire schemas are O06.

The gateway controller owns gateway-originated operations; the initiating operator application needs one owner for its own submitted HTTP commands. This is one owner per operation, not one physical event loop across all devices. Adapters/timer monitors report events and do not independently retry. ESP32s execute, publish terminal outcomes, and answer queries; a separate autonomous completion-retry/ACK protocol would need prior approval. Native TCP byte retransmission is transport behavior, not another application recovery owner.

The same principles apply to Start/Pause/Resume/Stop, settings, production, inspection, and future commands/jobs. Their terminal effects and timing profiles differ. Configuration must confirm active settings, and control-command completion is distinct from eventual batch completion; exact effects are O03. Query handling itself requires correlation, validation, finite handling, and separate delivery/acceptance/completion evidence when represented as a command. HTTP/WebSocket mapping may differ from the custom ESP packet layout while retaining those separate events.

Result/history retention must cover the full validity/recovery period. A still-valid accepted ID cannot be evicted and later treated as new; reserve resources before acceptance or stop admission safely. Receiver boot identity, durable-versus-volatile history, closed-scope rejection, and cache capacity are O04. An issuer session inside an ID is not the receiver boot identity.

Late evidence belongs only to its original job/batch/device context. It cannot silently resume a Fault/aborted batch or count toward a newer batch. Freshness limits, permitted historical reconciliation, and exact accounting are O05. Fault cannot physically stop a disconnected ESP32; unresolved work remains uncertain, not a manufactured product verdict.

## Open decisions and implementation authority

See [reliability-open-decisions.md](reliability-open-decisions.md) for O01-O06. The user permits implementation at coherent checkpoints after relevant decisions are agreed. If an alternative changes approved behavior or architecture, present the alternative and ask before implementing it. The current turn authorizes documentation updates, not silent selection of those open policies.

## Verification still required

- Normal receipt, acceptance, and explicit completion.
- Receipt followed by rejection without execution.
- Missing receipt ACK with later acceptance.
- Missing acceptance ACK with later completion.
- No replies and bounded retry exhaustion.
- Missing completion, in-progress duplicates, and cached completion replay.
- Duplicate/late replies without state regression, timer extension, or double-counting.
- Receiver restart with uncertain work and safe handling.

No checks above have been claimed as passed.

The expanded rule/requirement coverage and planned failure cases are in [reliability-verification.md](reliability-verification.md). These documents establish design agreements, not proven implementation compliance.
