# Step 5C run instructions (client-only; no flash)

The consolidated final setup/build/app-only-flash/test commands, physical
acceptance evidence and minimal gateway example are in [acceptance.md](acceptance.md).

## Current approved continuation follow-up

No firmware build/flash is required. Run all software checks and the targeted
new hardware paths; unchanged old hardware suites need not be rerun:

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python pc_test/continuation_test.py --port COM3 --log results/continuation_hardware.json
```

Expected: 48 software tests and five targeted hardware groups PASS. Close
other readers first. The fixture intentionally resets RAM/restarts the board;
the operational APIs do not. Public API examples: docs/continuation.md.

## Retained Step 5C repeat instructions

From PowerShell in the repository subsystem folder `member1/production-a/`,
close all serial monitors. See [repository setup](repository_setup.md) for
configurable activation and dependencies.
Use the existing tools; the helper changes environment only in this terminal.

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
```

The verified ESP32-D0WD-V3 on COM3 already has the unchanged Step 5B firmware.
No build, flash or erase is required. The recorded layout/settings remain:
1 MB factory app at 0x10000; 2 MB image configuration on probed 4 MB flash.

```powershell
python pc_test/retry_test.py --port COM3 --log results/step5c_retries.json --csv results/step5c_retries.csv
python pc_test/framed_test.py --port COM3 --log results/step5c_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5c_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5c_history_regression.json
python pc_test/session_test.py --port COM3 --log results/step5c_sessions_regression.json
```

Activation and these Python commands suffice; do not flash unnecessarily.
All use 115200 8N1, no flow control, finite timeouts and automatic port cleanup.
Production/history tests intentionally pulse RTS/EN to reset volatile station
state; it records/drains startup output before transmitting production frames.
Do not run another monitor or script on COM3 simultaneously.

Expected: 34 software tests, nine retry groups, 29 protocol cases, six production
groups, eight history groups and six heartbeat/session groups PASS. Heartbeats are allowed
during invalid-request tests but cannot satisfy a request response.
Each runner ends with PASS and port_closed=True. JSON contains actual wire
bytes/events/results; console summaries and actual measurements are recorded
in docs/progress.md. A failing run exits nonzero and records remaining checks
as NOT RUN. The new retry suite intentionally omits selected responses and
expects some operation outcomes UNRESOLVED/FAULT/REJECTED as successful safety
tests; check group PASS/FAIL separately. Exact JSON/CSV traces are saved.

Targeted local-cache gateway check (historical configuration must not arm a
stale setting):

```powershell
python pc_test/gateway_cache_test.py --port COM3 --log results/step5c_gateway_cache.json
```

Gateway integration: read docs/history.md before sending production requests.
Production requests require the discovered boot_id, positive uint32 op_no and matching canonical
decimal suffix on the full cmd_id/job_id. A retry keeps both unchanged.
History is RAM-only, with old-session requests fenced by boot_id. Each history test ends at maximum op_no; a later
test deliberately resets state before use. Retry logic never resets the board;
only explicit test fixtures do. Automatic retransmissions obey docs/retries.md.

Read docs/session.md for read-only GET_STATUS, heartbeat fields and sequence
rules, PC fault latching and explicit recovery. Observe without resetting or
sending work:

```powershell
python pc_test/station_watch.py --port COM3 --seconds 30
```

The gateway ProductionRun example requires configure and explicit start after
connect_or_recover. While idle, call observe regularly so the PC processes
heartbeats and checks its monotonic deadline. Bounded retries apply only within
the same original operation/session; a fault never resumes work automatically.
Physical unplug/replug was subsequently performed; see docs/acceptance.md for
results and timing/fixture limits. Physical same-session external-power recovery
remains NOT RUN. Controlled heartbeat-loss testing is separate evidence.

The software suite compiles the actual portable C history module with the
existing Windows host GCC found on PATH. It does not install a compiler;
the ESP cross compiler cannot substitute for executing a Windows host test.

The historical raw Step 2 reader does not apply to the current firmware.
The legacy Step 3 reserved_test_id regression sends non-JSON text with ID 0;
it now checks invalid-production-payload silence, rather than rejecting every
ID 0 record. Valid JSON production requests are exercised separately.
