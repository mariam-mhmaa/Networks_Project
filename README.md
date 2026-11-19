# MCT431 Industrial Communication - Milestone 1

A two-station production simulation: ESP32 A produces identified parts over
USB serial; the gateway queues them and asks ESP32 B to inspect them over TCP.
B calculates PASS/FAIL using the operator's runtime rule. The browser sends
HTTP commands and receives live WebSocket status.

Milestone 1 includes the working application, framing, separate delivery /
acceptance / completion events, bounded retries, duplicate protection and
evidence. The full protocol benchmark, MQTT migration and authentication are
Milestone 2 work.

## Start here

- [Architecture, ownership and operating states](docs/architecture.md)
- [Station message and framing specifications](docs/station-protocol.md)
- [Operator HTTP/WebSocket contract and recovery](docs/operator-protocol.md)
- [Software checks and hardware evidence](docs/testing.md)
- [Submission contents, measurements and limitations](docs/submission.md)
- [Contributions and third-party provenance](docs/contributions.md)

```text
gateway/                 Python application; production, inspection and operator modules
stations/production/     ESP32 A firmware, native tests and standalone diagnostics
stations/inspection/     ESP32 B firmware, native tests and standalone diagnostics
shared/station/          Shared C lifecycle/parser and licensed cJSON source
operator_ui/             Original toy-workshop theme, assets and browser tests
tools/                   Verification, software preview, measurement export and packaging
Test_Cases/              Original hardware evidence and report assets
verification/            Recorded software/build verification
reference/               Original assignment PDF and team proposal
```

The integrated launcher is `gateway.operator`. The standalone diagnostic
programs and `operator_ui/mock_gateway.py` are not the real gateway.
The folder cleanup does not require reflashing boards already running the
tested integrated firmware.

## Devices and tools

- Two ESP32 boards, a data-capable USB cable for A and USB power for B.
- Gateway PC: tested on Windows 11; it owns A's COM port and B's TCP connection.
- Operator PC: a browser. It does not run another gateway.
- A shared Wi-Fi LAN/hotspot for B, the gateway PC and the operator PC.
  A uses USB data to the gateway. B's USB connection supplies power; inspection
  messages travel through Wi-Fi/TCP.
- Python **3.11.9** and the root `requirements.txt` for the gateway, checks and plots.
- ESP-IDF **v6.1.1**, ESP32 target: needed to configure/build/flash firmware.
- Visual Studio 2022 C/C++ tools (MSVC): needed for native station software tests
  and the explicit software preview.
- Node.js **v24.22.3** was used for browser-adapter tests; it is not needed to
  open the real interface.
- Wireshark with its capture driver: needed for network evidence.
- Host GCC is needed only for the retained legacy production history test.

Python dependencies do not install ESP-IDF, compilers, Node.js or Wireshark.
The dependency versions are pinned to the working/tested versions; do not
upgrade them as part of setup.
The native fixtures use the tested Community-edition default location,
`C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat`.
An installation with another layout needs the corresponding fixture tool path.

## 1. Install Python dependencies on the gateway PC

From the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

For an existing working environment, use that environment and the same pinned
versions. The report and software tests can also run on the operator PC with
the same environment. Python's `sqlite3` is included in the standard library.

When updating an existing gateway checkout, first finish/close its batch and
stop the gateway while Idle. Pull the update, keep the same database/serial log,
then relaunch with the command below. This loads the relocated UI asset path;
it does not require a firmware reflash or a new batch.

## 2. Configure or flash firmware only when needed

Use an ESP-IDF PowerShell session. With the installation used for verification:

```powershell
$env:IDF_TOOLS_PATH = 'C:\Espressif'
. 'C:\Espressif\esp-idf-v6.1.1\export.ps1'
```

Adjust those installation paths for your machine. Run the following commands
from the repository root. Replace `<A_COM>` and `<B_COM>` with the identified
board ports before running commands.

**A - production firmware**

```powershell
idf.py -C stations/production/firmware build
idf.py -C stations/production/firmware -p <A_COM> -b 115200 flash
```

A uses UART0 at 115200 baud, 8N1. Its configured main-task stack is 8192 bytes.
The project inputs retain the tested ESP32 configuration.

**B - inspection firmware**

```powershell
idf.py -C stations/inspection menuconfig
idf.py -C stations/inspection build
idf.py -C stations/inspection -p <B_COM> flash monitor
```

In menuconfig, enter the real hotspot credentials under **Inspection Station
Wi-Fi**. Under **Inspection Station TCP**, use the agreed port (default 5001)
and leave **test-only framed echo disabled** for the integrated application.
Record B's IPv4 address from its startup output. Exit the monitor with Ctrl+].
Keep credentials and generated B sdkconfig/binaries local.

Use full `flash` for an initial installation. `app-flash` is available for
an application-only update on an already configured board. Flashing is not a
routine step when opening the workshop. Do not flash or open A's serial
monitor while the gateway owns its port.

Windows can have trouble with long build paths. If necessary, use a short
checkout path while preserving the complete repository hierarchy; both
stations depend on `shared/station`.

## 3. Identify ports and network addresses

On the gateway PC:

```powershell
Get-PnpDevice -Class Ports -PresentOnly | Format-Table Status,FriendlyName -AutoSize
ipconfig
```

Identify which COM port belongs to A rather than assuming a fixed number.
If both USB adapters have the same name, identify/label the boards during
initial setup before starting the gateway. Use the gateway's **Wi-Fi IPv4
address**, not a WSL/virtual-adapter address or the hotspot phone's address.

B, the gateway and the operator must be able to reach each other on the LAN.
In the tested phone-hotspot setup, gateway/operator/B were respectively
172.20.10.2 / 172.20.10.5 / 172.20.10.3. These are examples, not fixed settings.
Addresses may change after reconnection. Check phone client isolation if
devices cannot communicate.

If Windows Firewall blocks the operator connection, create a scoped rule on
the gateway in administrator PowerShell. Replace both example placeholders:

```powershell
$gatewayIp = '<GATEWAY_WIFI_IP>'
$operatorIp = '<OPERATOR_WIFI_IP>'
New-NetFirewallRule -DisplayName 'MCT431 operator TCP 8080' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -LocalAddress $gatewayIp -RemoteAddress $operatorIp -Profile Any
```

The operator connects to gateway TCP 8080. The gateway connects outward to
B TCP 5001. Do not disable the firewall or open unrelated ports.

## 4. Start the integrated system

1. Turn on the shared hotspot/LAN and connect the gateway PC, operator PC and B.
2. Connect A's USB data cable to the gateway PC; power B.
3. Close other programs that own A's COM port or B's single TCP connection.
4. On the gateway PC, from the repository root, run:

```powershell
.\.venv\Scripts\python.exe -B -m gateway.operator <A_COM> <B_IP> --host <GATEWAY_WIFI_IP> --port 8080 --inspection-port 5001 --state-file gateway.sqlite3 --serial-trace serial.local.jsonl
```

Replace every angle-bracket placeholder. Leave this terminal running.
The default host is 127.0.0.1; the explicit LAN address is needed for the
separate operator PC. Keep using the same database and serial log across
sessions.

5. On the operator PC, open `http://<GATEWAY_WIFI_IP>:8080/`.
   The gateway serves the real page and API together. Do not open index.html
   directly or launch the mock server. Correct the page's gateway address if
   it remembers another machine.
6. Wait for **Gateway live**, both stations connected, **Idle**, and no
   pending control before starting work.

If old runs or a changed station boot require recovery, review the recorded
results and follow [the recovery contract](docs/operator-protocol.md).
A browser refresh does not grant permission to repeat uncertain work.

## 5. Run a batch

Enter target parts (1-64), production/inspection times in seconds, N, K,
queue capacity (1-64), and **Wait for space** or **Raise Fault**.
The rule is FAIL when `(part_id + K) % N == 0`, computed on B.
Allowed times are 0.001-600 seconds, N is 1-2147483647, and K is
-2147483648 through 2147483647.

- **Start** configures both stations and creates a new batch.
- **Pause** stops new dispatch; accepted jobs finish and queued parts remain.
- **Resume** continues the same paused batch after readiness checks.
- While paused and both stations idle, change times/N/K and press
  **Apply settings while paused**. Wait for both confirmations before Resume.
  Editing input boxes alone does not change active settings.
- **Stop** finishes current jobs, performs bounded recovery and closes the
  batch. It does not inspect queued inventory. A later Start creates a new batch.

A fully completed batch shows **Idle / Completed**, with:
`produced = inspected = target`, `PASS + FAIL = inspected`, and zero
unresolved/not-started/not-inspected work. A stopped or uncertain batch may
be **Incomplete**, retaining all actual PASS/FAIL results. Technical errors
never become invented FAIL verdicts. Missing-work categories can overlap.

## 6. History and evidence

Select an entry in **Batch history** and use **Download batch report** for
its `batch-N.json`. Viewing/downloading history does not start work.
Short on-screen identities are persistent aliases; original full IDs remain
in wire messages and exported technical evidence.

On the gateway PC, relative to the working directory used to launch it:

| File | Purpose |
|---|---|
| `gateway.sqlite3` | Durable application journal, batch history, part numbering and ID aliases |
| `serial.local.jsonl` | Append-only raw A USB TX/RX hex chunks and capture health/session records |
| Saved `.pcapng` | B TCP and operator HTTP/WebSocket network evidence |
| Downloaded `batch-N.json` | Selected batch's settings, parts, stages, results and recovery evidence |

Save screenshots of transient GUI states during the case. Save the raw
Wireshark capture; annotated packet screenshots can be made from it later.
Capture on gateway Wi-Fi with `tcp port 5001 or tcp port 8080`.
Start capture before browser refresh/configuration/Start.

Collect a consistent copy of the database/serial log after a clean shutdown
while Idle. Do not delete the database to clear a Fault. A's serial log is
not B's USB console output and is not a substitute for TCP captures.

## 7. Software checks

These commands use native localhost peers, not physical ports:

```powershell
.\.venv\Scripts\python.exe -B tools/verify_operator.py
.\.venv\Scripts\python.exe -B tools/verify_station_integration.py
.\.venv\Scripts\python.exe -B tools/verify_duplicates.py
```

Require PASS/exit code 0. The first command covers operator/history/capture,
native A/B integration and nine browser-adapter checks. The second adds the
serial-worker checks; the third focuses on eight duplicate cases.
[Testing](docs/testing.md) explains individual suites, prerequisites, current
physical evidence and pending cases.

For a labelled software preview only:

```powershell
.\.venv\Scripts\python.exe -B tools/run_operator_preview.py --state-file preview.sqlite3
```

It uses actual C applications on localhost, requires MSVC, and never supplies
physical-hardware evidence. The real system must use `gateway.operator`.

## Troubleshooting and limits

- Page unreachable: check gateway Wi-Fi IP, listener, LAN membership, firewall
  and hotspot isolation. `localhost` on the operator PC points to that PC.
- A disconnected: check the identified COM port, data cable and exclusive
  ownership. Serial-port opening can reset some boards; boot fencing detects it.
- B disconnected: check power, its current IP, Wi-Fi credentials, normal
  application image and whether another client owns its TCP server.
- Page reconnects in Paused: operator loss deliberately pauses new dispatch;
  review current work, then explicitly Resume.
- Settings did not change: press Apply while paused/idle and wait for confirmation.
- Stop enters Fault: preserve evidence and use explicit recovery; do not keep
  pressing controls or clear uncertainty by resetting devices.
- A/B outcomes are RAM-retained within bounded runs. Restarts change boot
  identities; the gateway does not silently reexecute old jobs.
- The gateway does not automatically restore execution after its restart.
  The database retains history, not permission to resume old work.
- Initial heartbeat/deadline values and pending physical failure cases are
  documented in Testing. Software success is not a claim of every hardware case.
