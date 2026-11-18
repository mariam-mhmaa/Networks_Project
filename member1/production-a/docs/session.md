# Step 5B heartbeat and restart contract

The approved client-only follow-up is implemented in docs/continuation.md:
fresh read-only status, separate late-part evidence and explicit different-work
eligibility/action. These never clear the fault/recovery requirements below.

This Step 5B wire contract adds a restart fence and link observation to Step
5A. Step 5C now adds bounded Python retries (docs/retries.md), without firmware
or message changes. Persistent history, batching and gateway queues remain absent.

The agreed batch handoff policy in docs/gateway_handoff.md distinguishes an
isolated unresolved operation from station/session unavailability. Health
uncertainty pauses new production; reconnection never automatically resumes
a faulted run. Batch abort remains an explicit operator decision.

## Session discovery and bound production requests

Send an ATR with test_id 0 and any chosen nonzero correlation seq, payload:

```json
{"type":"GET_STATUS"}
```

It returns STATUS with the same ATR seq. No boot_id, op_no or command ID is
required. Discovery does not configure, produce, increment the accepted
high-water mark, consume an operation number, replace history, or increment
the heartbeat counter. It is valid in every state, including PRODUCING.

Example STATUS (the token is illustrative; use the actual discovered value):

```json
{"type":"STATUS","boot_id":"0123456789abcdef0123456789abcdef","state":"UNCONFIGURED","active_op_no":null,"high_water":0,"production_time_ms":0,"heartbeat_no":0}
```

All configuration and production requests now REQUIRE that boot_id:

```json
{"type":"CONFIGURE_PRODUCTION","boot_id":"0123456789abcdef0123456789abcdef","op_no":1,"cmd_id":"cfg:1","production_time_ms":1000}
{"type":"PRODUCE_PART","boot_id":"0123456789abcdef0123456789abcdef","op_no":2,"job_id":"job:2","batch_id":"batch-1","part_id":1}
```

There are exactly five configuration / six production fields. Existing ID,
suffix, numeric limits and Step 5A decision order remain. The session check
precedes history lookup, configuration change and timer effects. A missing,
wrong-type or different boot_id gets RECEIVED then REJECTED/SESSION_MISMATCH
when application IDs are usable; malformed JSON or unusable IDs remain silent.
All production JSON responses include the CURRENT station boot_id, including
session rejections and replayed historical results. The receiver treats a
response from another boot as a restart fault, never as a completion for the
old run. Failed framing/length/CRC still prevents trusting any identifiers.

## boot_id generation

Every application startup generates 16 bytes (128 bits) with esp_fill_random.
Since this station does not start Wi-Fi/Bluetooth, it explicitly calls
bootloader_random_enable to enable the internal physical SAR ADC entropy
source, fills those bytes, then bootloader_random_disable before other work.
There are no ADC/RF users during this short generation window. This follows
the installed ESP-IDF v6.1 Random Number Generation guide and esp_random.h.

The bytes are encoded as exactly 32 lowercase hexadecimal characters. The
token is opaque and is not based on uptime, an operation number, MAC address,
or a counter reset to zero. An independent pair's collision probability is
approximately 1 / 2^128. It is a session identifier, not a secret, signature or
authentication mechanism. No NVS or flash writes are used.

RAM history remains lost at reset. Unlike Step 5A, an unchanged old request
now contains the old boot_id and cannot execute after restart. Deliberately
rebinding an uncertain old operation to the NEW boot_id is still capable of
executing it again after configuration. There is no persistent work ledger;
the gateway must never perform that rebinding/resubmission automatically.

## Heartbeat framing and contents

The station sends HEARTBEAT with test_id 0, ATR seq **0**, about once each
1000 ms in UNCONFIGURED, IDLE and PRODUCING. It uses normal ATR length/CRC and
SLIP escaping. Example:

```json
{"type":"HEARTBEAT","boot_id":"0123456789abcdef0123456789abcdef","state":"PRODUCING","active_op_no":2,"high_water":2,"production_time_ms":1000,"heartbeat_no":7}
```

active_op_no is null when inactive; high_water is the highest ACCEPTED number.
heartbeat_no increases for each heartbeat within the boot and starts at 1.
STATUS reports the current counter without advancing it. The receiver requires
a fresh increasing heartbeat_no, valid status fields, current boot_id, valid
CRC and the unsolicited seq 0 before refreshing liveness. Duplicate/out-of-order
heartbeats, statuses, ordinary replies, invalid frames and other sessions do
not refresh the five-second deadline. No counter wrap is supported (uint32
heartbeat capacity exceeds 136 years at one per second).

Requests should use nonzero ATR seq values. Request replies, status replies,
duplicate status/results and original delayed completion retain Step 5A's
correlation rules. Heartbeats are identified by TYPE plus test_id/seq/session,
not by seq alone. An explicit seq-0 request is still distinguishable by type.

The existing single main loop serializes all full frames through send_record.
Heartbeat polling and timer completion run in that loop, not a concurrent
printing task or ISR. Bytes cannot interleave with a response frame. The
heartbeat target period can include the 20 ms poll wait and short frame
serialization; this is not a hard real-time scheduling claim or benchmark.
Production deadline behavior and nonzero-ID XOR records are unchanged.

## PC state and recovery rules

Receiver incrementally separates unsolicited heartbeats/status from responses.
Only an explicitly outstanding GET_STATUS seq routes STATUS back to a request;
other status frames remain observations. Heartbeats never satisfy a request's
acceptance/completion expectation. Logs retain raw RX chunks and decoded status
observations separately from request responses. During invalid-input tests,
silence means no request-specific response/action, not no serial traffic.

SessionGuard uses time.monotonic. Initial discovery binds the intended boot,
but STATUS alone does not make it available: a fresh heartbeat is required.
At **>=5.000 seconds** since the last valid current-session heartbeat, it marks
unavailable and latches HEARTBEAT_TIMEOUT. It continues reading. Fresh
same-session heartbeats can restore link availability, while the RUN fault
stays latched: work does not resume. A different valid boot_id latches RESTART,
stops the old run and is reported separately from same-session reconnection.
An old-session heartbeat cannot clear that restart fault.

An already accepted firmware job can finish while the PC loses contact; this
step does not add an abort command. The PC must treat uncertain work as faulted,
not automatically continue/resubmit it. Restart itself clears active work.

The gateway example ProductionRun enforces explicit recovery:

1. Caller invokes connect_or_recover (new guard and read-only discovery).
2. Caller configures the discovered session and waits for confirmed completion.
3. Caller invokes start explicitly.
4. Caller may produce a new identified operation. Step 5C may retransmit the
   same operation within its original budget/deadlines, never across a fault.

Timeout/restart faults invalidate local configuration/start permission.
ProductionRun.observe continues reading after a fault. station_watch.py is a
read-only CLI that can reopen a disconnected port and rediscover status, but
never configures, produces, clears a run fault or resubmits work. Its reconnect
discovery is observation, not a retry of an uncertain operation.

Call observe/pump regularly while idle; this is a single-threaded receiver,
not a hidden background monitor. Synchronous production waits already pump
incoming frames. Use station_watch's loop for continuous read-only observation.

Low-level Client/raw test APIs intentionally permit diagnostic invalid-input
probes; use ProductionRun for the explicit operational start/recovery gate.

## PC examples and repeat commands

```python
from gateway_client import ProductionRun
# port already opened at 115200 8N1 with DTR/RTS false; report is a log dict.
run = ProductionRun(port, report)
status = run.connect_or_recover()       # read-only, learns boot_id
run.configure(1, "cfg:1", 1000)        # explicit current-session configuration
run.start()                           # explicit NEW start
result = run.produce(2, "job:2", "batch-1", 1)
# On SessionFault: stop issuing work, observe, then require an explicit recovery.
```

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python pc_test/framed_test.py --port COM3 --log results/step5b_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5b_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5b_history_regression.json
python pc_test/session_test.py --port COM3 --log results/step5b_sessions.json
python pc_test/station_watch.py --port COM3 --seconds 30
```

Opening ports sets DTR/RTS false before open. Ordinary reconnect does not pulse
reset. Tests identify their deliberate RTS/EN resets; production/history test
fixtures reset RAM intentionally. All runners close the port.

Heartbeat-loss hardware testing uses controlled RX-heartbeat suppression while
still reading the actual serial connection; this is not physical cable removal.
Ordinary close/reopen and deliberate firmware restart are tested separately.
Physical idle and production unplug/replug were subsequently performed with
the guided physical_acceptance fixture. Both reconnections had new boot IDs;
old-session requests were rejected and explicit recovery completed new jobs.
See docs/acceptance.md for raw evidence, uncertain-part preservation and limits
on human timing/fixture scheduling. External-power physical same-session
disconnection remains NOT RUN. No automatic resume was added.
