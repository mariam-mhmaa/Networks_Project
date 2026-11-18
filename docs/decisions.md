# Gateway design decisions

Last updated: 2026-11-17

## Scope and working approach

- The user is Member 4, responsible for the Gateway.
- Current implementation scope is Milestone 1. Milestone 2 requirements remain tracked as deferred work.
- The official project PDF governs technical requirements. The team development guide is a proposal; its suggestions may be replaced by jointly approved decisions consistent with the PDF.
- Explain concepts and agree on material design decisions together. The assistant may choose implementation checkpoints once the relevant design decisions are approved. Review implemented behavior and actual test evidence with the user.
- Ask before implementing any alternative that changes approved behavior or architecture. Routine implementation within an agreed contract and explicitly requested documentation updates do not require repeated permission.
- As of 2026-11-17, the authoritative working copy is the existing Networks_Project at Semester7/Networks/Project/Networks_Project, on local main. Contributor branches have been inspected; all new project work belongs here. Earlier documents in Documents/ChatGPT/Industrial Communication are historical source snapshots.
- Member 2's transport foundation is now implemented and host-tested as recorded in D010. The inspection application, gateway controller, complete system, and hardware verification are not complete.

## Approved decisions

### D001 Separate the core from communication adapters

Keep batch coordination separate from USB serial, TCP, and operator HTTP/WebSocket communication details. Adapters report events and execute communication actions; the core decides application behavior.

### D002 Give the core sole ownership of application state

Only the core changes authoritative batch state, part/job records, queue membership, and counters. Communication components deliver events rather than directly changing these records.

### D003 Use an event loop with worker threads where needed

Run independent asynchronous communication activities and a core task on an event loop. Isolate unavoidable blocking I/O in worker threads and use thread-safe handoff back to the loop. Worker threads do not mutate core state. Keep core event handling short; represent outstanding device operations as pending records instead of waiting inside the core for a particular device result.

Deadline monitoring is distinct from USB serial communication. Its responsibility is to notify the core about expired deadlines; a central monitor versus individually scheduled timers remains an implementation detail to resolve.

### D004 Use Python, asyncio, and FastAPI

Python is the gateway language. Use asyncio for concurrency and FastAPI for the gateway's HTTP/WebSocket operator interface. The operator screen remains Member 3's responsibility. Exact dependency versions and the serial library are not yet selected; check Windows compatibility before choosing serial integration.

### D005 Run one authoritative gateway application process

Maintain a single core instance. Do not start multiple independent web worker processes with separate in-memory gateway states.

### D006 Use explicit command/job ID fields with readable action prefixes

Commands use `cmd_id`; jobs use `job_id`. Finalized ID shape: `ACTION-ISSUER-SESSION-COUNTER`, with a full UUID4 session token and independent counters per action. One small generator per issuing application owns allocation; receivers treat IDs as opaque and use explicit action fields for routing. Retries, responses, and protocol translations retain the original ID. Same-ID/different-request conflicts must be rejected. The detailed decision and remaining verification are in [identifiers.md](identifiers.md).

This decision implements command/job identity, not the complete batch/part identity model or durable duplicate/recovery behavior.

### D007 Track distinct lifecycle evidence and handle missing replies at every stage

For the custom serial/TCP application links, the agreed normal case uses three replies total: `RECEIVED`, `ACCEPTED`, and `COMPLETED` with the explicit result. Rejection is separate. Later valid evidence can establish prior stages without fabricated ACK observations. Timeout means uncertainty; permitted retransmission preserves original identity/contents and cannot repeat execution. One operation controller owns bounded recovery; exact numerical budget allocation is open. See [job-lifecycle.md](job-lifecycle.md). Timing, operator-interface representation, and restart/fault policies remain open.

### D008 Confirm three-stage architecture and universal reliability rules

On 2026-11-17 the user explicitly confirmed three-stage deadlines and R01-R10, recorded in [job-lifecycle.md](job-lifecycle.md). Accepted ESP32 work is independent of gateway ACK reception; cache and promptly publish completion; valid later evidence establishes earlier facts without invented timestamps; preserve retransmitted identity/contents; prevent duplicate execution; bound recovery attempts/windows/absolute horizon; progress cannot indefinitely renew deadlines; one controller owns decisions per operation; status reads cannot initiate target work; apply these principles to all commands/jobs.

This approval does not select arbitrary numeric retry candidates, receipt registration, receiver reboot/persistence mechanisms, exact command completion/cancellation effects, or late-result accounting. O01-O06 in [reliability-open-decisions.md](reliability-open-decisions.md) give the remaining joint decisions. [reliability-verification.md](reliability-verification.md) maps all ten rules and relevant PDF requirements to planned checks, all not run.

### D009 Keep batch identity separate from command/job identity

The user agreed to a separate batch_id. Include and validate it on batch-scoped commands/jobs, related replies, and live status. Allocate one batch identity for a newly accepted Start and return the same batch for duplicate submissions of that original Start command. Do not embed or rename the batch into existing command/job IDs; their counters do not reset between batches in the same issuer session. Device-wide discovery and heartbeats need not invent a batch context.

The exact batch ID generation/format, complete part-identity model, and receiver enforcement of closed run scopes remain open. Carrying a batch_id alone does not prevent old execution requests or stale results from affecting another run; receivers/controllers must validate the context.

### D010 Approve Member 2 network and transport foundation

The user approved all four Member 2 recommendations: use the gateway PC hotspot for integration (subject to actual support/reachability, router fallback), B as a TCP server with one active gateway connection, a four-byte big-endian length followed by up to 1024 UTF-8 JSON bytes, and one active inspection job on B with waiting inspections queued at the gateway. These are implementation choices within the required TCP link.

The existing Member 2 branch has been merged into local main with history preserved. The framing/server foundation is implemented; eleven native C/Windows loopback tests pass. Normal and optional diagnostic firmware compile/link with ESP-IDF v6.1.1 using non-secret placeholder Wi-Fi settings. No application inspection/configuration/query schema has been silently selected. One-active-job enforcement awaits that application layer; hotspot setup, physical TCP reachability, and ESP32 testing are not yet verified.

### D011 Approve Member 2 configuration, inspection rule, and active-job settings

The user approved runtime configuration by identified command carrying inspection_time_ms, N, and K, with completion confirming actual applied values before dependent jobs. B computes FAIL when (numeric part_id + K) mod N == 0 and PASS otherwise. N is positive and K is an integer. An accepted job keeps its settings unchanged; a new configuration while inspection is active is rejected as BUSY and may be submitted as a new operation when idle.

At the D011 checkpoint, numeric bounds, part allocation, schemas, receipt registration, cache/restart policy and operation-controller limits were still open. D012 below records their subsequent B-specific approval and implementation; D011 alone had not authorized those remaining choices.

A default-off framed echo diagnostic and a standalone PC probe support the authorized physical transport test. Diagnostic replies are never lifecycle acknowledgements or inspection results. SDK installation and both firmware build variants pass; no board has been flashed and physical communication remains untested. See [esp-idf-testing.md](esp-idf-testing.md).

### D012 Finalize and implement the gateway–B application

On 2026-11-18 the user explicitly approved all three remaining recommendation questions:

- Register a queryable record before RECEIVED; retain rejection/results under the original ID. inspection_time_ms is 1–600000, N is 1–2147483647, K is signed int32, and part_id is positive uint32. Preserve separate batch/part context.
- Use configurable initial receipt/acceptance windows of one second, completion allowance of configured duration plus two seconds, at most two original-request retransmissions before acceptance and two read-only recovery queries, one-second query response windows, and an immutable absolute cap of configured duration plus ten seconds. Progress cannot renew these limits.
- Bound the run to up to 64 inspection jobs; reserve history before acceptance and retain configuration/job outcomes through explicit idle closure. Reject retired scopes, use a fresh boot identity after restart, stop inspection dispatch on unresolved work, and require explicit reconciliation before proceeding.

The B firmware, gateway B adapter/controller/queue/accounting, and standalone client are implemented under [member2-protocol.md](member2-protocol.md). The receiver uses a boot-scoped monotonic run fence, 64 job records, 16 command records with a reserved CLOSE slot, and eight fenced read-only query snapshots. Full history refuses admission rather than dropping accepted outcomes. Gateway numeric part allocation/evidence persists in a local SQLite ledger; execution is not automatically restored after a gateway/device restart.

Queue capacity and block/Fault policy are explicit required settings; both behaviors are implemented and tested. B's low-level idle CLOSE and explicit reconciliation APIs do not silently define whole-system operator Pause/Stop semantics. Software tests and firmware builds pass; hardware/capture testing is assigned to the teammate and remains NOT RUN here.

This supersedes earlier B-specific “not implemented/pending contract” status text in D010-D011 and historical planning/review documents. Member 1 identity/serial compatibility and Member 3/full operator integration remain separate.

### D013 Approve Member 1 shared identity and run-history model

On 2026-11-18 the user answered Yes to Member 1 recommendation 1 and confirmed
we may adapt its implementation rather than follow the contributor's design
exactly. A will accept the shared opaque cmd_id/job_id scheme without a
mandatory :op_no suffix/separate application op_no, expand IDs to the shared
limit, and use boot/run fencing with retained outcomes for up to 64 production
jobs in a run. ATR sequence numbers remain separate transport correlation.

Recommendations 2 (one active production job and pre-production queue
reservation) and 3 (stop new A/B dispatch on unresolved production) remain
pending; the user requested clearer explanations and a check of examiner-
configured timing requirements. Those questions are not approval. See
[member1-integration.md](member1-integration.md).

### D014 Approve Member 1 scheduling and queue reservation

On 2026-11-18 the user approved decision 2: one active production job on A,
no hidden accepted-job queue there, inspection capacity reserved at the
gateway before production starts, the same part/batch identity passed on
confirmed production completion, and the configured block/Fault policy
applied before further production. A and B may run concurrently on different
parts using examiner-assigned durations.

Decision 3 remains under discussion. The user explicitly rejects permanent
system blockage solely because an old outcome/root cause cannot be learned,
and wants dispatch/future work possible with incomplete batches. The revised
recommendation is temporary hold followed by explicit incomplete closure and
safe new-run transition without requiring the missing result. Same-batch
guarded continuation is an alternative needing additional retirement and
accounting rules. Neither specific revised workflow is approved yet.

### D015 Recovery clarification and revised continuation recommendation

On 2026-11-18 the user agreed with retaining uncertainty correctly, preventing
old/duplicate work, safe readiness checks, and not permanently blocking future
work solely because a part's outcome is unknown. The user asked for the best
appropriate design rather than choosing solely to minimize implementation,
and asked whether INCOMPLETE must be entered manually in the GUI.

The revised recommendation is guarded continuation of other original-target
parts in the same batch, with explicit per-job retirement/fencing before
affected-station reuse, and incomplete closure/new batch as fallback when
safe isolation cannot be established. This is not implemented or approved
in its detailed form yet; it would extend D012's existing B recovery policy.
The gateway computes unresolved counts/final completion status automatically;
operator workflow actions never fabricate or manually assign factual results.
See member1-integration.md for the proposed guards and current scope.

### D016 Authorize A extension and require complete partial-batch reporting

On 2026-11-18 the user explicitly authorized extending A to the updated
recovery design and clarified that an incomplete batch must still show
confirmed PASS/FAIL totals for the rest. Always report those totals alongside
unresolved and other unfinished counts; uncertainty is never converted to
FAIL, and the gateway computes factual counts/status automatically.

The user requested a clearer explanation of isolation. It means a separately
tracked uncertain part with its original identity retained, dependent work
withheld until evidenced, and prevention of delayed duplicate execution.
Affected-station reuse and reservation release require readiness/inactivity
and fencing; accepted work is not implicitly cancelled. Exact retirement
messages and shared A/B mechanism details remain to be specified, not assumed
implemented by this discussion.

### D017 Finalize A contract and authorize implementation

On 2026-11-18 the user approved all remaining A recommendations: production
duration 1–600000 ms, positive uint32 part identity, frozen per-job settings,
the shared bounded recovery profile, and identified duplicate-safe RETIRE
on A and B for guarded same-batch continuation. Unknown parts never become
FAIL or replacement work. Active targets return BUSY; completed targets
return their actual results; safely unknown targets retain job/part fences.
Contradictory/lost history requires incomplete closure/new-run recovery.

A initially emits a heartbeat every second with a five-second stale limit;
B retains its initial 500 ms/1.5 s profile. All numerical heartbeat/deadline
settings are initial engineering values to validate/tune on hardware. Tuning
does not remove bounded attempts, immutable deadlines or explicit recovery.
No more A-specific behavior decisions block implementation. Whole-system
operator Pause/Stop and Member 3 screen integration remain separate scope.

### D018 Implement and verify the A/B gateway core

On 2026-11-18 the approved A integration was implemented on main, preserving
Member 1's source/history and its CRC/SLIP/ATR transport. A and B now share
the operation engine, identified read-only lookup and duplicate-safe RETIRE.
The gateway integrates real serial production, reserved inspection capacity,
TCP inspection, bounded recovery, explicit guarded same-batch continuation,
partial totals, two-scope closure and explicit different-boot recovery.

Verification passed: 53 inspection/controller/TCP tests, 19 native A/integrated
batch/CLI tests and three serial-worker tests (75 total), plus application
ESP-IDF v6.1.1 builds for both ESP32 targets. Source hashes and logs are in
verification/station-integration. No physical USB/Wi-Fi/board test was run;
existing contributor hardware evidence remains historical. Heartbeat/timeouts
are initial configurable engineering values pending real hardware calibration.

The active implementation/commands are in member1-integration.md. Whole-system
operator Pause/Stop behavior and Member 3 HTTP/WebSocket screen integration
remain separate; this is not a claim that the complete Milestone 1 GUI/capture
demonstration has been delivered.

### D019 Approve whole-system operator behavior

On 2026-11-18 the user approved Pause gating new A/B dispatch while current
accepted jobs finish; explicit Resume continues the same batch. Stop finishes
current jobs, performs bounded recovery and confirms old-scope closure, then
ends the batch with actual PASS/FAIL and automatic unfinished reporting.
A new Start creates a new batch. Screen loss pauses new dispatch after a
finite liveness interval and never automatically resumes on reconnect.
Paused fresh/idle stations may receive acknowledged timing/N/K changes for
future jobs; past results/settings and batch target/queue policy remain fixed.
Recovery controls and unresolved-part reporting are required.

### D020 Implement the operator/gateway integration

Member 3's branch is integrated with its overall workshop visuals preserved.
The authoritative asyncio core now backs identified HTTP controls and full
WebSocket status through gateway.operator. One controlling operator lease,
immutable duplicate-safe command registration, finite send/completion budgets,
read-only lookup, guarded continuation and explicit closure/restart controls
implement D019 without browser-generated outcomes. Station links remain open
between closed batches; ordinary closure does not reopen/reset the serial port.

96 software checks pass: prior 75 station/transport regressions, 12 operator
native-C-peer/HTTP/WS tests and nine frontend checks. No physical hardware was
used, and actual browser visual QA is blocked by the unavailable browser host.
See operator-protocol.md and verification/operator. Earlier pending operator
items in historical reviews are superseded by D019-D020.

### D021 Prepare the actual two-PC phone-hotspot setup

The user specified a Windows 11 gateway PC with A over USB, B powered from
this operator PC and connected by Wi-Fi to a phone hotspot, and a separate
operator browser. Both PCs and B must share a reachable LAN. The user
confirmed integrated firmware and app-flash project paths (A COM3, B COM6);
this review changes only PC-side code, not ESP firmware. No reflash is required
for these changes. Actual COM/IP assignments remain setup facts to verify.

Added append-only station JSONL evidence with raw A SLIP/ATR TX/RX hex and
capture-health reporting through a bounded background writer. Added explicit
new-boot recovery between closed batches, preserving the ended batch report
instead of leaving the Idle screen without recovery. Remote-origin HTTP
admission, native peers/capture and idle reboot recovery checks pass. Total
software checks: 100 (75 station, 16 operator/capture, nine frontend checks).
No physical test/flash or network/firewall setting change was performed here.
The user requested setup first and hardware test cases in a later exchange;
follow two-pc-hardware-setup.md and stop before Start.

### D022 Retain batch history, use readable aliases, separate evidence

The user approved all five discussed changes on November 19: preserve queue
reservation and both queue-full policies; retain earlier batches in the existing
SQLite file with a read-only History view and manual downloads only; separate
application history from raw serial and Wireshark evidence; persist short display
aliases while retaining original full protocol IDs; and correct the finished
batch feedback instead of leaving the earlier Start completion message visible.

Implementation leaves ESP firmware and the station protocol unchanged. Reports
are projected from durable application events, including pre-update journals.
Stage observations exclude periodic heartbeats. Query acknowledgement times
remain attached to query IDs; recovery never creates missing original ACK times.
Batch summaries reference operation outcomes instead of repeating full outcomes
in every saved view. Restarted history is read-only and cannot resume execution.
Display aliases survive when the same gateway database is retained.

The user reported two consecutive four-part hardware batches. The supplied
latest-batch JSON confirms four produced/inspected, two PASS, two FAIL, zero
unresolved and no recovery attempts for its eight station jobs. Only the latest
batch's detailed records were in that export. The old gateway.local.jsonl has
not yet been received, so the first batch and raw transport evidence have not
been independently audited. Both ESPs are now USB-powered on the gateway PC;
A uses COM3 for data, B uses Wi-Fi and its USB connection only for power.

See [batch-history.md](batch-history.md) for update and log-transfer steps.

### D023 Simplify operator evidence and explain station recovery

The user requested simpler operation names, station labels, short IDs throughout
the GUI, readable Details instead of raw JSON, one batch-report download and
pagination hidden when unnecessary. These presentation changes preserve full
wire identities in the database and downloaded technical evidence, with no
firmware, execution, recovery-policy or acknowledgement-timestamp change.

The old live-batch evidence button returned silently after restart because there
was no live batch ID. It is removed in favor of Download batch report for the
selected History entry. Download uses the existing read-only attachment endpoint
directly from the click, including when no current batch exists. The selected
report button is disabled during loading/failure; downloads are formatted JSON.
The separate browser-message export is explicitly optional troubleshooting.

Recover A/B labels become Confirm restarted A/B, making clear that they verify
an already restarted ESP rather than rebooting it or repeating jobs. Documentation
distinguishes A's raw USB serial trace, both stations' application evidence and
B's Wi-Fi TCP capture. Review of the supplied old log verified 64 station
operations across five closed batches and all submitted work for parts 1-22,
with matching three-stage replies, expected verdicts and valid captured A CRCs.
Read-only inspection of the running updated gateway also confirmed five saved
completed batches, Idle readiness, connected A/B and zero raw-trace drops/errors.

## Remaining verification and decisions

- No further operator-policy decision currently blocks implementation.
- Validate/tune initial heartbeat, lease and deadline numbers on real hardware
  while retaining bounded attempts and immutable limits.
- Perform actual browser visual/responsive QA when browser access is available.
- Run the assigned ESP32 USB/Wi-Fi and complete-system examiner scenarios,
  including transport captures and evidence required by the PDF.
- Milestone 2 security and any unresolved submission-format ambiguities remain
  outside this Milestone 1 software integration claim.

## Reference documents already read

- Official repository reference: ../reference/MCT431 Project Fall 26.pdf
- Team proposal repository reference: ../reference/MCT431_Milestone1_Team_Development_Guide.docx

The supplied transcript begins with the user's acceptance of Member 4. Earlier role-selection messages were not included. This log records agreed context, not a claim to contain the entire original chat.
