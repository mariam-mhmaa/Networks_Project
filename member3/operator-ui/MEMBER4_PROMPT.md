# Prompt for Member 4 gateway integration

Copy the following prompt into the coding assistant working on Member 4's gateway:

---

You are implementing Member 4's gateway for MCT431 Milestone 1 in
`https://github.com/mariam-mhmaa/Networks_Project`.

Member 3's operator interface is ready for initial integration on remote branch
`member3/operator-ui`, inside `member3/operator-ui/`. Fetch and inspect that
branch, then bring the contribution into your integration branch using the
repository's normal review/merge process. Preserve existing work and do not
force-push, overwrite other members' branches or assume it is already in main.

First read these files in Member 3's contribution:

1. `member3/operator-ui/README.md`
2. `member3/operator-ui/GATEWAY_HANDOFF.md` — the exact proposed v1 API contract
3. `member3/operator-ui/protocol.js` — the status/settings validator the UI actually uses
4. `member3/operator-ui/transport.js` — HTTP/WS synchronization, retry and staleness behavior
5. `member3/operator-ui/app.js` — pending-command lifecycle and rendering
6. `member3/operator-ui/examples/` and `TEST_RESULTS.md`

Keep the approved cartoon toy-factory design: cats and puppies, cream/yellow/blue
and walnut colours, bold outlines, machines and event-driven animations. The
browser must not simulate real production or calculate real inspection verdicts.

You can run Member 3 independently before wiring hardware. From its subsystem
folder, use Python 3.10+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe mock_gateway.py --port 8080 --test-controls
```

Open `http://127.0.0.1:8080`. This is a **test gateway**, not the real gateway;
its verdicts are simulated and are not valid ESP32 evidence. Test commands:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_gateway.py
node test_client.mjs
```

Node 18+ is optional and is used only for the JS tests; the UI is buildless.
The test controls and cross-origin example are documented in README.

Implement the real gateway's UI-facing endpoints:

- `POST /api/start`, `/api/pause`, `/api/resume`, `/api/stop`
- `GET /api/status` returning a fresh complete snapshot
- receive-only `WebSocket /ws/status` streaming full snapshots at least once per second
- `GET /api/commands/{cmd_id}` for resolving lost replies and pending commands

Use `GATEWAY_HANDOFF.md` and the JSON examples for exact field names; do not
substitute a simplified shape. Snapshots require `schema_version: 1`,
`type: "status"`, `simulation: false` for real hardware, unique boot
`gateway_id`, increasing `status_seq`, system state and fault, applied settings,
batch ID/target/outcome/elapsed time, counts, queue IDs/capacity, both station
connections/busy jobs/remaining times, all parts and recent command results.
The UI starts disabled until a valid current snapshot arrives. It displays
at most 200 toy cards but tracks all batch counters.

Start carries the batch size, production/inspection milliseconds, N, K,
`cmd_id` and expected `gateway_id`. Other controls carry `cmd_id`,
`gateway_id` and `batch_id`. Preserve original IDs across protocol boundaries.
Reject stale boot/batch targets. Duplicate identical command IDs must return
the original response without re-executing work; a changed payload under the
same ID must be rejected. Retain deduplication through the boot or change
`gateway_id` if that history is lost.

Return a matching HTTP application acceptance/rejection separately from the
terminal command result in status and command lookup. Transport success does
not prove acceptance or completion. Start completion means both real stations'
configuration is confirmed and the batch is Running; batch completion is a
later, separate outcome after every target part is inspected. Keep Pause,
Resume and Stop semantics and partial-result accounting as documented. UI
timeouts are 4 seconds per HTTP attempt, maximum 2 attempts with the same ID,
15 seconds for command-operation completion, and 3.5 seconds for stale status.
Coordinate these policies with your device timeouts rather than weakening
uncertainty handling. A long batch is not subject to the 15-second command deadline.

Read the latest Member 1 handoff and real client/session APIs from
`origin/member1/production-a`, especially its current gateway handoff and
continuation/session/retry documentation. Read Member 2's latest branch
`origin/member2/inspection-b` and check which TCP job/configuration/result
features actually exist. The last inspected Member 2 README described Wi-Fi
connection only, not complete TCP inspection. Do not invent that device
contract or declare hardware integration complete without evidence. Keep
device communication behind adapters while incomplete links use explicit test stubs.

For the real run: A is USB serial with SLIP/ATR/CRC, B is length-prefixed TCP,
and only ESP32 B computes inspection PASS/FAIL using runtime N/K. The gateway
owns the bounded queue, reservation for in-flight production, scheduling,
heartbeats, duplicate suppression, fault handling and final accounting. The
operator UI consumes those real results; do not copy the mock's inspection
formula into the production gateway as a replacement for B.

Prefer serving the UI assets on the same origin as the real API. On the
operator PC, open the gateway's LAN URL and enter that origin in the screen's
Gateway address field. If serving separately, implement the documented exact
Origin/CORS/preflight/WS rules. Do not hard-code localhost as the real gateway
address on a different PC, silently fall back to a mock, or change the UI's
visual theme while adapting the connection.

Test one real part end-to-end first, then a full batch, both timing extremes,
queue filling, Pause/Resume/Stop, duplicate commands, lost replies, stale WS,
reconnection and gateway/device restarts. Keep old/uncertain results out of new
batches. Validate gateway snapshots with `protocol.js`. Preserve completed and
aborted partial results until the next batch. Record actual test outcomes,
HTTP/WS captures, serial/TCP evidence and remaining blockers. Member 3's
software checks passed, but real gateway/ESP32 integration and browser visual
acceptance remain pending. Finish by reporting what was integrated, tests run,
and which real-device capabilities still need implementation or verification.

---
