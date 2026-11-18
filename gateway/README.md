# Integrated gateway

`gateway.operator` hosts Member 3's toy-workshop interface and the real
A -> reserved queue -> B asyncio core. See the [active operator contract](../docs/operator-protocol.md)
for controls, recovery, HTTP/WebSocket schema and limits.

```powershell
python -m pip install -r gateway/operator/requirements.txt
python -B -m gateway.operator COM5 192.168.137.20 --state-file gateway.sqlite3
```

Replace the port/IP with the actual stations, then open http://127.0.0.1:8080.
Only one gateway process may own those links. Preserve the SQLite state file.
No device port was opened during operator implementation/testing.

- `inspection`: TCP framing, B settings, bounded operation controller,
  inspection reservations, durable IDs and validated result accounting.
- `production`: SLIP/ATR/CRC serial adapter and integrated A/B scheduling,
  lifecycle, guarded continuation and two-station closure.
- `operator`: identified HTTP commands, full WebSocket status, operator lease,
  Pause/Resume/Stop/settings/recovery orchestration and same-origin assets.

The older `python -m gateway.inspection` uses a simulated producer and is a
B-only exercise. `python -m gateway.production` is the headless A/B exercise;
neither should run alongside the operator server on the same stations.

Software preview (MSVC required, localhost native C peers, no physical COM):
`python -B tools/run_operator_preview.py --state-file operator-preview.sqlite3`.
It is explicitly labelled test mode and is never a silent fallback.

Validation: 75 A/B regressions, 12 operator/native-peer tests and nine frontend
checks pass. Physical USB/Wi-Fi tests and browser visual QA remain unverified.
[A integration](../docs/member1-integration.md), [B contract](../docs/member2-protocol.md),
and [B hardware handoff](../docs/member2-test-handoff.md) remain applicable.
