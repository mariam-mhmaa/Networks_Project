# ESP32 B integration status

Updated 2026-11-18. The B firmware and gateway inspection subsystem are implemented. The source is on main; contributor history is preserved. See the [current protocol/API contract](member2-protocol.md), [teammate handoff](member2-test-handoff.md), and verification artifacts under member2/esp32_b_inspection/verification.

## Approved decisions

D010: gateway PC hotspot (router fallback), B as TCP server with one active controller, four-byte big-endian JSON-byte length and 1024-byte maximum, one active inspection with waiting work queued at the gateway.

D011: identified runtime configuration of inspection_time_ms/N/K, completion confirming applied settings, FAIL iff (numeric part_id+K) modulo N is zero, and settings frozen per accepted job. Configuration during active inspection is rejected BUSY.

D012: queryable registration before RECEIVED; fixed numeric bounds; explicit batch/part identity; configurable initial three-stage timing and finite request/query budgets; bounded retained history and boot/run fencing; Fault on unresolved work and explicit read-only reconciliation before further dispatch. The user approved all three remaining recommendation questions.

## Implemented code

- Firmware: inspection_app.c owns records/settings/timer/rule; inspection_protocol.c owns JSON/validation/publication; tcp_service.c/tcp_frames.c own bounded transport. main.c keeps ticking accepted work while network setup/reconnect is unavailable.
- Gateway: gateway/inspection owns wire adapter, IDs, operation controller, reservation queue, durable numeric part counter/evidence, once-only counts and Fault/reconciliation.
- A production integration hook reserves a slot before producing and queues only a matching production completion. Already reserved completions are retained during Fault.
- Standalone functional client and native fault-injection tests are available. Test-source production readiness is explicitly simulated.

Queue capacity and full policy are explicit settings; both block and Fault policies are implemented. Full-history admission refuses work instead of evicting still-valid accepted outcomes. The current contract documents the exact capacities and query high-water fence.

## Remaining work outside this implementation checkpoint

The assigned teammate must run physical ESP32/network tests and collect captures/serial evidence. No board has been flashed here. Host tests and firmware compilation do not prove hardware timing or radio reachability.

Member 1's serial protocol/ID compatibility and Member 3's HTTP/WebSocket/operator integration still need their separate implementation decisions and hookup. Whole-system Start/Pause/Resume/Stop semantics are not silently selected by B's low-level CLOSE/reconciliation API. Milestone 2 protocols/authentication/benchmarks remain separate.
