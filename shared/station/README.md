# Shared station operation engine

Both ESP32 applications compile this transport-independent lifecycle/parser.
`station_app` retains immutable commands/jobs, an active timer, bounded query
snapshots and retirement/part fences. `station_protocol` validates flat JSON,
fingerprints semantic contents, serializes replies and emits heartbeats via a
nonblocking caller-supplied queue callback. Returning false never stops work.

The runtime production profile selects PRODUCE / production_time_ms / produced
results. The inspection profile selects INSPECT / inspection_time_ms / N / K /
verdict. Internal `S_JOB` and `duration_ms` are station-neutral. No gateway or A
code computes B's verdict. The caller supplies its monotonic milliseconds and
boot identity and owns all transport scheduling; no hidden retry task exists.

B's inspection_app/protocol files are compatibility adapters to this single
implementation. Vendored cJSON 1.7.19 remains unmodified under its MIT license.
See docs/member1-integration.md and docs/member2-protocol.md for active contracts.
