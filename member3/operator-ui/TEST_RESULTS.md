# Integrated operator verification - 2026-11-18

- 75 existing A/B/controller/serial regression tests: PASS.
- 12 operator service/native-C-peer tests, including real HTTP/WebSocket: PASS.
- Nine Node frontend/protocol/render checks: PASS.
- Browser visual/responsive inspection: NOT RUN; browser access host unavailable.
- Physical ESP32/USB/Wi-Fi tests: NOT RUN here; assigned separately.

Logs and source/theme integrity are in ../../verification/operator and
../../verification/station-integration. The native peers execute the shared
station C application; they do not model all hardware/network timing.
Existing firmware build evidence remains applicable because no ESP firmware
source changed in this operator integration.

The verification/ directory beside this file and the mock Python tests are
original contributor evidence at d1b8e69, retained without treating that mock
as the current integrated backend. The original TEST_RESULTS.md is available
in contributor branch history. The active contract is ../../docs/operator-protocol.md.
