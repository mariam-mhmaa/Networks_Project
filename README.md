# MCT431 Networks Project

Integration work is on main. The A/B firmware and gateway batch core are implemented, including runtime settings, B-calculated verdicts, lifecycle replies, duplicate/result recovery, boot/run fences, bounded deadlines, queue reservations and result accounting.

Start with the [Member 2 test handoff](docs/member2-test-handoff.md), [message/API contract](docs/member2-protocol.md), [gateway module](gateway/README.md), and [firmware](member2/esp32_b_inspection/README.md). Software checks and ESP-IDF builds pass; actual-board/network testing is assigned separately and has NOT been run here.

Member 1 USB serial integration and the real A → bounded gateway queue → B batch core are now implemented. See [Member 1 integration](docs/member1-integration.md) for the active contract and runnable command. Member 3's existing toy-workshop screen is now integrated through `gateway.operator`, including Pause/Resume/Stop, runtime settings, liveness and recovery controls. See the [operator run instructions and contract](docs/operator-protocol.md). The standalone B exercise uses a simulated production source and is not a whole-system batch demonstration. Approved decisions are in [decisions.md](docs/decisions.md); original references are in reference/. Contributor branches/history are preserved.

Current software validation: **100 checks pass** (75 A/B, 16 operator/capture, nine frontend checks). Browser visual QA is blocked by the browser access host; actual hardware testing remains deferred. No physical ESP32 or COM port was used for this UI work.

Two-PC phone-hotspot setup and optional flashing instructions: [setup guide](docs/two-pc-hardware-setup.md). Setup stops before batch testing.
