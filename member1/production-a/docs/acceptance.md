# Member 1 acceptance and final handoff

Member 1 owns ESP32 A and its temporary Python PC/gateway-facing client.
Firmware and client functionality below are implemented. This is functional
acceptance, not Milestone 2 formal benchmarking or full-system acceptance.

## Evidence summary

| Area | Actual evidence |
| --- | --- |
| Current software suite | 48 PASS, results/continuation_software_tests.log |
| Protocol hardware | 29 PASS, results/step5c_protocol_regression.json |
| Production hardware | Six groups PASS, results/step5c_production_regression.json |
| RAM history hardware | Eight groups PASS, results/step5c_history_regression.json |
| Heartbeat/restart hardware | Six groups PASS, results/step5c_sessions_regression.json |
| Bounded retry hardware | Nine groups PASS, results/step5c_retries.json and .csv |
| Fresh status/late evidence/explicit continuation | Five groups PASS, results/continuation_hardware.json |
| Physical idle unplug/replug | PASS, results/physical_acceptance_idle.json; explicit recovery completion is in its retry operations |
| Physical production unplug/replug | PASS with operator-confirmed timing, results/physical_acceptance_producing.json and .csv |

The consolidated physical result is results/physical_acceptance_summary.json;
it distinguishes passed checks from the retained fixture failures and coverage
limits rather than treating an incomplete runner as an overall clean PASS.

The previous valid evidence is reused; unchanged suites are not rerun for
handoff cleanup. Physical test results will be recorded separately. The first
physical fixture discovery attempt failed before human actions or production:
repeated 17-byte invalid fragments, no correlated status. It is retained as
results/physical_acceptance_attempt1.json. A bounded read-only diagnostic then
received valid status/heartbeats (results/physical_discovery_diagnostic.json),
and unchanged-fixture discovery succeeded. Root cause is undetermined; no
firmware/client behavior was changed to bypass it.

The idle attempt then hit a fixture reporting TypeError (duplicate `result`
keyword) AFTER its explicit recovery part completed. The raw retry record
contains COMPLETED; the overall idle attempt is honestly retained as
passed=false, not rewritten. Corrected only the fixture's reporting field and
ran its remaining production phase with --phase producing, without repeating
the physical idle test. There were no application behavior changes.

Both removals caused Windows serial errors; both reconnections discovered NEW
boot IDs and UNCONFIGURED/high_water=0 status. Old-session probes were rejected
without settings/history changes. No automatic resume occurred. The interrupted
operation (boot 438ba8ad8f02e0a22d5359200cf99ade, op 4,
job physical-long-job:4, batch physical-interrupted, part 2) has accepted=true,
retry outcome FAULT and NO confirmed-produced evidence. Preserve it as uncertain,
not failed production or confirmed completion. Re-entry sent zero bytes and
left its original outcome/deadlines/attempt count intact. A DIFFERENT explicit
recovery job completed in boot 39c8595774fe7eff029715ae32437563, op 2.

The operator confirmed unplugging during the accepted 60,000 ms job. That
confirmation was processed about 81.6 seconds after acceptance: actual cable
removal time was not instrumented. The guided fixture pauses serial processing
while waiting for human input, so neither precise physical loss latency nor
continuous receive scheduling is claimed by this run. Actual disconnected-port
errors and changed boot IDs are observed; the exact five-second monotonic
deadline remains covered by existing deterministic/session tests. Exhausted
three-transmission budgets were already verified in step5c_retries.json and
continuation_hardware.json; this physical stopped job used ONE attempt and is
not described as retry-count exhaustion. It stayed stopped across reconnect.

Physical same-session cable recovery with external board power is NOT RUN:
both actual cable reconnections restarted this board. New jobs required
explicit recovery/configuration/start. Both fixtures closed COM3. Source hashes
before/after match (results/physical_firmware_before.csv and _after.csv).

## Setup, build, flash and tests

Current checkout setup: [repository_setup.md](repository_setup.md). Historical
paths in progress notes and raw evidence are preserved as provenance.

Windows / VS Code; verified ESP-IDF v6.1 and Python 3.11.9. ESP32-D0WD-V3,
revision v3.1, COM3, UART0 115200 baud, 8N1, no flow control. Use the installed
tools; no reinstall, upgrade or global environment change is needed.

```powershell
Set-Location .\member1\production-a  # from the repository root
. .\docs\activate_idf.ps1
idf.py --version
python --version
python -m serial.tools.list_ports -v
python -m unittest discover -s tests -v
```

Already-flashed firmware needs no build/flash. If intentionally rebuilding the
unchanged application, use these exact commands AFTER checking the intended
board/port, recorded partition layout and generated flash_app_args:

```powershell
idf.py -C firmware build
Get-Content firmware\build\flash_app_args
idf.py -C firmware -p COM3 -b 115200 app-flash
```

Retain `--flash-mode dio --flash-freq 40m --flash-size 2MB` and application
offset 0x10000. Factory partition is 1048576 bytes; verified Step 5B image is
177120 bytes. Rebuilt images must fit before flashing. The recorded 2 MB image
configuration versus probed 4 MB physical capacity is not a reason to guess or
change capacity/layout. app-flash writes only the application; do not use full
flash/erase, alter sdkconfig/partitions, or write bootloader/data partitions.
See results/step5b_preflash_check.log and docs/progress.md for historical checks.

Hardware commands (one at a time; close monitors first):

```powershell
python pc_test/framed_test.py --port COM3 --log results/step5c_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5c_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5c_history_regression.json
python pc_test/session_test.py --port COM3 --log results/step5c_sessions_regression.json
python pc_test/retry_test.py --port COM3 --log results/step5c_retries.json --csv results/step5c_retries.csv
python pc_test/continuation_test.py --port COM3 --log results/continuation_hardware.json
python pc_test/physical_acceptance.py --port COM3 --log results/physical_acceptance.json
```

Choose new output names to preserve prior evidence when repeating. Existing
automated fixtures explicitly reset RAM for isolation; physical_acceptance
does not pulse reset. It pauses for human unplug/replug/recovery confirmation
and saves JSON/CSV at checkpoints. A failed check stops without changing
application behavior. A skipped human action is NOT RUN, not PASS.

## Minimal gateway usage

Run with pc_test on Python's import path (for example a script in pc_test).
Port opening, closing and sole-reader ownership belong to the caller:

```python
import serial
from gateway_client import ProductionRun, OperationUnresolved

report = {"tx": [], "events": [], "rx_chunks_hex": []}
port = serial.Serial(port=None, baudrate=115200, timeout=0.02,
                     write_timeout=0.5, xonxoff=False, rtscts=False, dsrdtr=False)
port.dtr = port.rts = False
port.port = "COM3"
try:
    port.open()                         # no deliberate reset pulse
    run = ProductionRun(port, report)
    status = run.connect_or_recover()   # explicit discovery/recovery
    n = status["high_water"] + 1        # retain this allocation; uint32, no wrap
    run.configure(n, f"cfg:{n}", 1000)
    run.start()                        # explicit caller decision
    try:
        result = run.produce(n+1, f"job:{n+1}", "example-batch", 1)
    except OperationUnresolved:
        status = run.read_status(1.0)   # read-only; no operation retransmission
        evidence = run.operation_evidence(n+1)
        # Stop this operation. Keep its original identity and exhausted budget.
        # No automatic resume, batch abort or inspection submission here.
    run.observe(0.1)                    # pump regularly whenever otherwise idle
finally:
    port.close()
```

This short example assumes a healthy station and available uint32 numbers.
Real gateway callers must also handle SessionFault, RetryStopped, serial errors,
discovery failures and ContinuationBlocked. Do not allocate new IDs to recover
uncertain work or use this example to reconstruct a lost batch. See
[the complete client API contract](continuation.md) for late-evidence and
explicit different-part continuation examples.

## Protocol and ownership boundary

- [Wire protocol](protocol.md): SLIP/ATR/CRC, UTF-8 JSON, exact identifiers,
  responses and payload bounds; nonzero test IDs retain XOR diagnostics.
- [RAM operation identity](history.md): shared positive uint32 op_no stream,
  canonical `:<op_no>` ID suffix, allowed gaps, eight completed results and
  separate active operation. Accepted high-water mark blocks stale execution.
- [Sessions](session.md): opaque random boot_id, read-only discovery, one-second
  framed heartbeat, five-second PC deadline, explicit restart recovery.
- [Retries](retries.md): one immutable original deadline/budget, at most three
  transmissions, identity preservation and honest unresolved outcomes.
- [Gateway policy](gateway_handoff.md) and [public APIs](continuation.md):
  availability is separate from uncertainty; validated completion alone proves
  a part produced; eligibility alone starts nothing.

## Remaining limitations and integration work

**Both station history and PC history are RAM-only. Serial reading has ONE
owner.** Never run a monitor and a client together or concurrently call status
and an active synchronous operation. Pump heartbeats while idle. PC process
loss cannot be repaired by reading status/high-water marks alone; explicit
reconciliation is needed. No persistence or durable exactly-once guarantee is
claimed across restarts. Unknown/other-session historical evidence is not
automatically credited. Status eligibility is a point-in-time check.

Member 1 completes simulated station timing, validated transport/application
requests, bounded duplicate history, heartbeat/session safety, client retries,
read-only status and deduplicated late-part evidence. A reconnect or late result
never resumes a faulted run. Unconfirmed physical work remains uncertain.

Pending gateway/full-system work: durable operation/part mapping if required,
batch/queue scheduling, inspection routing and counts, operator abort/recovery
UI, coordination with other members, full-system integration and Milestone 2
benchmarking. An isolated unresolved part does not automatically abort a batch;
report separate confirmed production, inspection and unresolved counts, with
the batch incomplete while any part remains unresolved. This repository does
not implement those gateway policies as a batch manager.
