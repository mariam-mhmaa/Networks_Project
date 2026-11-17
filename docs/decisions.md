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

Exact numeric/duration bounds, unique numeric part allocation, configuration versioning/wire schemas, receipt registration, cache/restart policy, and operation-controller limits remain open. Approval of these three choices does not mean the inspection application or complete gateway-B integration has been implemented. The user separately authorized installing ESP-IDF and testing communication; the current hardware checkpoint is the implemented transport foundation.

A default-off framed echo diagnostic and a standalone PC probe support the authorized physical transport test. Diagnostic replies are never lifecycle acknowledgements or inspection results. SDK installation and both firmware build variants pass; no board has been flashed and physical communication remains untested. See [esp-idf-testing.md](esp-idf-testing.md).

## Open decisions

- Integration review is in [integration-plan.md](integration-plan.md). The user approved completing B here and directed reuse/completion of Member 3's existing screen. The newly fetched member3/operator-ui branch resolves its source location. The unresolved-operation dispatch policy is still pending. Existing contributor contracts do not override the official PDF or user decisions. The user now wants normal-chat discussion focused on [Member 2 integration](member2-integration.md), rather than additional form-based planning questions for this step.
- The next question round asks about queryable receipt registration, one active manufacturing job per station with the queue only at the gateway, and Pause-as-dispatch-stop while accepted work finishes. These are recommendations awaiting answers, not approved implementation rules.
- Three-stage deadlines and R01-R10 are approved. O01-O06 in [reliability-open-decisions.md](reliability-open-decisions.md) cover precise anchors/limits, receipt registration, command effects, restart/cache policy, late-result accounting, and query/wire ownership. The historical [reliability review](reliability-review.md) retains candidate mechanisms; earlier numeric retry suggestions and the two-timeout simplification are not approved specifications.
- Batch/part identifier formats, detailed parent/child operation correlation, and duplicate/result retention across restarts.
- Exact lifecycle message schemas and operator HTTP/WebSocket representation.
- Start/configuration sequencing and Idle/Running/Paused/Fault transitions.
- Pause, Resume, Stop, Fault recovery, and treatment of unfinished work.
- Inspection queue capacity, full policy, and reservation for production already in progress.
- Deadlines, retry limits, heartbeat/stale thresholds, and restart/disconnection handling.
- External message contracts, serial encoding details, TCP payload format, and operator endpoints.
- Valid inspection-rule parameter and duration ranges (the rule itself is approved).
- Serial library and exact runtime/dependency versions.
- Requirement-by-requirement implementation and verification register, including submission ambiguities.

Queue capacity five and the guide's Pause/Stop policies remain proposals. The TCP framing choice and inspection rule are approved in D010-D011.

## Reference documents already read

- Official repository reference: ../reference/MCT431 Project Fall 26.pdf
- Team proposal repository reference: ../reference/MCT431_Milestone1_Team_Development_Guide.docx

The supplied transcript begins with the user's acceptance of Member 4. Earlier role-selection messages were not included. This log records agreed context, not a claim to contain the entire original chat.
