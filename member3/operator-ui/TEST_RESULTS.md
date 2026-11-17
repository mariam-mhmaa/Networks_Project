# Gateway preparation verification

Checked on 17 November 2026. These results concern the Member 3 interface and its simulated test gateway, not real ESP32 hardware.

## Passed

- 7 Python checks: duplicate/conflicting IDs, invalid settings and old boot rejection, Pause/Resume/Stop, bounded queue with in-flight reservation, HTTP/WebSocket complete batch and duplicate request, Fault/restart/reconnect, CORS/malformed input/static asset isolation.
- 7 JavaScript checks: strict status validation, buffered synchronization, stale detection/restart recovery, identical-ID retry and separate acceptance, malformed-status rejection, same-boot sequence rollback rejection, operator pending-command/UI behavior.
- The operator behavior check also verifies no optimistic state change on Start, seconds-to-milliseconds conversion, repeated-click suppression, overdue acceptance remaining unresolved, countdown reaching zero without completing work, and no replay of completion effects after synchronization.
- 128 generated full snapshots covering production, queue filling, Pause/Resume, completion, Fault, Stop and restart passed the exact JavaScript protocol validator used by the browser.
- The documented JSON status example passed that same validator.
- Test dependency: Python 3.11.15, aiohttp 3.14.5. The HTTP/WebSocket tests use real local sockets through aiohttp's test server/client. Client tests use deterministic WebSocket/DOM doubles; no browser rendering is implied.

Commands and code are in `README.md`, `test_gateway.py` and `test_client.mjs`. `requirements-tested.txt` records installed versions for repeatable dependency setup.

## Still required with the team

- Member 4 must implement/agree on the proposed v1 contract and confirm bounds, timing policies, command semantics and hosting.
- Real gateway + ESP32 end-to-end batch and failure tests.
- Real packet captures, serial logs, screenshots and final hardware setup instructions.
- Browser visual inspection: automation host was unavailable in this environment. The approved artwork/theme files were retained; connection UI and gateway-driven behavior were verified programmatically.
- Milestone 2 MQTT/authentication/benchmarking features are outside this handoff.

The Python tests pass with aiohttp advisory warnings about string application keys and an OPTIONS handler; these do not affect the observed test outcomes.
