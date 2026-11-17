# ESP32 B inspection station

The normal firmware now implements the B inspection application. The gateway counterpart is in gateway/inspection. See the [physical test handoff](../../docs/member2-test-handoff.md) and [protocol/API specification](../../docs/member2-protocol.md).

## Implemented

- Wi-Fi station and one-owner nonblocking TCP server, port 5001 by default.
- Four-byte big-endian length framing; bounded 1–1024-byte UTF-8 JSON messages.
- Identified CONFIGURE, INSPECT, QUERY and CLOSE operations with distinct lifecycle replies.
- Runtime duration/N/K settings, frozen per accepted job, and BUSY configuration rejection.
- FAIL iff (int64(part_id)+K) modulo N is zero, computed only here on B.
- Independent execution through missing ACKs/network loss, cache-before-publication completion, duplicate protection, and read-only result retrieval.
- One active inspection, bounded retained history, receiver boot identity and run retirement.
- Periodic heartbeat/status; bounded TX cannot block the inspection timer.

The firmware polls at 20 ms. A configured duration is a minimum with scheduling granularity, not a hard real-time guarantee. History is RAM-only; reboot changes boot identity and invalidates old requests.

## Configure and test

Use ESP-IDF for the actual ESP32 target. Configure hotspot credentials locally in menuconfig under Inspection Station Wi-Fi. For functional job tests, leave Inspection Station TCP / test-only echo disabled.

Run the standard-library Python functional client from the repository root:

~~~powershell
python -B -m gateway.inspection B_CURRENT_IP --parts 6 --inspection-ms 100 --rule-n 3 --rule-k -1 --queue-capacity 2 --full-policy block --state-file gateway-test.sqlite3 --events run.local.jsonl
~~~

The test source simulates production readiness; it does not test A's USB link or the operator UI. Normal firmware and diagnostic firmware builds pass with explicit non-secret placeholder Wi-Fi settings. Enter real credentials and rebuild before flashing. No physical board test has been run here.

Local sdkconfig, build output and credentials must stay out of Git. Binaries embed configured network credentials. Use B's verified current COM port and IP.

## Software checks

On Windows/MSVC 2022:

~~~powershell
python -B -m unittest discover -s tests -v
~~~

The tests compile actual C application/protocol/transport sources and exercise the actual Python gateway over real loopback TCP. Evidence is in verification/application_summary.json, application_tests.log and esp_idf_build_summary.json. Host checks do not prove ESP32 radio/timing behavior.

## Optional echo diagnostic

INSPECTION_TRANSPORT_DIAGNOSTIC defaults off. Enabling it replaces the application handler with framed echo, solely for a transport round trip. tools/probe_transport.py is only for that image; tools/exercise_application.py is for normal application firmware. Echo is never a job acknowledgement or verdict.

## Historical Wi-Fi evidence

On 2026-11-17 the contributor joined an iPhone hotspot and obtained 172.20.10.3. That is historical association evidence, not the final integration network or a current IP assignment.
