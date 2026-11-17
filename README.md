# MCT431 Networks Project

Shared repository for the team's MCT431 project.

Subsystem implementations are contributed on separate branches for review. The Member 1 production-station contribution will live in `member1/production-a/` on branch `member1/production-a`.

Integration is underway on `main`. Member 2's Wi-Fi foundation is merged, and its bounded TCP/framing layer has eleven passing native C/loopback checks. ESP-IDF v6.1.1 normal and optional diagnostic firmware builds pass with non-secret placeholder network settings. See the [Member 2 checkpoint](member2/esp32_b_inspection/README.md), [SDK and physical test procedure](docs/esp-idf-testing.md), [integration plan](docs/integration-plan.md), [approved decisions](docs/decisions.md), and [reliability contract](docs/job-lifecycle.md). Original references are retained in `reference/`. The inspection application and full-system integration are not complete; physical ESP32 communication tests are not yet run.
