# Member 3 gateway integration contract v1

This is the proposed interface implemented by the operator UI and its test gateway. No real gateway or ESP32 implementation was present in this workspace. Member 4 must implement these endpoints, or agree on changes to the adapter in `transport.js` and validation in `protocol.js`. Paths, limits, sequence rules and cache policy below are team interface choices, not verbatim examiner requirements.

## Ownership

- UI: operator inputs, HTTP command IDs, bounded retries, status rendering, stale detection, reconnect synchronization and event-driven toy animations.
- Real gateway: configure/validate both ESPs, job IDs, queue reservations, scheduling, timeout/retry policies, device heartbeats, deduplication, batch state, truthful command completion and matching device results.
- ESP32 B: calculates actual PASS/FAIL using the runtime N/K rule. The UI never calculates verdicts. The test server's software verdicts are only for standalone UI tests.
- Cats and puppies are decorative alternation by part ID. They do not change the production or inspection rule.

## Hosting and connection

Preferred: gateway serves the UI assets and API on the same HTTP origin, e.g. `http://192.168.137.1:8080/`. Open that URL on the operator PC, and put that same origin in the Gateway address field. No frontend build or Node installation is required. There is no automatic simulation fallback.

Cross-origin development: serve the UI at `http://127.0.0.1:8765` and the gateway at `http://127.0.0.1:8080`. The gateway must permit the exact UI origin, handle JSON POST preflight (`OPTIONS`, `Content-Type`), and validate the WebSocket Origin. Test gateway flag: `--allow-origin http://127.0.0.1:8765`. No cookies or custom authorization headers are used in this Milestone 1 contract. An HTTPS page must use an HTTPS/WSS gateway. Use `http://` URLs, not `file://`.

`gateway_id` is a unique ASCII boot/session ID, changed after every gateway restart or loss of command-deduplication history. `status_seq` is a nonnegative strictly increasing integer for each full snapshot within that boot. Do not restart sequence numbers under an unchanged boot ID. Keep sequences within JavaScript's safe integer range.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/status` | Fresh complete snapshot; `Cache-Control: no-store` |
| GET / WebSocket upgrade | `/ws/status` | Receive-only stream of complete status JSON objects |
| POST | `/api/start` | Request a batch and runtime settings |
| POST | `/api/pause` | Stop issuing new jobs; accepted work may finish |
| POST | `/api/resume` | Continue the same paused batch |
| POST | `/api/stop` | Abort active batch and preserve partial results |
| GET | `/api/commands/{cmd_id}` | Query application acceptance/completion after lost replies or reload |

Use UTF-8 JSON. The WebSocket sends status at least once per second even when counters do not change; a 200–500 ms cadence gives smoother timers and effects. The test server sends at 200 ms. Send immediately after commands and meaningful transitions. Every status is a full replacement, including every part. Partial/delta updates are not accepted by v1.

## Commands

Start:

```json
{
  "schema_version": 1,
  "gateway_id": "gateway-boot-7",
  "cmd_id": "cmd-c3b54899",
  "batch_size": 12,
  "production_time_ms": 2000,
  "inspection_time_ms": 3000,
  "N": 4,
  "K": 0
}
```

Pause, Resume and Stop use the same shape at their respective endpoint; here is Pause:

```json
{
  "schema_version": 1,
  "gateway_id": "gateway-boot-7",
  "cmd_id": "cmd-pause-21",
  "batch_id": "batch-17"
}
```

All new commands get a new `cmd_id`. A retry preserves the original ID, endpoint, gateway ID, batch ID and complete body. `gateway_id` is a precondition: reject an old boot's command without executing it. For controls, reject a different/ended batch ID. Preserve IDs across your downstream protocol translation and return them in matching results. Never send a new Start automatically after an uncertain result.

Proposed bounds shared by UI/test server: batch size integer 1–1000; timing integers 1–3,600,000 ms; N integer 1–1,000,000; K integer −1,000,000–1,000,000. The screen displays seconds and converts to whole milliseconds; maximum three decimal places. Align these agreed bounds with ESP capability before the demonstration. If incompatible, update UI input attributes, `protocol.js`, this contract and server validation together. The real queue capacity comes from gateway status; it is not fixed by the UI.

HTTP `202` application acceptance response:

```json
{
  "schema_version": 1,
  "gateway_id": "gateway-boot-7",
  "cmd_id": "cmd-c3b54899",
  "command": "start",
  "accepted": true,
  "phase": "accepted",
  "message": "Command validated and accepted."
}
```

For rejection return `409` for state/ID conflicts, `422` for validation, or another non-2xx status; use the same fields with `accepted: false`, `phase: "rejected"` and a useful `message`. A well-formed UI command must receive this matching response even on rejection. An unreadable body or invalid/missing command ID may return HTTP `400` with `{"error":"..."}`. Do not send HTTP success with `accepted: false`.

Delivery evidence is kept separate: matching HTTP response received means a round trip was observed. The gateway separately logs received commands and downstream byte delivery. An HTTP response without application acceptance/completion is not proof of finished work.

`GET /api/commands/{cmd_id}` returns:

```json
{
  "gateway_id": "gateway-boot-7",
  "cmd_id": "cmd-c3b54899",
  "command": "start",
  "phase": "completed",
  "result": "Batch started; both station configurations applied."
}
```

Valid phases: `accepted`, `completed`, `rejected`. Unknown ID: `404` with `{"gateway_id":"gateway-boot-7","error":"Unknown command"}`. Include recent results in every snapshot as well. Start command completion means the start/configuration operation finished and the batch entered Running; **batch completion is separate**, reported by `batch.outcome`. Pause completes once new work has been gated, even if accepted jobs are draining. Stop completes only when abort accounting is settled and late results cannot alter it.

Deduplication: store original request fingerprint, HTTP acknowledgement and terminal result by `cmd_id` for the entire gateway boot. Duplicate identical requests return the cached acknowledgement without executing again; a changed payload/endpoint under the same ID is rejected with `ID_CONFLICT`. Do not evict accepted IDs and later execute them again. The test server caps history at 10,000 commands and rejects additional new IDs rather than evicting. If the real gateway loses its cache, change `gateway_id` and reject commands targeting the old ID.

## Complete status example

```json
{
  "schema_version": 1,
  "type": "status",
  "simulation": false,
  "gateway_id": "gateway-boot-7",
  "status_seq": 42,
  "state": "Running",
  "fault": null,
  "settings": {
    "batch_size": 4,
    "production_time_ms": 2000,
    "inspection_time_ms": 3000,
    "N": 4,
    "K": 0
  },
  "batch": {"id": "batch-17", "target": 4, "outcome": "active", "elapsed_ms": 6500},
  "counts": {"produced": 3, "inspected": 1, "passed": 1, "failed": 0},
  "queue": {"size": 1, "capacity": 5, "part_ids": [3]},
  "stations": {
    "production": {"connected": true, "busy": true, "part_id": 4, "remaining_ms": 1500},
    "inspection": {"connected": true, "busy": true, "part_id": 2, "remaining_ms": 500}
  },
  "parts": [
    {"part_id": 1, "status": "pass"},
    {"part_id": 2, "status": "inspecting"},
    {"part_id": 3, "status": "queued"},
    {"part_id": 4, "status": "producing"}
  ],
  "command_results": [
    {"cmd_id": "cmd-c3b54899", "command": "start", "phase": "completed", "result": "Batch started; both station configurations applied."}
  ]
}
```

| Fields | Meaning |
| --- | --- |
| `schema_version`, `type` | Exact values `1`, `"status"` |
| `simulation` | Required boolean: `false` for real hardware; `true` labels test stations and simulated verdicts visibly |
| `gateway_id`, `status_seq` | Boot ID and update ordering/freshness; integers never go backwards within a boot |
| `state` | `Idle`, `Running`, `Paused`, `Fault` |
| `fault` | `null` or readable reason; required nonempty in Fault |
| `settings` | Applied runtime settings, not merely a proposed form value |
| `batch.id`, `target` | Stable batch ID, requested total |
| `batch.outcome` | `none`, `active`, `completed`, `aborted`; outcome is distinct from operating state |
| `batch.elapsed_ms` | Gateway-measured monotonic elapsed batch time; frozen in Fault/ended batches; continues while Paused |
| `counts` | Produced, inspected, passed, failed; passed + failed = inspected ≤ produced ≤ target |
| `queue` | Waiting parts only, excluding in-flight production and inspection; reserve space for in-flight production |
| `stations.*.connected` | Gateway's heartbeat/connection assessment, independent from UI connectivity |
| `stations.*.busy` | Whether an accepted job is active |
| `part_id`, `remaining_ms` | Matching active job and nonnegative remaining milliseconds; both `null` when not busy |
| `parts` | Exactly target records with unique positive integer IDs stable across all links; see status names below |
| `command_results` | Up to 100 recent accepted/terminal command records; full lookup remains available separately |

IDs used as strings (`gateway_id`, `batch.id`, `cmd_id`) are 1–128 ASCII letters, digits, `_`, `.`, `:`, `-`. Part IDs are positive safe integers. Keep IDs unique across actual jobs/batches and include batch identity when handling delayed messages. The UI does not require contiguous part IDs.

Part status: `waiting`, `producing`, `queued`, `inspecting`, `pass`, `fail`, `stopped`. A `stopped` toy may have been interrupted during production or inspection; authoritative produced counts must be preserved. Queue records must match `queued` parts; busy station records match the single `producing` / `inspecting` part. Queued parts may remain after abort as partial inventory. Ended batches have no busy stations. A completed batch has produced = inspected = target. On Fault, keep uncertain jobs explicit and freeze timing rather than silently recomputing a result.

Before any batch: `state: "Idle"`, `settings: null`, batch `{id:null,target:0,outcome:"none",elapsed_ms:0}`, zero counts, empty parts/queue, station IDs/remaining null, empty command results. Retain a completed/aborted batch snapshot until another batch is accepted so the UI can show final results. Do not discard final counts immediately into an empty Idle snapshot.

## Client failure and animation behavior

- WS opens, UI buffers updates, fetches GET status, applies it then buffered newer snapshots. Controls stay disabled until synchronization succeeds. Unknown fields are ignored; missing/contradictory required fields mark the connection stale.
- Updates with sequence ≤ last applied are ignored and do not refresh the watchdog. Changed boot IDs require a new synchronization; old IDs/results are never folded into the new batch.
- No advancing valid status for 3.5 seconds marks data stale and stops motion. Reconnect delay starts at 0.5 seconds and doubles to 8 seconds. Initial synchronization has a 6-second deadline.
- HTTP request deadline: 4 seconds. Maximum 2 send attempts (one automatic retry), exact same request ID/body. A manual retry is explicit and uses the same ID/body again, only on the original gateway boot and origin.
- Accepted command completion deadline: 15 seconds, checked every 2 seconds. If no terminal application result arrives, show an unknown/overdue outcome and retain its ID. This deadline applies to the Start/Pause/Resume/Stop operation, not the entire batch; coordinate it with real configuration and abort timeouts. Change `commandCompletionDeadlineMs` in `app.js` if the team agrees otherwise.
- One pending operator command at a time. Exact unresolved request is retained in browser session storage across reloads. On reconnect, lookup its status before allowing a new command. Unknown outcomes remain visible; operator can check, retry safely on the same boot, or acknowledge after reviewing current status. No automatic restart or automatic batch creation.
- Status, counters and verdicts come only from validated gateway snapshots. Seconds remaining and elapsed time are cosmetic estimates between snapshots using the browser's monotonic clock; reaching zero never marks a job complete. They freeze on stale/Fault. Clocks on different devices are never subtracted.
- Toy puffs/scans/verdict effects follow actual snapshot transitions, not button clicks. First synchronization does not replay historical results. Pause drains already accepted jobs before the workshop settles. Stop/stale/Fault stops active motion. Reduced-motion preference is honored.
- UI draws at most 200 toy cards and 20 queue-slot icons, while totals remain full-batch values. This is a rendering limit, not a production limit.

## Integration acceptance sequence with Member 4

1. Serve UI, GET status and WS on the real gateway. Verify boot identity, idle station connections and increasing status sequence.
2. Start one part. Confirm seconds become correct integer milliseconds in the HTTP request. Verify configuration reaches both ESPs and acceptance/completion use the original IDs.
3. Confirm A completion changes produced/queue; B's matching result changes inspected/pass/fail. UI must not decide the verdict.
4. Test a batch with slow inspection to fill the queue, then slow production so B waits. Queue cannot overflow with a production job already in flight.
5. Test Pause/Resume on the same batch; Stop retains partial counts. Ensure late old results cannot modify aborted/new batches.
6. Drop the HTTP response and resend the exact command ID. Only one operation occurs. Change payload under the same ID: reject.
7. Drop UI WebSocket traffic, reload the browser with a pending command, disconnect an ESP, and restart the gateway. Check staleness, recovery snapshot, Fault and unknown-command notices.
8. Capture HTTP/WS and device exchanges, serial logs, operator log export and screenshots. Record actual real-hardware outcomes. The supplied test-server checks are not a hardware acceptance claim.
