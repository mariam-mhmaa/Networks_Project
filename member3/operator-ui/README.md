# Little Toy Works operator interface

Member 3's cream/butter/powder-blue/pink/walnut workshop, cat/puppy cards and
motion assets are reused in the integrated project. The active server is
`gateway.operator`, not `mock_gateway.py`.

From the repository root:

```powershell
python -m pip install -r gateway/operator/requirements.txt
python -B -m gateway.operator COM5 192.168.137.20 --state-file gateway.sqlite3
```

Open http://127.0.0.1:8080. Use the actual A port and B IP. See the
[active contract and operator workflow](../../docs/operator-protocol.md).
For software-only preview use `tools/run_operator_preview.py` with MSVC.

Pause finishes current individual jobs and holds the remaining same batch.
Resume continues that batch. Stop safely ends it with actual PASS/FAIL and
unfinished counts; another Start creates a new batch. Closing/disconnecting
the controlling panel pauses new work after its finite lease, requiring explicit
Resume. Paused idle settings edits and guarded recovery controls are integrated.

Run `node member3/operator-ui/test_client.mjs` for nine current frontend checks.
The original mock, Python mock tests, examples, handoff and contributor evidence
are retained as historical design infrastructure. Their original schema/bounds
are superseded by docs/operator-protocol.md. They do not validate the real server.
Exact original contributor versions remain in the member3/operator-ui branch
at d1b8e696c169a94292a2081ace02f5938a8b03a0.

Current software verification is in ../../verification/operator. Actual browser
visual inspection is blocked by the browser access host, and hardware testing
is deferred; neither is claimed complete.
