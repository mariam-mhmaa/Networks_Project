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

Production A and the integrated A → queue → B core are now in
`gateway.production`. See [the active A integration contract](../docs/member1-integration.md)
for the real USB/TCP command, bounded recovery and guarded continuation APIs.
Install `gateway/production/requirements.txt`. The older B-only command still
uses a simulated producer and remains useful for the assigned B test scope.
Member 3/operator HTTP/WebSocket integration is still separate work.
