# MCT431 Networks Project

Shared repository for the team's MCT431 project.

Subsystem implementations are contributed on separate branches for review. The Member 1 production-station contribution will live in `member1/production-a/` on branch `member1/production-a`.

Integration is underway on `main`. Member 2's Wi-Fi foundation is merged, and its bounded TCP/framing layer has ten passing native C/loopback checks. See the [Member 2 checkpoint](member2/esp32_b_inspection/README.md), [integration plan](docs/integration-plan.md), [approved decisions](docs/decisions.md), and [reliability contract](docs/job-lifecycle.md). Original references are retained in `reference/`. The inspection application and full-system integration are not complete; ESP-IDF build and real-device checks are not yet run.
