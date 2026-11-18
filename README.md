# MCT431 Networks Project

Integration work is on main. The A/B firmware and gateway batch core are implemented, including runtime settings, B-calculated verdicts, lifecycle replies, duplicate/result recovery, boot/run fences, bounded deadlines, queue reservations and result accounting.

Start with the [Member 2 test handoff](docs/member2-test-handoff.md), [message/API contract](docs/member2-protocol.md), [gateway module](gateway/README.md), and [firmware](member2/esp32_b_inspection/README.md). Software checks and ESP-IDF builds pass; actual-board/network testing is assigned separately and has NOT been run here.

Member 1 USB serial integration and the real A → bounded gateway queue → B batch core are now implemented. See [Member 1 integration](docs/member1-integration.md) for the active contract and runnable command. Member 3 operator HTTP/WebSocket integration remains separate work. The standalone B exercise uses a simulated production source and is not a whole-system batch demonstration. Approved decisions are in [decisions.md](docs/decisions.md); original references are in reference/. Contributor branches/history are preserved.
