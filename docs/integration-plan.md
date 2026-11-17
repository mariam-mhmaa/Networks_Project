# Milestone 1 integration plan

Reviewed: 2026-11-17, Africa/Cairo.

Status updated 2026-11-18: the B firmware and gateway B subsystem are implemented, 50 software tests pass, and normal/diagnostic ESP-IDF builds pass. Physical testing remains NOT RUN here. Member 1/full operator integration remains separate. The branch audit and original gap list below are historical; B-specific implementation/contract gaps are superseded by D012 and [member2-protocol.md](member2-protocol.md). All new work is on main and contributor branches/history are preserved.

## Repository and branch audit

Repository: https://github.com/mariam-mhmaa/Networks_Project

Local working copy: C:/Users/ainour/OneDrive - Faculty of Engineering Ain Shams University/Semester7/Networks/Project/Networks_Project

Fetched all configured remote branches and independently checked remote heads. The working tree was initially clean on member1/production-a. Inspected that checked-out branch, checked out member2/inspection-b and inspected its source, then created local main tracking origin/main. No existing source file was overwritten by switching branches.

| Branch | Reviewed commit | Contents and actual scope |
| --- | --- | --- |
| main | 4fa0883724474c177325e222b0bad00b7d738fb7 | Shared README only before this planning work. No integrated application. |
| member1/production-a | 58622a022b3391de14889410473a113eb8cc3a73 | 180 contributed files including production firmware, SLIP/ATR/CRC, boot/session guard, bounded history, Python client/retries, tests, and historical evidence. No gateway batch scheduler or operator interface. |
| member2/inspection-b | fb17631f09e54f77d37c0aae5f6575031ae3c6af | Seven files: Wi-Fi connection skeleton and project settings. README explicitly defers TCP and inspection; main.c implements Wi-Fi only. |
| member3/operator-ui | a7de4fa8f7f0819423482f47070813ea19e07128 | Newly discovered on the latest fetch. Operator HTML/CSS/JS, transport/protocol code, mock gateway, examples, tests, and gateway handoff are present. File inventory reviewed; detailed interface review remains to do. |

Initially no Member 3 branch was present. A subsequent fetch discovered member3/operator-ui at the commit above, resolving the source-location question. Reuse and complete that screen rather than replace its intended design. The current requested focus is Member 2; do not claim the new UI branch is fully reviewed merely from its inventory.

The connected GitHub API account reports pull access but no push permission. Local work is possible. No push was attempted; any different local Git credential's publication rights are unverified.

## Confirmed instructions and scope

- Work in this existing Networks_Project, with all changes on main. Do not create a separate feature branch or replace the repository.
- Inspect every contributor branch and preserve attribution/history when integrating.
- Build one complete integrated Milestone 1 project; editing and extending contributed code is in scope.
- The user approved completing ESP32 B here from the current Wi-Fi skeleton if no newer source is supplied.
- The operator screen must reuse Member 3's existing incomplete source and intended visual design. Its branch is now available; review it and complete the controls, validation, status, reconnect, and API integration.
- The approved Python/asyncio/FastAPI, single core owner, three-stage reliability contract, and R01-R10 remain the design baseline.
- Present remaining material choices as recommended yes/no questions, with brief reasoning and an opportunity for free-text questions/comments. Do not infer approval from silence or a preselected option.
- Ask before an implementation alternative changes approved behavior/architecture. Routine fixes needed to implement an agreed contract are part of the authorized project scope.

## What integration must resolve

These are engineering findings, not a claim that every existing teammate contract is an official requirement.

### Member 1 interface and architecture differences

- The firmware requires a shared increasing uint32 op_no across configuration and production. IDs must end with canonical :<op_no> and have at most 48 characters. Our approved action/issuer/full-session/per-action-counter IDs do not directly satisfy that suffix contract; some IDs also exceed its length limit. Choose one canonical end-to-end identity contract together before changing either implementation. Do not hide a renamed command/job ID inside a transport adapter.
- GET_STATUS is a read-only station snapshot, not an operation-specific cached-result lookup. Cached per-job results are currently obtained by replaying the original execution request. Approved read-only target-operation recovery needs an interface extension or an explicitly approved alternative.
- The Python ProductionRun/RetryController is synchronous, owns its serial reader, and must not run concurrently with another reader. Reuse framing/session/evidence logic where appropriate, but do not nest it unchanged under a second gateway retry controller.
- The current receipt reply does not promise a stored PENDING_VALIDATION entry. The proposed stronger receipt guarantee O02 therefore needs agreement and, if adopted, a firmware contract change.
- Firmware invokes ACCEPTED transmission before setting the production timer, and completion transmission before history_complete. The transmitter writes UART data inline. This is an ordering/coupling concern against our prompt nonblocking/cache-before-publication contract. It does not mean the firmware literally waits for the gateway to acknowledge receipt. Review and decouple the paths; do not claim blocked-transmit hardware behavior has been tested here.
- Eight completed results are cached with an accepted high-water mark. Eviction loses result detail while preventing older numbered work from executing again within that boot. Preserve the safety property; agree retention/recovery needs before changing the storage design.
- Rejected operations are not retained as accepted work; the documented interface permits correcting some rejected requests under the same number. Our immutable operation identity/contents contract needs a consistent rejection/reissue policy.
- Member 1's handoff proposes leaving an isolated operation UNRESOLVED while permitting explicit different work after fresh same-boot idle checks. Our unresolved-operation safe-state policy is still open. The user has been asked whether to stop new dispatch and require operator recovery; this must not be silently selected.
- Boot identity and history are RAM-only; station/global status is not proof that a particular part completed. The existing ledger explicitly protects unresolved part identity only while retained by the PC process.

Source references at reviewed commit: member1/production-a/docs/protocol.md, history.md, session.md, retries.md, gateway_handoff.md, continuation.md; firmware/main/production.c lines 119, 178-180, 217, 237-250; firmware/main/main.c lines 17-27 and 55; firmware/main/history.c; pc_test/gateway_client.py and retry.py.

Member 1 contains historical software/hardware PASS claims and honest NOT RUN limitations. They are contributed evidence, not freshly rerun integrated tests. Do not present them as proof of this future whole-system build.

### Member 2 gaps

The committed firmware currently connects to Wi-Fi and logs an IPv4 address. Complete length-prefixed TCP, bounded parsing, runtime inspection time/rule configuration, deterministic verdict generation on B, all operation lifecycle events, independent nonblocking execution, duplicate protection, boot/liveness handling, read-only result recovery, and a standalone test client. Network credentials remain local configuration.

### Operator screen and gateway gaps

Review the newly available Member 3 source before editing its visual design. Define a common HTTP/WebSocket contract and adapt its incomplete implementation. A click must not fabricate application state; correlate commands, fetch a fresh status snapshot after reconnect, and distinguish unavailable/stale display data.

Implement the gateway core, station adapters, operation controller, bounded inspection queue and reservations, settings sequencing, batch/part identities and records, state/control rules, result accounting, event logging, and evidence outputs. Preserve the distinction between part PASS/FAIL, technical execution error, command rejection, and unknown outcome.

## Planned execution sequence after relevant decisions are agreed

1. Preserve contributor history with ordinary merges into local main, resolving any conflicts transparently. Retain contribution ownership and historical evidence; no rewritten branch history.
2. Agree canonical interfaces against actual A/B/operator code and the PDF. Maintain requirements, decisions, interface versions, and explicit deferred M2 work.
3. Reuse existing transport/integrity helpers and implement the common gateway operation model/controller. First verify with deterministic simulated devices, without claiming hardware compliance.
4. Make the minimal A application/client changes needed for approved contracts, retaining SLIP/ATR/CRC and useful regression tests. Avoid competing serial readers/retry owners.
5. Complete B's TCP inspection implementation and standalone software tests using the same semantic reliability contract.
6. Implement gateway batches, queue reservation/full behavior, runtime settings, controls, and accounting. Test one part, overlapping production/inspection, and complete batches.
7. Complete and connect the existing operator screen without replacing its intended design. Verify command results, WebSocket freshness, disconnect/reconnect, and repeated clicks/retries.
8. Run appropriate host/software checks and firmware builds. Connect real devices for read-only discovery, then agreed functional tests; distinguish software evidence from actual board results. No automatic flash/reset is performed during this planning audit.
9. Exercise normal/slow/fast timings, queue full, Pause/Resume/Stop, ACK loss, duplicates, query/result races, stale/restarted devices, and bounded fault recovery. Collect serial logs, TCP captures, CSV evidence, diagrams, setup instructions, and contribution records.
10. Reconcile every relevant PDF requirement and deliverable, document remaining limitations honestly, and publish the reviewed main branch only when implementation/checks and repository write access are ready. No remote push is part of the current planning work.

## Decision rounds

Use short groups of yes/no choices; the user can select an answer or comment with questions/alternatives. Comments can qualify an answer. Keep required dependent implementation pending until the decision is made.

Round 1, integration scope and unresolved work:

- Complete B here? User answered Yes.
- Build a replacement operator UI? User answered No: reuse and complete Member 3's existing screen. Source location is now resolved by the newly fetched member3/operator-ui branch.
- Stop new dispatch on an unresolved production/inspection job and require operator recovery? Recommendation Yes for M1; user requested clarification, not approval. [Recovery and subsequent batch proposal](recovery-proposal.md) explains read-only reconciliation, conditional explicit resume, incomplete-batch closure, and a safe next-run transition. Alternative is an explicitly defined guarded-different-work policy, not automatic continuation.

Subsequent rounds must address O01-O06 from reliability-open-decisions.md with code-specific recommendations:

Separate batch_id is agreed in D009. The user has not yet approved the recovery/stop-dispatch proposal merely by asking for clarification or proceeding to another topic.

Current yes/no round (each recommendation is Yes; comments/questions are welcome):

1. O02: Register a queryable PENDING_VALIDATION record before sending RECEIVED. Acceptance remains a separate validated commitment; invalid requests never execute.
2. O03/IV: At most one active manufacturing job per ESP32, with the waiting inspection queue owned by the gateway. A and B can execute concurrently; communication and permitted controls remain responsive.
3. O03: Pause stops dispatch of new production/inspection jobs, retains the queue, and lets accepted work finish/report. Pause completes when dispatch is disabled, not when both devices become idle. Resume continues the same batch. Completion of an entire batch while paused and Fault/Stop overrides will be covered in the full state-transition table.

Answers to these three questions remain pending until received. They do not automatically approve Stop, cancellation, restart handling, or exact numerical timing.

- Receipt registration before RECEIVED (recommended Yes).
- Exact completion/cancellation meanings for every command, and no hidden accepted-job queue (recommendations to present individually).
- Canonical ID/op_no compatibility; choose whether to extend A's contract or explicitly revise the approved ID scheme, without silent aliasing.
- Read-only operation-specific lookup and one gateway controller rather than nested synchronous client retries (recommended Yes).
- Explicit receiver restart/closed-run handling and cache policy; do not promise automatic crash recovery from RAM-only histories.
- Finite deadline formulas/attempts/windows/horizon, freshness and late-result accounting, and operator schema ownership.

This is a plan, not approval of every candidate mechanism or numerical value above. Update decisions.md when the user answers each material choice.

## Current discussion focus

The user requested normal-chat decisions specifically for Member 2. See [ESP32 B integration decisions](member2-integration.md) for the initial role/framing/one-job recommendations and remaining interface topics. This steering changes the presentation/focus; it does not silently approve earlier unanswered choices or authorize deviations from approved rules.

The four Member 2 recommendations are now approved as D010. The portable transport code has been compiled with MSVC and exercised through ten real loopback checks. Tests do not substitute for an ESP-IDF build or board validation. The existing firmware callback intentionally logs framed payload lengths without accepting jobs until configuration/rule/query/result contracts are agreed.
