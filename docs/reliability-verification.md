# Reliability verification plan

Date: 2026-11-17.

Status updated 2026-11-18: 50 B-scoped software tests pass, including actual native C/loopback application tests, scripted gateway recovery tests, and transport tests. See member2/esp32_b_inspection/verification/application_summary.json and application_tests.log. Normal/diagnostic ESP-IDF builds pass. The broader scenarios below remain a whole-project plan; A/operator and physical hardware scenarios are NOT claimed as passed. D012/member2-protocol.md resolve the B-specific choices.

## Ten-rule coverage

| Rule | Planned scenarios |
| --- | --- |
| R01 independent execution | V01-V03 |
| R02 prompt cached completion | V03-V05 |
| R03 missing ACKs do not gate work | V01-V03, V18 |
| R04 later evidence without invented timestamps | V01-V02, V06, V29 |
| R05 preserved identity and at-most-once execution | V05, V07-V09, V17 |
| R06 bounded attempts/windows/absolute horizon | V10-V12, V29 |
| R07 no endless progress extensions | V11-V12 |
| R08 one controller and obsolete-timer checks | V13-V14 |
| R09 read-only queries | V15-V16 |
| R10 all commands/jobs | V17-V19, V30 |

## Scenarios and required outcomes

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| V01 | Drop RECEIVED, deliver acceptance/completion | Work proceeds; later evidence advances state; missing ACK observation stays absent. |
| V02 | Drop ACCEPTED, deliver completion | Job completes and result counts once; no invented acceptance timestamp. |
| V03 | Drop both intermediate ACKs | One execution and unsolicited completion without gateway polling. |
| V04 | Block/disconnect transmit at completion | Cache outcome; blocked send does not block execution/control handling; recover retained result later. |
| V05 | Query/duplicate races completion | Coherent pending or terminal state, no cache gap or second execution. |
| V06 | REJECTED arrives without RECEIVED | Establish receipt/rejection, not acceptance or product FAIL. |
| V07 | Retransmit exact execution request | Same ID/semantic contents and one local execution. |
| V08 | Same ID, different parameters/part/action | Reject conflict, no silent overwrite or second execution. |
| V09 | Repeat completion/status result | Apply original accounting once. |
| V10 | No replies | Finite attempts, response waits, total horizon, then safe uncertainty/Fault. |
| V11 | Repeated PENDING_VALIDATION | Admission/recovery still expires, no renewed attempts or infinite wait. |
| V12 | Repeated IN_PROGRESS after work deadline | No full new work period; only bounded recovery. |
| V13 | Completion and obsolete timeout both queued | Recheck state/version, no resend after completion. |
| V14 | Adapter timeout, heartbeat fault, operation timeout coincide | One decision owner; no competing recovery transmissions. |
| V15 | Query UNKNOWN operation | Target remains nonexistent/unexecuted; query itself terminates within bounds. |
| V16 | Query pending/rejected/completed operation | Existing status/outcome only; no target admission/restart/change. |
| V17 | Duplicate Start/Stop/Pause/Resume/configuration | One effect per original ID and explicit retained result under the agreed command contract. |
| V18 | Control/configuration ACK loss | Accepted effect occurs independently; promptly send/cache terminal outcome. |
| V19 | Command completion versus batch completion | Correct per-command effect; no false full-batch success. |
| V20 | Receiver reboot after acceptance | Detect lost history/context; no silent uncertain-job replay. |
| V21 | Gateway/operator restart or reconnect | Preserve recovered identities and prevent unintended second Start/batch. |
| V22 | Cache/outbox full or retention boundary | No accepted result silently discarded; no forgotten valid ID becomes executable again. |
| V23 | Old batch, wrong device, stale, conflicting result | Reject/log/reconcile under O05, never count for a new batch or overwrite terminal truth silently. |
| V24 | Stop/Fault during accepted work | Apply O03, preserve uncertainty, no late-message auto-resume. |
| V25 | Production faster/slower than inspection | Respect configured times and queue reservations; recovery creates no extra parts. |
| V26 | Corrupt/truncated/oversized/bad-CRC frame | No unintended work or trusted bad ID; valid subsequent traffic still works. |
| V27 | Missing heartbeats with pending work | Independent liveness detection and safe state. |
| V28 | Execution/communication error versus FAIL | Explicit technical error/uncertainty, no fabricated verdict. |
| V29 | Very late first acceptance/status | Original absolute cap remains effective; no reconstructed ACK time. |
| V30 | Fast command finishes in one scheduler turn | Separate truthful events without artificial waiting or ACK-delivery gating. |
| V31 | Fresh job ID refers to an already processed part | Per-part scheduling/accounting prevents unintended extra work/results; ID uniqueness alone cannot bypass the agreed part lifecycle. |

## Official requirement coverage

| PDF reference | Evidence required |
| --- | --- |
| II, VI; M1 item 3 | V09, V19, V23-V25, V31: unique parts, correct counts/state, no completion with unresolved work. |
| III | V05, V08, V17-V19, V28: runtime settings applied on B; B-generated matching deterministic verdict. |
| IV | V22, V25: capacity/reservations respected during recovery. |
| V | V12, V25, V29: examiner-configured durations and documented bounded allowances. |
| VII; M1 item 5 | V01-V19, V29-V30: preserved IDs, distinct events, timeouts/retries for all commands/jobs. |
| VIII | V05, V07-V09, V17, V20-V22: no repeated execution/accounting, including history/restart boundaries. |
| IX | V10-V14, V20-V24, V27, V29: disconnection/freshness checks and bounded safe recovery. |
| XI | Review that manufacturing stays software timers/counters, without added mechanical/sensing complexity. |
| M1 items 1-2, 4, 6 | Real framed serial/TCP captures, HTTP/WebSocket evidence, serial logs, reproducible commands and a full-batch demo, in addition to simulation. |

Collect receiver execution counts/start-finish records, original IDs and contents, gateway monotonic event/deadline logs, observed/inferred evidence fields, cache/status replay, and packet/serial captures. Record actual results before marking any scenario passed.

This is a scoped reliability plan, not a complete register of every project deliverable or M2 benchmark condition. Those remain part of the eventual full-project requirement register.
