> Main now builds the integrated A contract described in
> [Member 1 integration](../../docs/member1-integration.md). The contributed
> CRC/SLIP transport is preserved; shared boot/run IDs, QUERY and RETIRE replace
> the older op_no/suffix application contract. pc_test application clients and
> results below describe the contributor version at 58622a0. Use the integrated
> gateway/test runner for the current firmware; old hardware PASS is historical.

# MCT431 Member 1 - ESP32 A production station

Repository setup and verification: [portable checkout instructions](docs/repository_setup.md).
Original hardware acceptance logs retain their recorded local paths.

Gateway handoff: [agreed policy and implementation status](docs/gateway_handoff.md).
The approved [status/late-evidence/continuation APIs](docs/continuation.md) are
now implemented client-side. Original UNRESOLVED outcomes and spent budgets
remain intact; validated late part evidence is recorded separately once.
Eligibility alone never starts work. Explicit different-part submission checks
fresh status again and cannot recreate unresolved parts under new IDs.
Firmware is unchanged; no flash. Current evidence: 48 software tests and five
targeted hardware groups PASS. Physical idle/production unplug/replug checks
are now recorded, including operator-timing and fixture limits; COM3 is closed.
See the standalone [acceptance summary and final handoff](docs/acceptance.md)
for exact commands, gateway example, evidence and pending integration work.

The ESP32 firmware remains at verified Step 5B. Step 5C adds bounded retries
in the Python gateway client only. Production JSON still uses the verified
SLIP/ATR/CRC protocol using test_id 0. It configures timing, produces one
identified part at a time and reports delivery, acceptance and completion
separately. Nonzero test IDs retain the XOR regression path. Formal
benchmarking belongs to Milestone 2. RAM history now protects accepted
operations from duplicate execution during the same boot. Framed one-second
heartbeats and random boot IDs now provide availability/restart protection.

Step 5C passed: **34 software tests**, **9 new retry hardware groups**, a
targeted historical-configuration gateway hardware check, and
all existing hardware regressions (29 protocol cases, 6 production groups,
8 history groups, 6 session groups). Firmware/main hashes are unchanged; no
build/flash was performed. COM3 is closed. Physical unplug/replug is NOT RUN.
The [retry contract](docs/retries.md) documents original deadlines, one shared
two-retry budget, stable identity, unresolved outcomes and JSON/CSV evidence.

Step 5B passed: **19 software tests**, **29 protocol cases**, **6 production
groups**, **8 history groups**, and **6 heartbeat/session groups**. Read-only
watcher and final COM3 release checks passed. Physical cable removal was
NOT RUN; heartbeat loss was tested using controlled RX suppression.
Read the [session contract](docs/session.md): GET_STATUS discovers boot_id,
production requests must carry it, and recovery requires configuration plus
an explicit start. No automatic retries or continuation were added.

Step 5A final results: **13 software tests**, **29 protocol hardware cases**,
**6 production regression groups**, and **8 history hardware groups** passed.
COM3 is closed. Read the [gateway history contract](docs/history.md): required
op_no and the canonical `:<op_no>` suffix on cmd_id/job_id are interface
requirements. Eight completed entries plus the active record and bookkeeping
use **1132 bytes** on ESP32; the deadline adds 8 bytes. History does not survive
reset. Evidence and initial test-harness failures: [progress](docs/progress.md).

Step 4 passed: nine software tests, all 29 protocol hardware cases and all six
production hardware check groups. Measured completion delays were 1047 ms
for a 1000 ms setting and 2531 ms for 2500 ms. COM3 is closed.
See [run instructions](docs/run.md) and [production byte/event evidence](results/step4_production.json).

Step 3 result: **PASS**. Nine software tests (including the 29-case parser
matrix) and all 29 actual hardware exchanges passed. FAIL: 0; NOT RUN: 0.
COM3 was released and closed. [Protocol specification](docs/protocol.md),
[hardware byte evidence](results/step3_hardware.json) and
[progress record](docs/progress.md) describe the exact checks.

Step 1 passed: READY and nine heartbeats were captured. Historical evidence
remains in `results/setup_serial.log`. The old receive-only `setup_check.py`
belongs to that firmware and is not the test for the current application.

Step 2 passed on COM3: exact responses for text (20 bytes), special binary
(7 bytes) and all byte values (256 bytes). Build and application-only flash
passed, and COM3 was released and closed. Full byte evidence is saved in
`results/step2_serial.json`.

## Layout

- `firmware/`: reusable C SLIP/ATR/CRC, production station and XOR regression path.
- `pc_test/`: reusable Python protocol, current framed tests and historical readers.
- `tests/`: host stream tests and hardware acceptance checklist.
- `results/`: actual build, board, flash and serial evidence.
- `docs/`: progress record and local tool activation helper.

## Existing tools and board

ESP-IDF v6.1, Python 3.11.9, pyserial 3.5 and esptool 5.6.0 are already installed.
The physical board was probed on COM3: ESP32-D0WD-V3 revision v3.1, 4 MB flash,
MAC `c0:cd:d6:ce:50:38`. The exact development-board/module model is unverified.
COM1 and COM2 are virtual HHD bridged ports. Recheck ports when reconnecting.

From a clone of this repository, first enter `member1/production-a/`. All
commands below run from that subsystem root in a VS Code PowerShell terminal.
Activate your existing ESP-IDF v6.1 environment, or use the configurable helper:

```powershell
. .\docs\activate_idf.ps1
idf.py --version
python --version
python -m serial.tools.list_ports -v
idf.py -C firmware build
```

The helper uses an existing ESP-IDF installation supplied through IDF_PATH or
`-IdfPath`; optional `-IdfToolsPath` selects your existing tools directory. It
changes only this terminal. No personal installation paths are embedded. See
[repository setup](docs/repository_setup.md) before running these commands.

## Flash-size warning and storage

The recorded warning says physical flash is 4096 KB but the image header is
configured for 2048 KB. The physical capacity came from esptool's chip flash
probe, not a guess. IDF's existing configuration limits this image to 2 MB.
The existing factory partition is `0x10000` through `0x10ffff` (1 MB), inside
that range. The warning does not block this serial test. Flash-size settings,
partition layout, bootloader and data partitions are not changed.

The Step 5B application is 177120 bytes (0x2b3e0), leaving 83% of the existing
1 MB application partition free. Only the application was flashed.

## Run Step 5C (no flash)

Close any serial monitor before running Python. Step 5B firmware is already
flashed and unchanged; do not rebuild/reflash for these client-only checks.

```powershell
python -m unittest discover -s tests -v
python pc_test/retry_test.py --port COM3 --log results/step5c_retries.json --csv results/step5c_retries.csv
python pc_test/framed_test.py --port COM3 --log results/step5c_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5c_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5c_history_regression.json
python pc_test/session_test.py --port COM3 --log results/step5c_sessions_regression.json
```

Run these from the project root after `. .\docs\activate_idf.ps1`.
COM port is configurable. Firmware uses 115200 baud, 8 data bits, no parity,
one stop bit and no flow control; Python explicitly matches those settings.
Changing `--baud` alone does not change firmware's baud rate.

PC sends a complete ATR inside SLIP delimiters. ESP validates length and CRC.
For nonzero test IDs it XORs only the payload with 0xA5. It preserves test_id and seq and
recalculates CRC in the response. Test ID 0 now selects production JSON.
Corrupt records cause no response and increment a local rejection counter.
See [docs/protocol.md](docs/protocol.md) for exact fields, recovery rules,
limits and the shared complete byte example. The raw Step 2 test is historical
and must not be run against this framed firmware.

Heartbeats are framed protocol messages; raw status/printf output and normal
IDF runtime logging remain disabled. Existing ROM/bootloader/early IDF text can still
appear after reset. Explicit-reset hardware fixtures record/drain startup output before their
tests. Normal discovery/reconnect does not deliberately reset the board. Receivers route validated heartbeat/status observations
separately from request responses. Unexpected request responses still fail
tests. Reset noise cannot establish a session; a changed boot faults the run.

The hardware suite has 29 cases: text, special bytes, all byte values, empty
and maximum payloads, one-byte fragmentation, coalesced frames, empty frames,
and ten invalid-input categories each followed by immediate valid recovery.
Invalid cases require silence for 350 ms; recovery cases send invalid input
and a valid frame in one write. Reads of at most 17 bytes accumulate under a
finite deadline; extra bytes fail the case. JSON saves complete TX/expected
RX/actual RX bytes, parsed fields, per-case PASS/FAIL, NOT RUN cases and port
closure. Any failure stops remaining cases. No serial monitor is launched.

Payload limit is 1024 bytes; decoded ATR limit 1034 bytes; worst-case SLIP
wire limit 2070 bytes. Buffer overflow or malformed escaping drops that frame
through the next END delimiter; a subsequent valid frame can be processed.

Host checks, independent of the board:

```powershell
python -m unittest discover -s tests -v
```

For another board, verify its identity and partition layout before reusing
`app-flash`. Recorded hardware results are in `docs/progress.md`.

## Later work and lab reuse

The brief requires A-to-gateway USB serial with SLIP, ATR, CRC and sequence
numbers, preserved in the production implementation. Runtime production timing,
identified requests, separate acceptance/completion and RAM duplicate
suppression now work. Session-safe recovery, bounded client retries and explicit
different-part continuation are implemented; automatic resumption is prohibited.
The XOR application remains only for regression tests. Production starts
unconfigured and accepts CONFIGURE_PRODUCTION before PRODUCE_PART. Its states
are UNCONFIGURED, IDLE and PRODUCING. Accepted work uses a polled monotonic
deadline so communication remains responsive. See docs/protocol.md for the
exact JSON schema, limits, events and rejection rules.

Future work: persistent work reconciliation, batching,
inspection integration and gateway queue management. These remain unimplemented.

Existing lab sources are in `C:\Networks\Lab_Code`, outside this project.
UART driver/event handling in `lab3_a_uart_basics`, PC serial opening/closing,
and SLIP/CRC helpers in `lab3_bc_framed_link` and `host/lab3proto.py` can inform
later work. The lab frame is `type:u8 | seq:u16 | len:u16 | payload | crc:u16`;
the required ATR is `test_id:u16 | seq:u32 | payload_len:u16 | payload | crc:u16`
with big-endian integers. Do not reuse the lab frame unchanged. Keep debug text
separate from future framed traffic. The lab throughput scripts are not needed
for this setup. No old lab files were edited.

See [docs/progress.md](docs/progress.md) for actual results and limitations.
