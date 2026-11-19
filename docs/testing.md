# Testing and evidence

Run one physical case at a time. Review its evidence before assigning the next.
The current cleanup does not perform physical tests, flash either board, reset
devices, change the hotspot or contact the running gateway.

## Software verification

Install root `requirements.txt` in Python 3.11 and provide MSVC C/C++ tools.
The native harness replaces UART/radio I/O with localhost transport while
compiling the actual C application/parser. It does not prove USB electronics,
RF timing or physical restart behavior.

```powershell
.\.venv\Scripts\python.exe -B tools/verify_operator.py
.\.venv\Scripts\python.exe -B tools/verify_station_integration.py
.\.venv\Scripts\python.exe -B tools/verify_duplicates.py
```

Expected results: PASS/exit 0, with detailed logs and source hashes under
`verification/`. The operator command covers 32 backend/history/capture checks,
21 native A/integration checks, 53 B/controller/transport checks and 9 browser
checks. The station command repeats station coverage and includes 3 serial-worker
checks. The duplicate command selects 8 focused cases; these counts overlap and
must not be added to claim distinct coverage.

Individual suites:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s gateway/operator/tests -p "test_*.py"
.\.venv\Scripts\python.exe -B -m unittest discover -s stations/production/tests -p test_integrated.py
.\.venv\Scripts\python.exe -B -m unittest discover -s stations/inspection/tests -p "test_*.py"
node --test operator_ui/test_client.mjs
```

The retained broader production suite also includes contributor-era Python
protocol/helper tests and a native legacy `history.c` test:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s stations/production/tests -p "test_*.py"
```

Its history test requires **host GCC on PATH**, independently of MSVC.
Before cleanup this PC ran 72 production checks with one failure solely because
host GCC was absent. Do not interpret that pre-existing environment limitation
as a new gateway/firmware regression. The native integrated tests use MSVC and
do not substitute the ESP cross-compiler for a host compiler.

The standalone design mock has a separate optional suite, not hardware evidence:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s operator_ui -p test_gateway.py
```

## Cleanup verification records

Before/after software logs, compiler-build records and source/evidence integrity
checks are under `verification/submission-cleanup/`.
A fresh environment is separate from the existing gateway environment.
Firmware builds use ESP-IDF v6.1.1 and nonsecret build-only B Wi-Fi placeholders.
No build result implies that a board was flashed.

## Reviewed physical cases

Final evidence is under `Test_Cases/Evidences/Final_Verification/`.
Case labels are independent of persistent GUI batch numbers.

| Case | Accepted run and evidence | Reviewed outcome |
|---|---|---|
| T01 Normal | Batch 10; four parts, P2s/I1s, N2/K0, queue2/block | 4/4, 2PASS/2FAIL; normal execution. Capture started mid-WebSocket connection, so it does not prove every brief GUI transition. |
| T02 Queue Wait | Batch 11; six parts, P1s/I4s, queue1/block | 6/6, 3PASS/3FAIL; waiting capacity respected; same batch continues automatically. |
| T03 Pause/Resume | Batch 12; six parts, P3s/I5s, queue2/block | 6/6, 3PASS/3FAIL; accepted jobs finish, dispatch holds, explicit Resume preserves batch. |
| T04 Graceful Stop | Batch 14 in `T04_Graceful_Stop/Retest` | Idle/Incomplete; 2 produced, 1 inspected, 1PASS; both closures confirmed, no Fault. |
| T05 Paused settings | Batch 16 | Same batch; old PASS retained; new jobs P1s/I2s/N1; final 6/6, 1PASS/5FAIL. |
| T06 Duplicates | Live replay of Batch 16 Start plus 8 native software checks | Two identical HTTP replays return cached202; changed contents/same ID returns409; batch/results unchanged. |

T04's earlier Batch 13 Stop failure/restart recovery is not a passing ordinary
Stop run. T05's earlier Batch 15 did not apply edited values and is not a passing
settings-change run. The remaining T05 `Paused_Before_Change.png` names Batch15;
exclude it from Batch16 report illustrations. Use `New_Settings_Applied.png`,
which names Batch16 and shows both confirmations and the retained PASS.

T06 tests the physical gateway's cached **HTTP command** handling. Its A/B job
duplicate checks are explicitly native **software** evidence. It does not
inject duplicate jobs onto physical ESP links.

The original evidence review notes remain alongside the files, including
historical checkpoints. The table above identifies accepted final runs.

## Pending physical checks

The user postponed further physical cases until report work is complete.
These are planned, not passed, and are not automatically authorized to run:

1. Raise Fault on full queue, followed by explicit result-preserving closure.
2. Operator loss and reconnect: accepted jobs finish; new dispatch pauses;
   reconnect alone must not Resume.
3. B network interruption while keeping B powered; distinguish same-boot
   reconnect from reboot and check bounded result recovery.
4. A USB interruption: unplugging its only power reboots it; never call that
   a same-boot connection-only test.
5. Short invalid-input and nonzero/negative K checks; integrate valid rule
   changes into remaining batches where practical.

Additional B/gateway restarts, competing screens and long maximum-duration
runs are optional follow-up coverage. Formal multi-protocol benchmarks and
their controlled fault matrix belong to Milestone 2. Bounded retry/duplicate
requirements still require the existing controlled software evidence in M1.

## Per-case hardware recording

1. Use the real integrated gateway with A's USB port and B's single TCP
   connection exclusively owned by that process.
2. Confirm the expected initial state; record settings and actual batch number.
3. Start Wireshark on gateway Wi-Fi with
   `tcp port 5001 or tcp port 8080` **before** Ctrl+F5/configuration/Start.
   Refresh while idle so the HTTP/WebSocket handshake is present.
4. Follow the one assigned action sequence. Photograph/screenshot transient
   defining states such as a full queue, Pause confirmation or Fault.
5. Save final GUI, selected batch History and the original `batch-N.json`.
   For a no-new-batch duplicate test, retain request/response records and
   before/after status rather than fabricate a new batch report.
6. Stop/save the raw PCAP and transfer it into that case folder on the operator PC.
7. On unexpected Fault, preserve the state/capture; do not reset devices or
   press recovery controls until the case has been reviewed.

Packet screenshots can be selected later from saved PCAPs. Actual missing
packets cannot be recreated. TCP ACK is not an application acceptance or completion.

## Serial and database collection

`serial.local.jsonl` and `gateway.sqlite3` live on the gateway and span cases.
A current stopped-session copy is still pending. Stop cleanly while Idle before
copying the database; retain all required files if using a SQLite online backup.
Do not repeatedly copy/delete the active database or reset durable part numbers.

Validate A's raw SLIP/ATR/CRC/sequence frames and correlate original IDs with
the selected batch report. RX records can contain partial or several frames.
Logger status with zero dropped records is useful but not a substitute for
frame validation. Serial capture proves A's USB link; Wi-Fi PCAP proves B's TCP
and operator IP links. Neither replaces the other.
