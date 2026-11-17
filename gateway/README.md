# Gateway inspection subsystem

The asyncio B client, operation controller and inspection queue are implemented.
No additional Python packages are required. See
[the teammate handoff](../docs/member2-test-handoff.md) and
[protocol/API contract](../docs/member2-protocol.md).

- inspection/client.py: B adapter, settings and shared ID allocation.
- inspection/controller.py: one owner for stage deadlines and bounded recovery.
- inspection/coordinator.py: reservations, durable part numbers, queue,
  validated result counts, Fault/reconciliation, explicit run closure.
- inspection/wire.py: bounded framing, one socket reader, boot/liveness context.
- python -m gateway.inspection: standalone functional exercise; A source simulated.

Member 1 serial integration and Member 3 HTTP/WebSocket/operator integration
remain separate. This package supplies their B-side hooks; it is not a
completed whole-project gateway or a full-batch hardware demonstration.
