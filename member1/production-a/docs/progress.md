# ESP32 A progress

Date: 2026-11-16 (Africa/Cairo). Step 1 records below describe the original
environment/heartbeat check. Steps 2 through 4 follow below. Formal benchmarking
remains deferred; initial production behavior is implemented in Step 4.

## Briefs read

- `MCT431 Project Fall 26.pdf`: six pages inspected through embedded text
  extraction using Node's existing filesystem/zlib modules. Milestone 1 on
  page 5 requires USB serial with SLIP, ATR, CRC and sequence numbers; page 4
  and page 5 explicitly defer formal benchmarking to Milestone 2. Some special
  glyphs were omitted by extraction; no document layout was evaluated.
- `MCT431_Milestone1_Team_Development_Guide.docx`: paragraphs read from
  `word/document.xml` with .NET ZIP/XML tools. Member 1 owns the station and PC
  test program; later acceptance and completion must be separate and IDs kept.
- Neither source was changed.

## Successful environment checks

| Item | Actual result |
| --- | --- |
| IDF | `ESP-IDF v6.1`, reported by `idf.py --version` |
| IDF source | `C:\Users\Omen Gaming 16\esp\esp-idf-v6.1` |
| Working tools root | `C:\esp-tools` |
| Python | `Python 3.11.9` from existing IDF environment |
| Python executable | `C:\esp-tools\python_env\idf6.1_py3.11_env\Scripts\python.exe` |
| pyserial / esptool | 3.5 / 5.6.0 |
| IDF activation | Python dependencies OK; no outdated tools found |
| Physical serial port | COM3, CP210x USB interface, VID:PID 10C4:EA60, USB serial 0001 |
| Other available ports | COM1 and COM2, HHD Software Bridged Serial Port, virtual |
| Direct chip probe | ESP32-D0WD-V3, revision v3.1, dual core, 40 MHz crystal |
| Device identity | MAC `c0:cd:d6:ce:50:38` |
| Flash probe | 4 MB; manufacturer 68; device 4016 |
| Existing partition table | NVS 0x9000/24K; phy_init 0xf000/4K; factory app 0x10000/1M |

Chip identity came from the ROM/esptool response, never from the CP210x name.
COM3 is the sole physical candidate, so the intended chip and port are
unambiguous for this session. Exact development-board and module branding
cannot be established from this software probe.

## Commands and observations

Run from `C:\Networks\MCT431_Production_A` unless stated otherwise. Probes of
COM3 reset the board through RTS but do not write persistent device storage.
Commands requiring normal Windows access were executed outside the restricted
shell after its access limitations were confirmed.

```powershell
Get-ChildItem -Force
rg --files
Get-Command python,py,idf.py,esptool -ErrorAction SilentlyContinue
python --version
py -0p
[System.IO.Ports.SerialPort]::GetPortNames()
Get-ItemProperty HKLM:\HARDWARE\DEVICEMAP\SERIALCOMM
Get-CimInstance Win32_SerialPort
```

Initial restricted-shell results: `python`/`idf.py` absent from PATH, launcher
reported no registered Python, .NET/registry listed COM3. Installation folders,
`idf-env.json`, `pyvenv.cfg` and old lab CMake cache were inspected read-only to
locate the working tools. The old cache recorded Python 3.11.9/IDF v6.1, then
these versions were verified live.

With normal Windows access (no installs or settings changes):

```powershell
& 'C:\esp-tools\python_env\idf6.1_py3.11_env\Scripts\python.exe' --version
& 'C:\esp-tools\python_env\idf6.1_py3.11_env\Scripts\python.exe' -m serial.tools.list_ports -v
& 'C:\esp-tools\python_env\idf6.1_py3.11_env\Scripts\python.exe' -m esptool --port COM3 chip-id
. .\docs\activate_idf.ps1
idf.py --version
python --version
python -m pip list --format=freeze
python -m esptool --port COM3 flash-id
python -m esptool --port COM3 read-flash 0x8000 0x1000 results/original_partition_table.bin
python "$env:IDF_PATH/components/partition_table/gen_esp32part.py" results/original_partition_table.bin results/original_partition_table.csv
idf.py -C firmware build
```

`chip-id` warned that ESP32 has no separate chip ID and returned its MAC.
`flash-id` and `read-flash` succeeded. The original partition table was saved
and decoded; it provides the basis for preserving data partitions with an
application-only flash. Full output: `results/board_probe.log`,
`results/partition_read.log`, `results/build.log`.

## Existing UART lab and reuse

No source code or AGENTS.md was found in this project at the start. Nearby
sources were found read-only under `C:\Networks\Lab_Code`:

- `firmware/lab3_a_uart_basics/main/main.c`: UART0 115200 8N1, driver setup,
  event queue, bounded byte/line handling and UART error counters. It mixes
  console logs with data deliberately; future production framing must avoid it.
- `host/a_terminal.py`: argparse, receive loop and serial cleanup.
- `host/lab3proto.py` and `firmware/lab3_bc_framed_link/main/`: SLIP, CRC-16/
  CCITT-FALSE (known input `123456789` -> 0x29B1), framing and duplicate/ACK
  concepts. The lab uses 16-bit sequence numbers and a type byte; ATR requires
  a 16-bit test_id, 32-bit sequence and 16-bit payload length. Adapt and verify
  later; the existing protocol is not already compliant.
- Throughput/reliability lab tools exist but were not run for benchmarking.

No lab sources or configurations were modified or copied into this firmware.

## Checks that could not run in the restricted shell

- `python --version`: command not found; `py -0p`: no registered installations.
  These describe that shell only; live Python verification succeeded above.
- IDF virtualenv executables initially reported `No Python at ...Python311`.
  The same executable succeeded with normal access: this was an access issue,
  not evidence that reinstallation was needed.
- CIM serial enumeration: Access denied; PnP command gave no useful output.
  Normal-access pyserial and CIM enumeration later succeeded.
- `version.txt` was absent in the IDF checkout; `idf.py --version` succeeded.
- No pypdf/pdfplumber/PyMuPDF was present in the IDF environment. Initial raw
  PDF stream decompression hit a non-deflate stream; extraction then skipped
  non-text streams and read the six text pages without installing packages.

## Successful build and device validation

| Check | Actual result |
| --- | --- |
| `idf.py -C firmware build` | PASS, exit 0, ESP32 image generated |
| App size | 142272 bytes (0x22bc0), 86% of 1 MB app partition free |
| Layout comparison | Captured first 3072 bytes exactly match generated partition table; original read was 4096 bytes |
| Python reader | AST syntax and `--help` checks passed |
| `idf.py -C firmware -p COM3 -b 115200 app-flash` | PASS, exit 0; written data hash verified |
| Write extent | App at 0x10000; only sectors 0x10000 through 0x32fff erased as required to replace firmware |
| Runtime capture | PASS, `READY idf=v6.1 cores=2 revision=301`, nine ALIVE lines |
| Reader outcome | `PASS: ready_seen=True, heartbeats=9; serial port closed`; exit 0 |
| Port release | PASS: a fresh open of COM3 succeeded; it was closed immediately afterward (`COM3 closed: True`) |

Validation commands after the build:

```powershell
python pc_test/setup_check.py --help
# Python ast.parse checked setup_check.py; pathlib compared partition bytes.
idf.py -C firmware -p COM3 -b 115200 app-flash
python pc_test/setup_check.py COM3 --seconds 8 --log results/setup_serial.log
python -c "import serial; p=serial.Serial(port=None,baudrate=115200,timeout=0.2); p.dtr=False; p.rts=False; p.port='COM3'; p.open(); print('COM3 reopen: PASS (previous reader released port)'); p.close(); print('COM3 closed:',not p.is_open)"
```

`app-flash_args` contains only `0x10000 mct431_a_setup.bin`; bootloader and
partition-table images were not flashed. No data partition was in the erase
range. No `erase-flash` command was used. Flashing necessarily replaced the
previous application on the board; old lab files on the PC remain untouched.

Evidence: `results/build.log`, `results/flash.log`, `results/setup_check.log`
and `results/setup_serial.log`, plus `results/port_release.log`. The capture is a smoke check, not a timing or
throughput benchmark. No interactive IDF monitor was left running.

The boot log warned that physical flash is 4096 KB while the binary header
specifies 2048 KB. The generated sdkconfig uses IDF's default 2 MB flash size.
The existing partition layout fits in that range and the app runs successfully;
this setup does not use the extra capacity. No repartitioning was attempted.

## Step 1 boundaries

No upgrade, reinstall, global setting change, full-chip erase or old-lab edit.
The new app contains only console output and an RTOS delay; it does not open
NVS, configure sensors, drive GPIO, accept jobs or implement SLIP/ATR.
The Python reader is receive-only setup scaffolding, not the gateway yet.

Setup complete. Stopped here as requested; production behavior and formal
benchmarking have not been implemented or claimed as tested.

## Step 2 - temporary two-way serial test

Read README.md, this progress record, all existing project source and the
recorded `results/setup_serial.log` warning before editing. No new AGENTS.md
was present. Existing UART lab files were not changed.

### Flash warning reviewed before flashing

The exact Step 1 warning was:

```text
Detected size(4096k) larger than the size in the binary image header(2048k). Using the size in the binary image header.
```

Cause: physical flash was probed as 4 MB, while the existing sdkconfig/image
header is set to 2 MB. This restricts the addressable flash range for this
image; it is not evidence of insufficient flash. The existing factory app is
at 0x10000, size 0x100000, ending before 0x110000, inside 2 MB. The Step 2
build passed IDF's size check: 0x29540 / 169280 bytes, 84% partition space free.
The warning does not block this UART check. The flash-size setting, bootloader,
partition layout and data partitions are deliberately preserved.

Before the application flash, a fresh read of 0x8000/0x1000 was saved to
`results/step2_partition_before.bin`. Its 4096 bytes matched the Step 1 capture;
the generated table was also compared before writing. The flash command is
`app-flash`, never full `flash` or `erase-flash`.

### What changed

- `firmware/main/main.c`: replaced Step 1 heartbeat with UART0 raw-byte RX/TX
  at 115200 8N1, no flow control. Each input byte produces input XOR 0xA5.
  UART reads may be partial; every received byte is transformed and written.
- No heartbeat or printf in test mode; normal logging is disabled at entry to
  app_main. ROM/bootloader/early application text may precede that mode after
  reset. Python records/drains startup only, then requires silence before TX.
  Startup has a five-second deadline, a one-second minimum settle period and
  half-second quiet requirement. Unexpected traffic during a case fails it.
- `pc_test/two_way_test.py`: configurable port and host baud, explicit 8N1/no
  flow control, finite read/write deadlines, accumulated responses, exact-byte
  comparisons, extra-byte rejection and automatic port closure. The firmware
  baud is fixed at 115200; host settings must match. TX uses at most three
  bytes per write; RX requests at most seven bytes to exercise streaming.
- Cases: ASCII text, binary `00 c0 db ff 41 00 ff`, and bytes 00 through ff.
  Special input `00 c0 db ff` must return `a5 65 7e 5a`.
- Logs are hexadecimal JSON records containing intended TX, actual bytes
  accepted by the OS serial write, expected RX, actual RX, extra RX, read
  sizes, case outcomes and port-closed status. TX means bytes submitted to
  the serial driver; matching transformed RX confirms the round trip.
- `tests/test_two_way.py`: four host checks for partial RX, incomplete-read
  timeout, partial TX with exact binary comparison, and corrupt/extra RX.
- README and test checklist updated. The historical setup reader and Step 1
  logs remain; that reader does not apply to the current firmware.

This is a raw temporary transform with no framing or message format. There is
no SLIP, ATR, CRC, production behavior or formal benchmark implementation.

### Commands and results

From the project root, using the existing Python and IDF tools with normal
Windows access:

```powershell
python -m serial.tools.list_ports -v
python -m esptool --port COM3 chip-id
Get-CimInstance Win32_Process # filtered for serial monitors/test processes
python -m unittest discover -s tests -v
python -m esptool --port COM3 read-flash 0x8000 0x1000 results/step2_partition_before.bin
. .\docs\activate_idf.ps1
idf.py -C firmware build
# Python struct/pathlib verified captured/generated table, app bounds and app-flash_args.
idf.py -C firmware -p COM3 -b 115200 app-flash
python pc_test/two_way_test.py --port COM3 --baud 115200 --timeout 3 --log results/step2_serial.json
```

Successful checks so far: same ESP32-D0WD-V3 rev v3.1 and MAC
`c0:cd:d6:ce:50:38` on COM3; COM1/COM2 remain virtual ports. No matching serial
monitor was running, and the esptool connection succeeded and closed. Four
host tests passed, exit 0 (`results/step2_host_tests.log`). PowerShell wrapped
unittest's stderr output in a NativeCommandError record even though unittest
reported OK and returned 0. Build passed, exit 0 (`results/step2_build.log`).

### Successful hardware results

| Check | Actual result |
| --- | --- |
| Pre-flash layout/bounds | PASS; live/original/generated tables match; app 169280 bytes fits 1048576-byte factory partition |
| Application-only flash | PASS, exit 0, written data hash verified |
| Actual flash erase range | 0x10000 through 0x39fff, entirely inside factory app |
| Ordinary text | PASS; 20 transmitted bytes, 20 exact response bytes; reads 7 + 7 + 6 |
| Special binary | PASS; 7 transmitted bytes, 7 exact response bytes |
| All byte values | PASS; 256 transmitted bytes, 256 exact response bytes; 37 reads (36 x 7 + 4) |
| Unexpected response bytes | None in any case |
| Port cleanup | PASS; JSON reports port_closed=true; separate COM3 reopen succeeded, then closed immediately |

Special case actual exchange:

```text
TX:       00 c0 db ff 41 00 ff
Expected: a5 65 7e 5a e4 a5 5a
RX:       a5 65 7e 5a e4 a5 5a
PASS
```

The startup drain recorded 404 bytes before sending any test data. There was
no runtime heartbeat/debug text in responses. The read loop exercised real
multi-read assembly in the text and full-byte-range cases. Timeouts are
functional bounds, not benchmark measurements.

The firmware binary is 169280 bytes; esptool reported 172032 bytes written
including flash padding. Its reported erase range excludes the bootloader,
partition table, NVS and PHY data. No full-chip erase, flash capacity change,
repartitioning, global setting change or lab modification was performed.

Evidence:

- `results/step2_preflash_check.log`: partition and size assertions.
- `results/step2_build.log` and `results/step2_flash.log`: build/write results.
- `results/step2_serial.json`: complete TX, expected RX and actual RX bytes,
  per-case PASS/FAIL, startup bytes, read sizes and port closure.
- `results/step2_hardware_test.log`: three PASS lines and final PASS, exit 0.
- `results/step2_verification.log`: saved-result inspection and COM3 release.
- `results/step2_host_tests.log`: four passing host checks.

The final port release check used the same explicit 115200/control-line
settings as Step 1, opened COM3, called close(), and printed
`COM3 reopen: PASS` and `COM3 closed: True`. No monitor was launched or left
running. All requested Step 2 checks were accessible; none remain blocked.

Repeat from a PowerShell terminal in the project root, with monitors closed:

```powershell
. .\docs\activate_idf.ps1
python pc_test/two_way_test.py --port COM3 --baud 115200 --timeout 3 --log results/step2_serial.json
```

Step 2 complete. Stopped after the two-way communication test.

## Step 3 - SLIP, ATR and CRC

Date: 2026-11-16 (Africa/Cairo). Read README.md, this record, current C/Python
sources and test code before implementing. Explained SLIP framing, ATR fields
and CRC checking before editing. No production behavior or heartbeats added.

### Implementation

- `firmware/main/protocol.h` and `protocol.c`: reusable bounded incremental
  SLIP decoder/encoder, CRC-16/CCITT-FALSE and full ATR validation.
- `pc_test/protocol.py`: matching reusable functions and streaming decoder.
- Main app validates entire ATR and nonzero test_id before acting; XOR only
  payload with a5, preserve test_id/seq/length, regenerate CRC and SLIP reply.
- Invalid input produces no response. A local debugger-visible volatile
  `rejection_count` counts rejected frames/records without printing on UART.
  Counter values were not queried; hardware evidence is silence and recovery.
- Fixed limits: payload 1024; decoded 1034; worst-case encoded 2070 bytes.
  Malformed escapes and overflow enter discard mode through END. Empty frames
  are ignored. Partial undelimited records stay bounded until the next END.
- `pc_test/protocol_cases.py` defines 29 functional exchanges used by both the
  software simulation and `pc_test/framed_test.py` hardware runner.
- `tests/protocol_vector.json` fixes the complete shared byte example; C
  startup self-test checks the same example and CRC reference before enabling
  UART communication. Reference CRC is 29b1 for ASCII 123456789.
- `docs/protocol.md` specifies fields, byte order, CRC, framing, recovery,
  startup handling, counter behavior, size limits and evidence limitations.

CRC settings: polynomial 1021, init ffff, no reflection, xorout 0000. All
multibyte fields, including CRC, are big-endian. The independent standard
library `binascii.crc_hqx` confirmed the reference and complete example:

```text
ATR:  12 34 01 02 03 04 00 04 00 c0 db ff c3 0e
SLIP: c0 12 34 01 02 03 04 00 04 00 db dc db dd ff c3 0e c0
```

### Storage and access checks before flashing

COM3 was directly reprobed as ESP32-D0WD-V3 rev v3.1, MAC
c0:cd:d6:ce:50:38 (`results/step3_board_probe.log`). No matching serial
monitor was found running. esptool opened and released the port normally.
Its standard warning about ESP32 lacking a separate chip ID merely explains
why it returned the MAC; PowerShell wrapped that stderr warning as a
NativeCommandError record, but the probe succeeded (exit 0).

A fresh partition table read at 0x8000/0x1000 exactly matched the original
4096-byte capture. Its generated-table prefix also matched. App size is
170336 bytes (0x29960), fits the existing 1048576-byte factory partition at
0x10000; IDF reported 84% space free. Assertions checked both the live layout
and application-only flash arguments before writing.

The existing physical 4 MB / configured 2 MB warning remains understood:
all existing partitions fit inside 2 MB. No capacity was guessed, and the
flash-size configuration and partition layout were not changed.

### Actual outcomes

| Scope | Check | Result |
| --- | --- | --- |
| Software-only Python | CRC reference, independent CRC cross-check, shared byte example | PASS |
| Software-only Python | ATR field/size limits, worst-case SLIP size | PASS |
| Software-only Python | 29-case parser/recovery matrix, fed byte by byte | PASS |
| Software-only Python | SLIP rejection count and buffer recovery | PASS |
| Software-only Python | Four historical Step 2 stream-handling tests | PASS |
| Build | New C firmware, IDF app bounds and pre-flash assertions | PASS, exit 0 |
| Flash | Application only, final data hash verified | PASS, exit 0 |
| Hardware | Shared complete example, correct IDs and new CRC | PASS |
| Hardware | Text, special bytes and all 256 byte values | PASS |
| Hardware | Empty and maximum 1024-byte payloads | PASS |
| Hardware | One-byte writes including split escapes | PASS, 18 writes |
| Hardware | Three frames in one write; empty frames ignored | PASS |
| Hardware | Incorrect CRC and declared length, valid CRC on wrong-length test | PASS: silence then recovery |
| Hardware | Invalid and dangling escapes | PASS: silence then recovery |
| Hardware | Truncated header, truncated CRC, unterminated record | PASS: silence then recovery |
| Hardware | Oversized decoded frame and over-limit declared payload | PASS: silence then recovery |
| Hardware | Reserved test_id 0 | PASS: silence then recovery |
| Cleanup | Python port_closed=true; COM3 reopen then close | PASS |

Software runner: 9 top-level tests passed, including the 29-case matrix in
subtests. Hardware runner: 29 PASS, 0 FAIL, 0 NOT RUN; exit 0. Software and
hardware are separate evidence. The hardware replies also establish that the
silent C CRC/example startup self-test passed, because it gates communication.

Each invalid category was observed for 350 ms with no received bytes. Its
next case sent the invalid data immediately followed by a valid request in
the same write; exactly the valid response was received. This is a bounded
silence check, not a claim about arbitrary delayed replies. Valid cases use
three-second deadlines and a 200 ms extra-byte check, with reads up to 17
bytes. Maximum payload request was 2060 encoded bytes and response 1036;
response assembly took 61 reads. Three requests sent together produced three
correct replies, including seq ffffffff and test_id ffff.

The startup drain recorded zero bytes in this run (the reader started after
boot output). The same finite settle/quiet handling remains enabled; no
runtime noise was discarded. No serial monitor was launched. COM3 reopened
successfully after tests and was closed immediately afterward.

IDF/esptool used differential application flashing. Reported erase/write
regions were 0x10000-0x10fff and 0x13000-0x39fff, all inside the factory app.
The unchanged sectors were skipped. The bootloader, partition table, NVS and
PHY data were outside the write ranges. No full flash, full-chip erase,
global configuration change, tool installation or old UART lab edit occurred.

### Evidence and repeat commands

- `results/step3_software_tests.log`: software test results.
- `results/step3_board_probe.log`, `step3_partition_read.log` and
  `step3_partition_before.bin`: identity and live table capture.
- `results/step3_preflash_check.log`, `step3_build.log`, `step3_flash.log`:
  bounds, layout, configuration, build and write verification.
- `results/step3_hardware.json`: exact intended/actual TX, expected/actual RX,
  parsed responses, CRC status, partial read/write sizes, per-case results,
  NOT RUN list and port closure. TX counts OS-accepted serial write bytes;
  exact matching replies establish the round trip.
- `results/step3_hardware_test.log` and `step3_verification.log`: hardware
  console outcomes, summary and port-release verification.

From the project root, close serial monitors first:

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python -m esptool --port COM3 chip-id
idf.py -C firmware build
# Check app bounds and app-flash_args; for this same verified board:
idf.py -C firmware -p COM3 -b 115200 app-flash
python pc_test/framed_test.py --port COM3 --baud 115200 --timeout 3 --log results/step3_hardware.json
```

If firmware is already flashed, only activation and the final Python command
are needed. Port is configurable; baud must match firmware's 115200 8N1.
Step 1 and Step 2 hardware readers are retained only for historical code.
No requested Step 3 test remains NOT RUN. Production and formal benchmarking
were intentionally not run. Stopped after Step 3.

## Step 4 - production application messages

Date: 2026-11-16 (Africa/Cairo). Read README.md, this record, protocol.md and
current firmware/Python code first. Explained request examples, validation
limits and UNCONFIGURED/IDLE/PRODUCING states before implementation.

### Git checkpoint

No `.git` metadata exists in this project, C:\Networks or C:\. The initial
plain shell also had no git executable on PATH. This is not an existing Git
project, so the conditional checkpoint was not applicable. No repository was
initialized, no commit created, no global Git settings changed and nothing
was pushed. Original SLIP/ATR/CRC sources were preserved.

### Changes

- `firmware/main/production.c` / `.h`: bounded flat JSON schema parser and
  production state. Existing IDF does not include a JSON component; used a
  deliberately restricted, documented schema without installing dependencies.
  No heap allocation. IDs 1-48 ASCII characters in `[A-Za-z0-9_.:-]`; timing
  1-60000 ms; part numbers 1-2147483647. JSON booleans, null, quoted numbers,
  fractions and exponent notation are rejected as integer settings.
- Fully validate before changing configuration or starting a part. No NVS
  changes. Reset clears configuration and active work.
- Valid application requests with usable IDs get framed RECEIVED, then
  ACCEPTED/REJECTED. Completion is PRODUCTION_CONFIGURED or PART_PRODUCED.
  Corrupt transport records never reach JSON parsing. Malformed JSON or
  unusable IDs are discarded silently, without production.
- One job saved at a time. Valid configuration changes and other jobs get
  BUSY while producing. A saved microsecond deadline is polled without a
  production-duration sleep, and the RX loop continues. Completion preserves
  original job/batch/part IDs and ATR seq even after intervening busy requests.
- `main.c` dispatches test_id 0 to production. Nonzero IDs use the unchanged
  XOR payload behavior. No raw runtime debug or heartbeat output.
- `pc_test/production_test.py`: reset board via RTS/EN, drain/record boot
  output, send bounded framed requests, accumulate partial responses, validate
  CRC/UTF-8 JSON/IDs/order and measure delays with time.monotonic(). Logs
  complete TX/RX bytes, decoded events and check outcomes. No retries.
- Updated README/protocol documentation and added docs/run.md. The old
  reserved_test_id protocol case sends non-JSON text and remains silent under
  the new routing; it now tests invalid production payload, not a ban on ID 0.

### Storage and board verification

Direct esptool probe still identified ESP32-D0WD-V3 rev v3.1, MAC
c0:cd:d6:ce:50:38 on COM3. No matching monitor was running. Fresh partition
read at 0x8000/0x1000 exactly matched the original capture and generated table
prefix. Pre-flash assertions checked factory offset 0x10000, size 1048576,
and application-only flash arguments with unchanged 2 MB configuration.

App size 173632 bytes (0x2a640), 83% free, fits the existing factory partition.
The existing 4 MB physical / 2 MB header warning is still not a blocker for
this layout. app-flash used differential writes only within 0x10000-0x10fff
and 0x13000-0x3afff. Data hash verified. Bootloader, partition table, NVS and
PHY data were outside the write ranges. No full flash, erase-flash, capacity
change, repartitioning, tool reinstall, global setting change or lab edit.

### Actual results

| Scope | Result |
| --- | --- |
| Existing software regressions | PASS, 9 tests; production runner syntax also checked |
| Build and pre-flash bounds/layout checks | PASS, exit 0 |
| Application-only flash and data hash | PASS, exit 0 |
| Protocol hardware regression | PASS, 29 cases, 0 FAIL, 0 NOT RUN |
| Production before configuration | PASS, RECEIVED then REJECTED/NOT_CONFIGURED |
| Configure 1000 ms | PASS, RECEIVED/ACCEPTED/PRODUCTION_CONFIGURED with applied time |
| Invalid requests | PASS, 9 invalid time values, 7 invalid part values, missing/extra/unknown commands, malformed JSON/IDs/UTF-8 and corrupt CRC |
| One 1000 ms part and busy handling | PASS, matching IDs/order, different job/config rejected BUSY, XOR responsive while producing |
| Configure 2500 ms and produce another part | PASS, matching IDs and event order |
| Cleanup | PASS, port_closed=true, independent COM3 reopen then close succeeded |

Production runner: 6 check groups PASS, 0 FAIL, 0 NOT RUN. It sent 34
production test requests and recorded 56 application events, plus an XOR
exchange while busy. It recorded/drained 2971 startup bytes after intentional
reset; no output was discarded after testing began.

Measured from host receipt of ACCEPTED to host receipt of PART_PRODUCED:

| Applied time | Measured | Allowed interval | Result |
| --- | --- | --- | --- |
| 1000 ms | 1047 ms | 900-1500 ms | PASS |
| 2500 ms | 2531 ms | 2400-3000 ms | PASS |

Tolerance is requested time minus 100 ms through plus 500 ms, accounting for
UART serialization, host scheduling and 20 ms firmware polling. These are
functional timer checks, not formal benchmarks. The first part also proves
rejected/invalid settings did not change the applied 1000 ms time. Extra-event
checks after completion found no unintended production.

### Evidence and repeat commands

- `results/step4_software_tests.log`, `step4_build.log`: software/build output.
- `results/step4_board_probe.log`, `step4_partition_before.bin`,
  `step4_partition_read.log`, `step4_preflash_check.log`: identity/layout/bounds.
- `results/step4_flash.log`: differential app-only writes and verified hash.
- `results/step4_protocol_regression.json` and `.log`: 29 protocol cases.
- `results/step4_production.json` and `step4_production_test.log`: actual wire
  bytes, decoded events, response identity/order checks, measured delays and
  per-group PASS/FAIL/NOT RUN.
- `results/step4_verification.log`: result summary, timings and port release.

From project root, close any serial monitor first:

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
idf.py -C firmware build
idf.py -C firmware -p COM3 -b 115200 app-flash
python pc_test/framed_test.py --port COM3 --log results/step4_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step4_production.json
```

Already flashed: only activation and the last two test commands are needed.
The production test deliberately resets volatile state, making the initial
unconfigured check repeatable. All requested Step 4 tests ran successfully.
COM3 is closed; no monitor was launched or left running.

Step 5 remains: full duplicate/retry handling, batching, inspection, gateway
queue management and heartbeats. Idle duplicate IDs can still execute again;
the test does not retry uncertain work. Stopped after Step 4.

## Step 5A - approved RAM history and duplicate protection

Date: 2026-11-16 (Africa/Cairo). User approved required uint32 op_no, shared
configuration/job ordering, allowed gaps, eight completed entries, separate
active record, replay/ATR sequence rules, and the additional canonical
`:<op_no>` suffix convention before implementation. No further convention
was silently chosen. Read current code and docs before editing.

### Mechanism and gateway requirements

- `history.h` / `history.c` hold typed request/result records, one active
  operation and a FIFO completed cache. Parsed application fields are compared,
  not JSON formatting, padding bytes or ATR seq.
- `production.c` validates schema, positive uint32 op_no and canonical ID
  suffix before looking up active, cached, stale or new operations in that
  order. Invalid requests and BUSY rejections never advance accepted progress.
- Identical active request gets RECEIVED/OPERATION_RUNNING without restarting
  its deadline. Identical cached operation gets RECEIVED/historical terminal
  event with replayed=true. Conflicts get OPERATION_CONFLICT. Missing cached
  results at/below accepted high-water get STALE_RESULT_UNAVAILABLE, without
  claiming that a skipped number definitely executed.
- New acceptance stores active identity/request/seq/applied duration and
  advances high-water BEFORE changing settings or starting the timer.
  Completed entries replace the oldest completion; replay does not refresh
  FIFO position. The active record never occupies/evicts a completed slot.
- Replay/status replies use the arriving ATR seq. Original delayed completion
  keeps the originally accepted seq. All validated operation replies include
  op_no and full application IDs. Config replay never reapplies an old time.
- IDs must retain their ORIGINAL complete value on retry, together with op_no.
  A used ID at a higher number mismatches its suffix even after eviction and
  cannot execute. Full ID <=48 characters, nonempty prefix, canonical decimal
  suffix without leading zeros. batch_id retains its old rules.
- Gateway specification: docs/history.md. Updated protocol/run/README docs.
  Legacy production regression builders now add explicit increasing op_no and
  suffixes. Explicit history probes disable this builder convenience.

### Actual RAM usage

Installed ESP32 GDB inspected the built ELF offline, without a device
connection. Commands in order were sizeof(operation_t), sizeof(result_t),
sizeof(history_t), sizeof(history.completed), sizeof(history.active), and
sizeof(deadline_us). Output: `116, 124, 1132, 992, 124, 8` bytes.

| Component | ESP32 bytes |
| --- | ---: |
| One parsed operation | 116 |
| One completed-result entry | 124 |
| Eight completed entries | 992 |
| Separate active result | 124 |
| High-water/FIFO/count/active flag and padding | 16 |
| Complete history structure | 1132 |
| Separate deadline | 8 |
| History plus deadline | 1140 |

These are actual history-related static data sizes, excluding existing
protocol/UART buffers, other station variables and temporary stack buffers;
not a claim about total firmware RAM. Actual portable C host tests independently
reported the same structure sizes. See step5a_target_ram.log and
step5a_c_history.log. No heap allocation or persistent storage was added.

### Build, flash and regression results

Direct probe confirmed ESP32-D0WD-V3 rev v3.1, MAC c0:cd:d6:ce:50:38 on COM3.
No serial monitor was found. Fresh partition capture exactly matched the
original and generated prefix. Before flashing, assertions verified factory
offset 0x10000, size 1048576 and unchanged app-only / 2 MB flash arguments.
App is 174832 bytes (0x2aaf0), 83% app-partition space free. The previously
explained physical 4 MB / configured 2 MB warning remains nonblocking.

Build, bounds assertions and app-flash passed, exit 0. Differential write
ranges: 0x10000-0x10fff and 0x13000-0x3afff; data hash verified. Bootloader,
partition table, NVS and PHY data were outside these ranges. No capacity or
partition change, full erase, tool reinstall, global change or old-lab edit.

| Final check | Result |
| --- | --- |
| Software suite | PASS, 13 tests, 0 FAIL/0 NOT RUN |
| Actual portable C history core on existing PC GCC | PASS (part of software suite) |
| Protocol hardware regression | PASS, 29 cases, 0 FAIL/0 NOT RUN |
| Production hardware regression | PASS, 6 groups, 0 FAIL/0 NOT RUN |
| New history hardware suite | PASS, 8 groups, 0 FAIL/0 NOT RUN |
| Independent COM3 reopen and close | PASS |

The software suite includes the original nine tests, actual C history
execution and three client-probe tests. The existing host GCC was found at
`C:\Program Files (x86)\SKTOOL7.1\Marco\X86\bin\gcc.exe`. It emitted
aggregate zero-initializer warnings in the harness, but compiled and executed
successfully. ESP-IDF build had no C compiler warning/error matches.

The final history run sent 66 production probes and recorded 145 events,
with two intentional resets. Hardware groups all passed:

1. Missing/mismatched suffixes, leading zeros, invalid alphabet, op_no missing,
   zero, negative, boolean, fraction, string, null and overflow; malformed JSON
   01; exact 48-character cmd/job IDs accepted and 49-character IDs rejected.
2. Active duplicate with different JSON key order/whitespace and new ATR seq
   reports running; altered part/ID conflicts; rejected op 100 while busy
   does not block later op 4. Original delayed seq remains intact.
3. Completed job replay does not produce another part (650 ms extra check);
   changed batch conflicts; old ID with higher number is rejected.
4. Cached 1000 ms configuration replay after 2500 ms returns historical 1000
   without reverting settings, including replay while a job is active.
5. Allowed gap 6->10, never-accepted 8 rejected honestly as unavailable;
   rejected invalid 11 can later be accepted as corrected 11.
6. Enough completions replace cache entries: 13 stale, 14 still cached after
   completions through 21. Old job/config stale and their IDs cannot be reused
   with 22; valid new job 22 still executes after replacement.
7. Reset erases RAM high-water/cache. New op 1 AND the exact pre-reset config
   operation 4 can be accepted again, explicitly proving restart limitations.
8. UINT32_MAX accepted and replayed; lower uncached numbers stale and overflow
   rejected. No wraparound.

Measured acceptance-to-completion in history suite:

| Operation | Applied time | Measured | Meaning |
| --- | --- | --- | --- |
| 3 | 500 ms | 515 ms | Duplicate sent after 200 ms; additionally required <650 ms, detecting a restarted deadline |
| 6 | 2500 ms | 2516 ms | Old config replay did not revert the newer setting |
| 22 | 30 ms | 47 ms | New work continued after cache replacement |

Production regression timings: 1000 ms -> 1000 ms, 2500 ms -> 2531 ms, within
the documented functional tolerance. These are not formal benchmarks.

### Initial failed hardware attempts retained

The first two history runs each stopped in identifier_validation (one FAIL,
seven remaining groups NOT RUN); they were test-harness errors. No firmware
change or additional flash was needed between attempts.

- attempt1: `cfg:+1` contains an invalid ID character, so existing schema
  rules silently discarded it. The test wrongly expected a framed rejection.
  Corrected to bounded silence while retaining framed rejection tests for
  usable-but-mismatched suffix IDs.
- attempt2: the legacy production client auto-added a missing op_no and suffix
  in a deliberately missing-field probe. It accidentally sent a valid request.
  Added explicit sending mode that preserves invalid input, and software tests
  proving missing numbers remain missing, explicit duplicate identities stay
  stable and legacy regression builders still add their new-operation fields.

Both attempts closed COM3 and are preserved as step5a_history_attempt1.* and
step5a_history_attempt2.*. The final corrected run passed all eight groups.
No final requested test remains NOT RUN.

### Evidence and repeat commands

- `results/step5a_software_tests.log`: 13 software PASS results.
- `results/step5a_c_history.log`: actual C host execution and compiler path.
- `results/step5a_target_ram.log`: ESP32 ELF type-size measurements.
- `results/step5a_board_probe.log`, `step5a_partition_before.bin`,
  `step5a_partition_read.log`, `step5a_preflash_check.log`: identity/layout.
- `results/step5a_build.log`, `step5a_flash.log`: build and verified app write.
- `results/step5a_protocol_regression.json`, `step5a_production_regression.json`
  and corresponding .log files: retained hardware regressions.
- `results/step5a_history.json`, `step5a_history_test.log`: final exact TX/RX,
  timestamps/events/check outcomes; initial attempts retained separately.
- `results/step5a_verification.log`: final counts, timings and port release.

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
idf.py -C firmware build
idf.py -C firmware -p COM3 -b 115200 app-flash
python pc_test/framed_test.py --port COM3 --log results/step5a_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5a_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5a_history.json
```

Already flashed: activation and three hardware commands suffice. Close serial
monitors first. Production/history runners intentionally reset volatile state.
Final history run ends at maximum op_no; a new test run resets explicitly.
COM3 closed after tests; independent reopen succeeded then closed immediately.

History is RAM-only and does NOT protect across reset/power loss. Previously
accepted work can execute again after restart. No persistent session identity,
heartbeats, automatic retries, batching, inspection or gateway queues added.
Stopped after Step 5A.

## Step 5B - framed heartbeats and restart protection

Date: 2026-11-16 (Africa/Cairo). Read implementation/README/protocol/progress
first. The user's initial prompt was cut off; requested and received the full
remaining test requirements before finalizing the work. Explained discovery,
random boot identity, heartbeat liveness and explicit recovery before coding.

### Implementation and interface changes

- Each boot generates a 128-bit opaque ID, 32 lowercase hex characters, using
  esp_fill_random with physical SAR ADC entropy temporarily enabled through
  bootloader_random_enable/disable. Consulted installed v6.1 esp_random.h,
  bootloader_random.h and docs/en/api-reference/system/random.rst. No uptime,
  reset-to-zero counter, MAC-only identifier or persistent write is used.
- `production.c` sends framed HEARTBEAT once per nominal second in all states:
  boot_id, state, active_op_no (or null), accepted high_water, applied time and
  increasing heartbeat_no. Unsolicited heartbeat ATR test_id=0, seq=0.
- GET_STATUS (type-only JSON, no session or operation number) returns STATUS
  using the request's seq. It reads state without touching config, operations,
  history or the heartbeat counter. All production JSON replies include boot_id.
- Production/configuration requests now require boot_id. Missing/different
  session is rejected before history lookup or settings/timer effects. Existing
  operation number/suffix, replay and ATR correlation behavior remains.
- Full frames are sent serially by the existing main loop. No heartbeat task,
  ISR printing, raw status text or concurrent TX writer was added. Production
  completion is checked before the heartbeat poll; both remain nonblocking.
- New reusable `session.py` and `receiver.py`: partial SLIP/ATR reads, CRC/JSON
  validation, separate observations versus request responses, monotonic liveness
  and sticky run faults. Invalid/replayed/out-of-order/other-session heartbeats
  do not refresh liveness. STATUS never refreshes it. Only an outstanding
  GET_STATUS seq routes STATUS into its request queue; other statuses are
  observation-only. Heartbeats cannot satisfy ACCEPTED/PART_PRODUCED waits.
- >=5.000 s without valid fresh current-session heartbeat marks unavailable
  and latches HEARTBEAT_TIMEOUT. Same-session heartbeat recovery can restore
  link availability but never clears the run fault or sends work. A new boot
  latches RESTART, stops old-session waits and blocks further work submission.
  Invalid/reset noise is discarded through framing recovery, never trusted as
  a session identity. Observation continues after faults.
- `gateway_client.py` ProductionRun requires explicit connect_or_recover,
  completed configuration and explicit start before produce. Faults invalidate
  local configuration/start permission. No request is automatically retried.
  `station_watch.py` observes/read-only discovers and can reopen a lost port
  without configuring, producing, or resuming a run. Idle gateway loops must
  pump/observe regularly; there is no hidden PC background thread.
- Existing tests add discovered boot_id and route heartbeat/status separately.
  Invalid input now means no request-specific reply/action while unrelated
  validated heartbeats remain allowed. The XOR path stays nonzero-test_id and
  can still be tested without binding production sessions.

Current gateway contract and examples: docs/session.md. Existing docs/history.md
now distinguishes RAM loss from the boot fence: an unchanged old-session
request is rejected, while explicitly rebinding uncertain work to a new boot
can execute it again. Do not automatically perform that rebinding.

### Board, build and storage

Direct probe still found ESP32-D0WD-V3 rev v3.1, MAC c0:cd:d6:ce:50:38 on COM3.
No serial monitor was running. Fresh 0x8000/0x1000 partition capture exactly
matched the original and generated table prefix. Pre-flash assertions checked
factory offset 0x10000, size 1048576, application-only args and unchanged 2 MB
configuration. The known physical 4 MB / configured 2 MB warning remains
nonblocking for this layout.

Final app size 177120 bytes (0x2b3e0), 83% factory-partition space free. Build,
pre-flash checks and app-flash passed; hash verified. Differential application
write ranges: 0x10000-0x10fff and 0x13000-0x3bfff. The bootloader, partition
table, NVS and PHY data were outside the writes. A bootloader binary was built
by IDF but NOT flashed. No flash capacity/layout change, full-chip erase,
tool reinstall, global setting change or old-lab edit.

### Final actual results

| Scope | Actual result |
| --- | --- |
| Software regressions and new session/run policy tests | PASS, 19 tests, 0 FAIL/0 NOT RUN |
| Protocol hardware regression | PASS, 29 cases, 0 FAIL/0 NOT RUN |
| Production hardware regression | PASS, 6 groups, 0 FAIL/0 NOT RUN |
| History hardware regression | PASS, 8 groups, 0 FAIL/0 NOT RUN |
| New heartbeat/session hardware suite | PASS, 6 groups, 0 FAIL/0 NOT RUN |
| Read-only watcher smoke check | PASS, discovered session/heartbeat available; no work sent |
| Final independent COM3 reopen/close | PASS |
| Physical USB unplug/replug | NOT RUN; no physical cable removal performed |

New hardware suite verified:

1. Read-only discovery and repeated status leave high_water/config/active work
   unchanged. Heartbeats arrive while UNCONFIGURED and are not request replies.
2. Missing and wrong boot_id on BOTH command types cause SESSION_MISMATCH and
   leave config=0/high_water=0; no part starts.
3. Heartbeats in IDLE; ordinary close/reopen with DTR/RTS false retains the
   exact same boot. This was NOT a reset test.
4. Controlled RX-heartbeat suppression while actual serial data is still read:
   five heartbeat observations suppressed, deadline fault detected at 5.016 s
   after the last valid heartbeat. Same-session observation recovery restores
   available=true with HEARTBEAT_TIMEOUT still latched, and send remains blocked.
   Explicit new discovery/configuration was then chosen by the test.
5. A 15000 ms job reports PRODUCING heartbeats with active op 3/high_water 3.
   Deliberate RTS/EN restart changes boot_id, faults/stops the old run before
   completion, and continued read-only pumping sees later new-boot heartbeats.
6. New-boot discovery shows UNCONFIGURED/config=0/high_water=0. An unchanged
   old-session configuration request with otherwise-acceptable op 1 is rejected
   without advancing history. Explicit recovery verifies start fails before
   config, produce fails before start, then config/start/new job succeed.

The final session run logged 7 UNCONFIGURED, 11 IDLE and 3 PRODUCING heartbeats.
Consecutive same-boot counter intervals observed by the PC were approximately
0.985-1.031 s (host receipt timing, not a benchmark). Actual initial and new
boot IDs are in results/step5b_sessions.json and step5b_verification.log.
The software fake-clock test checks available at 4.999 s and unavailable at
exactly 5.000 s. Status, malformed heartbeat, replay, wrong-seq and other-boot
tests ensure unrelated traffic cannot keep the old run alive.

Same-session timeout is tested by RX heartbeat filtering, NOT a physical
disconnection or disabling the station's heartbeat. Ordinary port reopen and
deliberate restart are separately executed. The read-only watcher is tested
for discovery/availability/port cleanup. Its physical cable removal/reconnect
path is NOT RUN; optional manual steps are in docs/session.md. USB-only power
removal normally also causes restart, so same-boot physical disconnect testing
would need separate power.

### Initial history regression attempt retained

The first Step 5B history run passed identifier_validation then stopped in
active_duplicate_and_conflicts: the 500 ms part completed while the test was
still exchanging the now-longer session-tagged conflict responses. Six later
groups were NOT RUN in that attempt. This was an invalid test timing window,
not evidence of timer restart or firmware failure. Retained as
results/step5b_history_attempt1.json/.log.

Changed the regression fixture to 1200 ms, sends the duplicate after 450 ms,
and independently requires original completion before 1500 ms (a restarted
deadline would exceed that). Final measured completion was 1219 ms; config
replay test was 2515 ms for 2500, and post-eviction new work 47 ms for 30.
No firmware change/reflash was needed for this test correction. Final receiver
routing changes were software-tested; the session hardware suite was rerun
successfully. Final software tests also check malformed observations cannot
stop read-only recovery observation or refresh heartbeat liveness.

### Evidence and repeat commands

- `results/step5b_software_tests.log`: 19 passing tests, including actual C
  history regression, deadline/routing policy and explicit start gates.
- `results/step5b_board_probe.log`, `step5b_partition_before.bin`,
  `step5b_partition_read.log`, `step5b_preflash_check.log`: identity/layout.
- `results/step5b_build.log`, `step5b_flash.log`: build and app-only verification.
- `results/step5b_protocol_regression.json`, `step5b_production_regression.json`,
  `step5b_history_regression.json` and matching logs: prior hardware coverage.
- `results/step5b_sessions.json`, `step5b_sessions_test.log`: exact transmitted
  and received bytes, decoded statuses/responses, timestamps, fault injection,
  reset/session evidence and per-group PASS/FAIL/NOT RUN.
- `results/step5b_watch.log`, `step5b_verification.log`: observation smoke check,
  final measured summary and confirmed port release.

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
idf.py -C firmware build
idf.py -C firmware -p COM3 -b 115200 app-flash
python pc_test/framed_test.py --port COM3 --log results/step5b_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5b_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5b_history_regression.json
python pc_test/session_test.py --port COM3 --log results/step5b_sessions.json
python pc_test/station_watch.py --port COM3 --seconds 30
```

Already flashed: activation/tests only. Close serial monitors first. Test
fixtures explicitly pulse reset; normal watcher/reconnect does not. Final
watcher and independent reopen closed COM3; no serial monitor was left running.
No automatic retries, uncertain-work resubmission, persistent history,
batching, inspection or gateway queue management added. Stopped after Step 5B.

## Step 5C - bounded automatic retries in the Python client

Date: 2026-11-16 (Africa/Cairo). Read current client/receiver, firmware, README,
protocol and progress first. Explained acceptance/completion/saved-result
states and all deadline interactions before editing, including configuration's
initial one-second window. Implemented only within the approved timing and
identity rules. Firmware behavior and message interface did not change.

### Client mechanism

- `pc_test/retry.py`: reusable RetryPolicy, RetryController and shared RAM
  RetryLedger. One synchronous logical operation at a time; no batch queue,
  operation-number allocator or background reset/recovery behavior.
- Default acceptance deadline t0+1 s. Initial production completion deadline
  t0+configured duration+1 s. Two additional transmissions maximum (three
  total), SHARED across acceptance/completion recovery. Saved-result response
  windows <=1 s, clamped to the original absolute deadline. Production absolute
  t0+duration+3 s; configuration overall t0+3 s. All use time.monotonic and
  remain configurable through RetryPolicy. Never reset these times on replies.
- First attempt freezes the full payload with original boot_id/op_no/IDs/
  settings/part details. Retransmissions use identical payload bytes and a new
  ATR seq. Known original/retry seq values correlate one logical operation;
  original delayed completion and replay result are both accepted when matching.
- RECEIVED alone never establishes acceptance. ACCEPTED or OPERATION_RUNNING
  does. A valid matching completion terminates waiting immediately. Running
  replies never extend absolute time. Once attempts are spent, observe only
  until the original overall deadline; no additional transmission is made.
- Matching terminal rejection, operation conflict, invalid request, unavailable
  historical result or session/heartbeat fault stops automatic retries.
  Outcomes are COMPLETED, REJECTED, FAULT or UNRESOLVED. Missing confirmation
  does not prove no production occurred; an I/O error is unresolved rather
  than evidence the request was not delivered.
- Heartbeats/status continue through the existing receiver during every wait,
  outside the deterministic response-omission hook. Stale earlier-operation
  or unrelated old-session replies are quarantined, not credited. A different
  boot on a current-attempt reply faults RESTART; session observations retain
  the existing strict restart/liveness rules.
- Ledger records first deadlines, request contents, allowed seqs, stopped
  outcomes and confirmed completion keys. Same stopped operation submitted
  again cannot acquire another budget or deadline. A known completed result
  returns locally with zero sends and no second logical completion credit.
  ProductionRun retains this RAM ledger across explicit reconnect calls.
- `gateway_client.py` uses the controller for config and production. Unresolved,
  rejected or faulted work disarms the run; heartbeat recovery cannot rearm it.
  Historical configuration confirmation does not imply current settings: read
  STATUS after replay and do not arm if current applied time differs.
- Low-level regression Client remains usable without retries. It gained only
  an optional write deadline and an optional non-strict response-session route
  for the controller to classify stale versus current replies. The receiver
  heartbeat/session policy and firmware messages are unchanged.

Current contract, policy defaults, PC examples and limits: docs/retries.md.
README/protocol/session/history/run documentation was updated consistently.
The ledger is PC RAM-only; no new persistent work ledger exists. Restarting
the Python process is not permission to resubmit uncertain work automatically.

### Firmware, storage and port handling

No build, flash, erase or esptool reset/probe was performed in Step 5C. SHA256
before/after comparison verified every firmware/main source/header/CMake file
unchanged (`step5c_firmware_before.csv`, `step5c_firmware_after.csv`,
`step5c_firmware_verification.log`). Existing config still records 2 MB image
flash size and partition table offset 0x8000. Bootloader, partition table and
data partitions were untouched. The existing Step 5B image remains on COM3.

No tools were upgraded/installed, global settings changed or old UART lab files
edited. All serial opens set DTR/RTS false before opening. Hardware test fixtures
explicitly pulse RTS/EN to isolate cases; the retry controller itself never
resets the board. Physical unplug/replug remains NOT RUN.

### Final actual results

| Scope | Result |
| --- | --- |
| Software suite including deterministic fake-clock retry tests | PASS, 34 tests, 0 FAIL/0 NOT RUN |
| Existing protocol hardware regression | PASS, 29 cases |
| Existing production hardware regression | PASS, 6 groups |
| Existing history hardware regression | PASS, 8 groups |
| Existing heartbeat/restart regression | PASS, 6 groups |
| New deterministic omission/retry hardware suite | PASS, 9 groups, 0 FAIL/0 NOT RUN |
| Targeted local historical-config gateway hardware check | PASS, Start blocked with current 1500 ms versus old 500 ms |
| Firmware/main before/after hashes | PASS, unchanged |
| Independent COM3 reopen/close | PASS |
| Physical USB unplug/replug | NOT RUN, unchanged limitation |

Software tests execute the actual controller with a fake monotonic clock and
scheduled replies, including repeated running responses, exact budgets,
three-second configuration limit, combined acceptance/completion loss sharing
one budget, stop outcomes, cross-controller shared ledger, late/duplicate
completion quarantine and gateway disarming. The previous 19 tests still run.

Hardware omission is deterministic and occurs only after normal response
validation/routing; ignored frames remain recorded with their decoded ATR,
seq, identity and time. Unsolicited heartbeats are not omitted by response-loss
rules. Separate explicit test injections copy an observed running/completion
frame, trigger a deliberate restart, or suppress heartbeat observations.

| New hardware group | Actual controller behavior |
| --- | --- |
| No loss | COMPLETED with 1 production transmission, no retries |
| Ignore acceptance | 2 transmissions; retry got running status; original completion retained first seq; 1.891 s for 1800 ms setting |
| Ignore original completion | 2 transmissions; cached replay confirmed at 1.406 s, replayed=true; late copied completion quarantined; re-entry returned local result with zero sends |
| Exhaust response budget | 3 transmissions; UNRESOLVED at 3.313 s for 300 ms duration; second API call sent nothing; firmware log still showed original result/cache replay withheld from controller |
| Repeated running frames | Captured running response copied during waits; 3 transmissions; UNRESOLVED at 4.813 s with fixed 4.800 s deadline for 1800 ms duration |
| Historical config replay | Old confirmation withheld, explicit newer 1500 ms config applied; original config retried/cached at 1.079 s without reverting it; new part used 1500 ms setting |
| Restart | FAULT/RESTART at 1.063 s; at most 2 old-session transmissions before restart was observed; new session stayed unconfigured/high_water=0 |
| Heartbeat loss | FAULT/HEARTBEAT_TIMEOUT, 1 transmission; no retry after same-session heartbeat recovery |
| Terminal rejection | OPERATION_CONFLICT and INVALID_CONFIGURATION each stopped immediately after 1 transmission |

The absolute times remain fixed; Windows read/scheduling wake-up granularity
made timeout decisions roughly 13 ms after their timestamps. No late completion
was credited and no transmission occurred after the deadline/budget. Heartbeat
loss fault occurred 4.906 s after transmission because the last valid heartbeat
preceded transmission by about 94 ms; its heartbeat deadline was still five
seconds after that heartbeat, not five seconds after the request.

The final retry log has 23 operation records (including local result reads),
292 CSV trace rows and 30 observed heartbeats. Expected UNRESOLVED/FAULT/
REJECTED operation outcomes are PASS scenarios, not failed test groups.
All hardware groups passed without a failed run. The retry suite was rerun
after ledger/logging refinements, and the affected gateway/session regression
was rerun after integration. No firmware change or flash was needed.

### Non-duplication evidence and honest limits

Do not infer non-duplication solely by counting PC completion messages. The
hardware log also checks station high_water/active state, no second ACCEPTED
on retransmission, the preserved ORIGINAL completion seq, original timer
duration without restart, and replayed=true cached result flags. Existing C
history-core software tests and the history hardware regression also pass.
No independent physical-part counter exists in this virtual station; claims
are limited to these station-sourced state/result/timer and unchanged-code
observations. Status evidence requests are read-only, not extra transmissions
of an exhausted operation.

Ignored frames are visible to the test harness for audit, but deliberately
unavailable to the controller. Thus the harness can show that production DID
complete while the controller correctly reports UNRESOLVED due to simulated
response loss. It never reports that missing confirmation proves production
failed. No new op_no is assigned to resolve that uncertainty.

### Evidence and repeat commands

- `results/step5c_software_tests.log`: 34 passing software tests.
- `results/step5c_retries.json`: policy values, immutable request identities,
  first transmission time, deadlines, each attempt/seq, state transitions,
  normal/ignored/quarantined responses, final outcomes and station evidence.
- `results/step5c_retries.csv`: matching identity/attempt/response/deadline/
  elapsed-time/outcome trace rows, with full event details.
- `results/step5c_retry_test.log`: nine hardware group outcomes.
- `results/step5c_gateway_cache.json`, `.csv` and `step5c_gateway_cache_test.log`:
  real-board proof that a local old config result reads current status and
  cannot arm Start with a stale setting. Added a matching software regression.
  The local historical return transmits only read-only STATUS, not the operation.
- `results/step5c_protocol_regression.json`, `step5c_production_regression.json`,
  `step5c_history_regression.json`, `step5c_sessions_regression.json` and their
  .log files: existing hardware coverage.
- `results/step5c_firmware_before.csv`, `step5c_firmware_after.csv`,
  `step5c_firmware_verification.log`: unchanged firmware source hashes.
- `results/step5c_verification.log`: actual outcomes/counts and port release.

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python pc_test/retry_test.py --port COM3 --log results/step5c_retries.json --csv results/step5c_retries.csv
python pc_test/gateway_cache_test.py --port COM3 --log results/step5c_gateway_cache.json
python pc_test/framed_test.py --port COM3 --log results/step5c_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5c_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5c_history_regression.json
python pc_test/session_test.py --port COM3 --log results/step5c_sessions_regression.json
```

Close serial monitors first. No firmware flash is required. COM3 was closed by
the suites; independent reopen succeeded and was closed immediately. No monitor
was left running. No firmware/interface changes, batching, inspection or queue
management added. Stopped after Step 5C.

## Gateway policy documentation and static API review

Date: 2026-11-16 (Africa/Cairo). Documentation-only follow-up requested after
Step 5C. Read retry/gateway/receiver/session/client implementation and current
README, protocol, session, retry and progress docs. No implementation edit.

Created docs/gateway_handoff.md with the agreed policy: exhausted work stays
UNRESOLVED with spent budget; it does not automatically abort the batch.
Only genuinely different parts may continue after explicit same-boot reliable
communication and confirmed idle/available status. Do not recreate unresolved
work/parts under new IDs. Inspection receives confirmed produced parts only.
Lost heartbeat/restart/uncertain availability pauses new production; reconnect
does not resume a faulted run; abort is an operator decision. A batch with
unresolved parts is incomplete and needs separate confirmed production,
inspection and unresolved counts. No batch logic/counters were implemented.

Review findings:

1. Core retry outcomes and SessionGuard health are separate. High-level
   RetryStopped inherits SessionFault, and ProductionRun disarms all stopped
   production paths, so the wrapper does not directly express the policy's
   distinction. Disarming is not a batch abort command.
2. GET_STATUS already reads current session/state without resending exhausted
   operations or advancing history. There is no dedicated run-level status
   helper robust to intervening late application responses. Do not replace
   the guard or invoke explicit recovery just to refresh same-session status.
3. Matching late completion works within the original deadline and deduplicates
   confirmations. After UNRESOLVED, the ledger preserves the stopped result;
   observe only pumps and can leave application frames queued. Later work may
   quarantine them. No passive post-stop reconciliation/part-confirmation API
   currently exists. completion_count includes configurations, not just parts.
4. Low-level pieces permit different work with healthy same-session state,
   but ProductionRun lacks a supported explicit read-only health/idle
   continuation gate after isolated uncertainty. New IDs alone do not prove
   the part is different; future gateway part-to-operation identity tracking
   must prevent recreating an unresolved batch_id/part_id under new IDs.

Proposed client-only follow-up, awaiting approval: typed stop distinction,
public correlated read_status with shared dispatcher, passive validated late
evidence/deduplication, and explicit same-session health/idle continuation
assessment/authorization. Keep original retry outcomes/budgets immutable and
restart protection unchanged. A separate late-evidence view could record
later production confirmation without rewriting retry history or automatically
resuming; that accounting distinction is proposed, not implemented.

Updated README.md, docs/protocol.md, docs/retries.md and docs/session.md to
link this handoff/review. No firmware/wire-interface change appears necessary.
No client implementation or gateway batch management was added.

Verification: static source/document inspection only. Software/hardware tests
NOT RUN for this documentation-only step; existing PASS history is unchanged.
No serial access, reset, build, flashing, retry-budget reset or global setting
change. COM3 was not opened and remains closed. Physical unplug/replug remains
NOT RUN. Implementation changes require approval before proceeding.

## Approved client-only continuation follow-up

Date: 2026-11-16 (Africa/Cairo). Implemented the subsequently approved status
dispatch, passive late evidence and explicit different-work assessment/action.
The static review above describes the earlier implementation, not current gaps.
Firmware, wire messages, flash settings and partitions are unchanged.

Added pc_test/dispatch.py and evidence.py, integrated with RetryLedger and
ProductionRun. Public read_status issues a fresh, finitely timed GET_STATUS,
correlates its ATR sequence, handles interleaved heartbeats/results and refuses
stale queued status. It consumes no operation number or retry budget. Client
instances share nonreusing process-local ATR sequences. A different boot's
status can be observed without adopting its session or clearing RESTART.

OperationUnresolved is distinct from SessionFault/availability. Original retry
outcomes, attempts, deadlines and exhausted budgets remain immutable. Validated
known-operation PART_PRODUCED evidence is recorded once, separately. The audit
retains RETRY_STOPPED/UNRESOLVED and adds PART_RESOLVED_LATE. Full ATR/CRC,
session, operation, original IDs and allowed attempt sequence must match.
Status/heartbeat/high-water mark never prove production. Evidence cannot clear
faults, rearm a run or submit work.

assess_continuation reports eligibility only, requiring healthy same-session
heartbeats and a NEW correlated configured/idle status. Explicit produce_different
makes its OWN fresh assessment, submits only that different part, and leaves
the normal run disarmed. Retained batch_id/part_id associations block recreating
unresolved parts with new operation/job IDs, including direct retry submission.

| Actual check | Result / evidence |
| --- | --- |
| All software regressions and deterministic new tests | PASS, 48 tests; results/continuation_software_tests.log |
| Targeted COM3 hardware checks, 115200 8N1 | PASS, five groups; results/continuation_hardware.json and .log |
| Exhausted budget | Original three transmissions remain spent; re-entry sends zero bytes; UNRESOLVED unchanged |
| Late result | Original withheld completion confirms op 2 once after op 3; duplicate/mismatched results do not increment evidence |
| Fresh status/continuation | Seven queries; explicit different work succeeds; busy, unresolved-part reuse, restart and unconfigured states denied |
| Firmware/main hashes | PASS, unchanged; results/continuation_firmware_before.csv, _after.csv and _verification.log |
| Independent COM3 reopen/close | PASS; results/continuation_verification.log; port closed afterward |
| Unchanged protocol/production/history/session/retry hardware suites | NOT RERUN; earlier PASS evidence retained |
| Physical unplug/replug | NOT RUN |

Development software runs exposed fixture issues: a historical fake lacked the
new dispatcher, and status fixtures used heartbeat counters older than the
validated heartbeat. Corrected fixtures rather than weakening freshness. The
final log records 48 PASS. The hardware late-result fixture releases a REAL
completion withheld by the PC, retaining its original receipt time and logging
release separately; this does not claim physical UART delay. Stale-status
coverage includes an explicitly logged synthetic old frame. Initial fixture
reset and deliberate restart clear RAM; ordinary APIs do not reset the board.

Repeat with the existing ESP-IDF v6.1 / Python 3.11.9 environment:

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python pc_test/continuation_test.py --port COM3 --log results/continuation_hardware.json
```

Close other serial readers first. The hardware fixture deliberately resets RAM
for isolation/restart coverage. No build or flash was needed. Final independent
port reopen/close succeeded. No serial monitor remains open.

Updated README, protocol/run/retry docs, gateway handoff, test/evidence indexes
and docs/continuation.md with the API contract/examples and exception changes.
Remaining limits: PC ledger/session/sequence allocation is RAM-only; loss of
client state requires explicit reconciliation, since STATUS cannot rebuild a
batch. Unknown/unregistered and other-session historical results are not
automatically credited. One synchronous reader is required. Status is a
point-in-time check; final firmware state/session rejection still applies.
No batch scheduling/counts, inspection sender, persistence, abort UI or automatic
resume was added. Physical unplug/replug remains NOT RUN. Stopped after this
approved follow-up with COM3 closed.

## Physical USB acceptance and final handoff cleanup

Date: 2026-11-16 (Africa/Cairo). User performed both physical cable removals
and reconnections after explicit instructions. Added only a guided acceptance
fixture and documentation; no firmware/client behavior, persistence or batch
features changed. Existing valid regression evidence was reused, not rerun.

Commands executed with the existing installed Python (no activation/global
changes needed in this terminal):

```powershell
& 'C:\esp-tools\python_env\idf6.1_py3.11_env\Scripts\python.exe' -u pc_test/physical_acceptance.py --port COM3 --log results/physical_acceptance.json
& 'C:\esp-tools\python_env\idf6.1_py3.11_env\Scripts\python.exe' -u pc_test/physical_acceptance.py --phase producing --port COM3 --log results/physical_acceptance_producing.json
```

COM3: 115200 baud, 8N1, no flow control; DTR/RTS false before open, no deliberate
reset pulse or flash. Actual USB power removal restarted the board both times.

| Check | Actual outcome |
| --- | --- |
| First discovery | FAIL: GET_STATUS transmitted, repeated invalid 17-byte fragments, no valid response; COM3 closed; retained physical_acceptance_attempt1.json |
| Bounded read-only diagnostic | PASS: valid status and two heartbeats, no reset; physical_discovery_diagnostic.json; cause of initial failure undetermined |
| Unchanged fixture rediscovery | PASS: boot 08ddc9d4b70bb99c61790a498e20504b, UNCONFIGURED; explicit idle configuration succeeded |
| Physical idle unplug | PASS: user confirmed removal; Windows serial PermissionError/SerialException; unavailable/faulted, no new work |
| Idle replug/discovery | PASS: new boot 438ba8ad8f02e0a22d5359200cf99ade, UNCONFIGURED, no active operation, high_water=0 |
| Idle restart protection | PASS: no automatic resume; old-session configuration rejected SESSION_MISMATCH, settings/history unchanged |
| Explicit idle recovery | PASS in raw retry evidence: configure op 1 and new part op 2 COMPLETED |
| Fixture idle result recording | FAIL: duplicate result keyword raised TypeError AFTER completion; preserved overall passed=false; corrected reporting field only |
| Physical production unplug | PASS with operator-confirmed timing: accepted 60,000 ms job, physical removal confirmed; accepted work stopped FAULT, no recorded completion |
| Production replug | PASS: new boot 39c8595774fe7eff029715ae32437563, UNCONFIGURED/high_water=0; no automatic resume; old-session probe rejected without state changes |
| Re-entry of stopped work | PASS: zero transmissions, original outcome/deadlines/attempt count unchanged; no fresh retry permission |
| Explicit recovery/new different part | PASS: new-session config op 1, new identified job op 2 COMPLETED |
| Final closure/source comparison | PASS: both fixtures closed COM3; firmware/main before/after SHA256 lists match; no build/flash |
| Physical same-session recovery under external power | NOT RUN: both actual cable removals restarted the board |

The interrupted operation is boot 438ba8ad8f02e0a22d5359200cf99ade, op_no 4,
job physical-long-job:4, batch physical-interrupted, part_id 2. Its original
retry outcome is FAULT/HEARTBEAT_TIMEOUT, accepted=true, one transmission,
confirmed_produced=false. Its physical outcome remains UNCERTAIN. Reconnection,
new boot/status/high-water mark and the later different job do not resolve it.
Do not recreate it with new IDs or send it for inspection.

Timing limitation: operator confirmation was processed about 81.6 seconds
after ACCEPTED. The operator reported unplugging during production, but actual
unplug time was not independently timestamped. The guided fixture pauses serial
processing while awaiting input, so this run does not measure exact cable-loss
latency or demonstrate continuous receive scheduling during the human pause.
Actual serial errors/restarts are recorded. Exact five-second deadline tests
and continuous heartbeat routing remain covered by prior valid software/session
evidence. The physical job stopped after ONE attempt; it is not called retry-
count exhaustion. Exhausted-three-transmission immutability is established by
existing Step 5C and continuation evidence, reused for this acceptance.

Evidence: physical_acceptance_idle.json/.csv (raw idle fixture and completed
recovery, honestly passed=false due reporting failure),
physical_acceptance_producing.json/.csv (ten checks PASS),
physical_acceptance_summary.json (seven idle checks plus recovered completion,
ten production checks, limits and uncertain identity), and
physical_firmware_before.csv/_after.csv. Original discovery failure and
successful diagnostic are retained separately. No application correction was
needed; no feature or firmware/interface changes were made.

Final handoff: docs/acceptance.md is the standalone evidence/scope/limitations
summary with exact setup/build/application-only-flash/test commands and minimal
gateway usage. Updated README, gateway handoff, protocol/session/run docs and
results index. Superseded static API review is archived rather than presented
as current gaps. Explicit warnings: both histories are RAM-only, one serial
reader owns the port, uncertain outcomes need explicit reconciliation, and
gateway batching/inspection/operator UI/full-system integration and Milestone 2
benchmarking remain pending. Stopped with COM3 closed.


## GitHub contribution packaging (separate copy)

Date: 2026-11-16 (Africa/Cairo). This section applies to the repository copy,
not to a mutation of the verified working project. Authorized checkout:
C:\Networks\Networks_Project-member1; subsystem member1/production-a/;
branch member1/production-a. Remote was rechecked empty immediately before
initialization. Minimal root README initialization commit on main:
4fa0883724474c177325e222b0bad00b7d738fb7. GitHub confirms main is default.
The subsystem is not merged into main.

Preserved firmware/settings/operational Python exactly. Parameterized only
ESP-IDF activation paths, redirected the host C test from archived results to
auto-removed temporary output, and updated current repository instructions.
Historical paths, failed attempts, raw JSON/CSV/log/partition evidence remain
unchanged; all 118 included raw evidence files match source SHA256 hashes.
Git attributes disable line-ending conversion on results/**. Included sdkconfig
and defaults, source/CMake, all Python modules/requirements, tests and docs.
Excluded generated builds/caches/host executables/environments/toolchains and
unnecessary archives; original brief PDF/team guide DOCX remain local.

Software-only verification from the contribution folder: 48 tests PASS,
including actual host C history code. No COM3 access, hardware rerun, firmware
build or flash. Verification output and integrity manifest are under
verification/, separate from archived results. Credential scan and staged
review are required before committing. See docs/repository_setup.md for
portable setup/dependencies and docs/acceptance.md for retained limitations.
Both histories remain RAM-only; one reader owns serial; gateway/full-system
integration is pending. The original working project is preserved.
