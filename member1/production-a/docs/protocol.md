# ATR over SLIP and production messages

Final [acceptance and gateway handoff](acceptance.md) consolidates setup,
application-only build/flash/test commands, physical results and remaining
integration limits. This wire contract is unchanged by final acceptance work.

Gateway policy and current API scope are recorded in
docs/gateway_handoff.md. An isolated UNRESOLVED operation is not an automatic
batch abort; its budget stays spent. Only confirmed produced parts may go to
inspection. Idle/high-water/status evidence alone is not production completion.
No wire message or firmware change is made by the client-only follow-up.

The subsequently approved client-only APIs are now implemented in
docs/continuation.md: public correlated read-only status, passive late-part
evidence, and explicit different-work assessment/action. GET_STATUS and all
firmware payloads are unchanged. Evidence resolution never rewrites original
retry outcomes/budgets or clears session faults. Status is not part completion.

The Step 3 binary transport remains unchanged. Step 4 routes test_id 0 to
production JSON messages; nonzero test IDs retain the payload XOR application.
Step 5B adds framed heartbeats and session binding; see docs/session.md for
mandatory boot_id, read-only discovery and restart handling. No formal
benchmarking. UART0 is 115200 baud, 8N1, no flow control.

Step 5C changes ONLY the Python client: bounded same-operation retries follow
the existing firmware running/cached-result behavior. No wire fields, firmware
behavior, frame format or session rules changed. See docs/retries.md for the
approved deadlines/budget and outcome handling; requests retain full identity.

## ATR layout

All unsigned multibyte values, including the transmitted CRC, are big-endian.

| Offset | Field | Size |
| --- | --- | --- |
| 0 | test_id | 2 bytes, unsigned |
| 2 | seq | 4 bytes, unsigned |
| 6 | payload_len | 2 bytes, unsigned, 0 through 1024 |
| 8 | payload | exactly payload_len bytes |
| 8 + payload_len | crc16 | 2 bytes |

Decoded record length must be exactly `10 + payload_len`. Reject too-short,
too-long, mismatched-length and bad-CRC records. The reusable ATR functions
accept test_id 0 as a representable value; Step 4 uses it for production JSON.
XOR regression tests use nonzero test IDs.
All ATR sequence values through 0xffffffff are representable. Transport seq
is a correlation field, not the production operation identity. Step 5A uses
op_no for ordering/duplicate protection; it does not enforce ATR seq ordering
or implement automatic retries. See docs/history.md for replay sequence rules.

CRC-16/CCITT-FALSE covers the entire 8-byte header plus payload, excluding the
CRC itself. Polynomial 0x1021; initial 0xffff; no input or output reflection;
final XOR 0. Reference ASCII `123456789` gives 0x29b1 (wire bytes `29 b1`).
CRC detects accidental corruption; it does not authenticate a sender.

## SLIP encoding and recovery

- END is c0; ESC is db.
- A decoded c0 becomes db dc; decoded db becomes db dd.
- Send c0 before and after every encoded record; empty frames are ignored.
- Decoders retain state across arbitrary chunks and can emit several frames
  from a single chunk. Initially ignore bytes until the first END.
- An unknown escape or ESC directly followed by END rejects that frame.
  After an unknown escape/overflow, discard through the next END, then resume.
- A partial frame without a closing END stays buffered, within the size limit.
  There is no parser idle timeout. The next END terminates it; a subsequent
  valid record works. A leading END therefore also resynchronizes the stream.
  An empty frame is ignored; a nonempty truncated ATR is rejected by ATR checks.

Payload maximum: **1024 bytes**. Decoded ATR maximum: **1034 bytes**.
Worst-case encoded maximum: **2070 bytes** = 2 x 1034 + 2 delimiters.
Escapes count toward decoded storage only after unescaping. Decoders have a
fixed decoded limit and enter discard mode on the next decoded byte beyond
that limit. They do not grow buffers for an unlimited input stream.

The C encoder accepts a caller-provided output capacity; it returns zero on
insufficient capacity. Firmware uses a 2070-byte static output buffer and a
1034-byte static decoder buffer. Firmware's UART RX ring is 2048 bytes and is
consumed incrementally, rather than holding the whole encoded frame there.

## Shared complete example

test_id = 0x1234, seq = 0x01020304, payload = `00 c0 db ff`, length = 4.

```text
ATR:
12 34 01 02 03 04 00 04 00 c0 db ff c3 0e

SLIP wire bytes:
c0 12 34 01 02 03 04 00 04 00 db dc db dd ff c3 0e c0
```

CRC c30e was independently calculated with Python's standard-library
`binascii.crc_hqx(body, 0xffff)`. The example is fixed in
`tests/protocol_vector.json` and the C startup self-test; Python's software
test compares exact ATR and SLIP bytes against that fixture. The C self-test
checks the reference CRC, complete ATR validation, exact encoding and
incremental decoding before enabling communication. Failure leaves it silent.

## Nonzero-ID XOR regression application

Only after valid SLIP, exact ATR length, CRC and nonzero test_id does ESP32 A
XOR each payload byte with a5. test_id and seq remain unchanged. Payload
length is unchanged. The response has a newly computed CRC and SLIP encoding.
Invalid input produces no response. `rejection_count` in main.c is a local
volatile uint32 counter, visible to a debugger; no counter query or debug
text is added to the protocol. Each rejected SLIP frame is counted once; a
decoded invalid ATR is also counted once. Empty frames
and bytes before the first delimiter are ignored. The counter resets on boot.

There is no raw printf/status output and normal runtime logs are disabled.
Step 5B heartbeats are complete framed ATR messages, not console text.
ROM/bootloader/early IDF logs still occur after reset because the bootloader
is preserved. The PC records and drains startup output, requiring at least
one second of settling and half a second of silence within five seconds.
Receivers route valid heartbeat/status observations separately from responses.
Reset noise cannot establish a session or refresh liveness; a new boot faults
the active PC run. It is never accepted as a completion for old-session work.

## Validation and limits of the evidence

Software-only: `tests/test_protocol.py` checks CRC/reference/example, field
bounds, every functional input/recovery scenario byte by byte, parser storage
bounds and rejection counting. The existing four Step 2 host tests also run.
These are Python tests, not proof of C parser execution by themselves.

Hardware: `pc_test/framed_test.py` sends the same functional scenarios to the
flashed C implementation. It tests text, special bytes, all byte values, zero
and maximum payload lengths, one-byte writes (including split escapes),
three frames in one write, empty frames, ten invalid-input categories and
an immediate valid recovery after each. The shared reference example also
travels to the device. The C startup self-test must pass for replies to work.

For each invalid category, one test observes no request-specific response for
350 ms; unrelated valid heartbeats/status are allowed and logged separately.
The next sends invalid input and a valid recovery frame together, without
an intervening wait; the only allowed reply is that recovery frame. All
response bytes are compared with independently constructed expected wire
bytes, then decoded/CRC-checked for the evidence log. Reads of at most 17
bytes are accumulated. Read/write phases have finite deadlines (default
three seconds); valid responses get a further 200 ms extra-byte check.
This is bounded functional evidence, not a proof against arbitrary delayed
failures and not a performance benchmark. A failure stops remaining cases,
which are marked NOT RUN in the JSON log. Serial context cleanup closes COM3.

Repeat commands and actual outcomes are in README.md and docs/progress.md.

## Step 4 production JSON (test_id 0)

ATR, CRC and SLIP must validate before parsing application fields. Payload is
a UTF-8 JSON object. This station implements a deliberately restricted flat
schema, with at most eight fields and ASCII field names/string values. IDs
are 1-48 characters from `[A-Za-z0-9_.:-]`; ASCII is a valid UTF-8 subset.
No arrays, nested objects, duplicate keys, unknown fields or trailing content
are accepted. ASCII JSON string escapes (including ASCII `\uXXXX`) are
supported; non-ASCII strings, embedded NUL and overlong strings are rejected.
This bounded parser lives in production.c; it is not a general JSON library.

Requests have exactly the following fields. Numbers must use positive JSON
integer syntax: no quotes, booleans, null, fraction or exponent notation.

```json
{"type":"CONFIGURE_PRODUCTION","boot_id":"0123456789abcdef0123456789abcdef","op_no":1,"cmd_id":"cfg-1:1","production_time_ms":1000}
{"type":"PRODUCE_PART","boot_id":"0123456789abcdef0123456789abcdef","op_no":2,"job_id":"job-1:2","batch_id":"batch-1","part_id":1}
```

production_time_ms range: 1-60000. part_id range: 1-2147483647. Command type is
case-sensitive. Step 5B CONFIGURE_PRODUCTION requires exactly five fields and
PRODUCE_PART exactly six, including required op_no and boot_id. Discover the
actual boot_id using GET_STATUS; the example token is illustrative only.
See docs/history.md for
the mandatory ID suffix, ordering, conflict and replay rules. Responses have test_id 0 and the
same ATR seq as that request, including the delayed completion. A saved copy
of the accepted job's seq and IDs prevents busy traffic changing completion IDs.

For configuration the ordered response events are:

```json
{"type":"RECEIVED","boot_id":"0123456789abcdef0123456789abcdef","op_no":1,"cmd_id":"cfg-1:1"}
{"type":"ACCEPTED","boot_id":"0123456789abcdef0123456789abcdef","op_no":1,"cmd_id":"cfg-1:1"}
{"type":"PRODUCTION_CONFIGURED","boot_id":"0123456789abcdef0123456789abcdef","op_no":1,"cmd_id":"cfg-1:1","production_time_ms":1000,"replayed":false}
```

For a valid production job:

```json
{"type":"RECEIVED","boot_id":"0123456789abcdef0123456789abcdef","op_no":2,"job_id":"job-1:2","batch_id":"batch-1","part_id":1}
{"type":"ACCEPTED","boot_id":"0123456789abcdef0123456789abcdef","op_no":2,"job_id":"job-1:2","batch_id":"batch-1","part_id":1}
{"type":"PART_PRODUCED","boot_id":"0123456789abcdef0123456789abcdef","op_no":2,"job_id":"job-1:2","batch_id":"batch-1","part_id":1,"replayed":false}
```

RECEIVED reports arrival of a structurally parsed application request with
usable identity. It does not mean accepted or complete. ACCEPTED means that
the validated request is allowed to act; PRODUCTION_CONFIGURED and
PART_PRODUCED are separate completion events. A successful serial write alone
is not any of these events.

Semantic rejections with usable IDs get RECEIVED then REJECTED. REJECTED has
a reason: INVALID_CONFIGURATION, INVALID_JOB, UNKNOWN_COMMAND, BUSY or
NOT_CONFIGURED. For an invalid part number the job/batch IDs are echoed but
the invalid numeric field is omitted. Invalid JSON/schema structure,
duplicates, unsupported nested values, or missing/unusable identity are
silently discarded; no production starts. Corrupt framing/ATR/CRC receives
no application response, even if bytes appear to contain usable IDs.

Local states:

| State | Behavior |
| --- | --- |
| UNCONFIGURED | Boot/reset clears RAM configuration; jobs get NOT_CONFIGURED |
| IDLE | Valid config can replace settings; a valid job can start |
| PRODUCING | New work gets BUSY; active duplicate reports running; cached results replay without side effects |

A configuration is validated fully before changing the applied time. An
accepted job starts a monotonic microsecond deadline after its ACCEPTED event
is queued. The main loop polls this deadline after incoming records and each
UART read (20 ms wait). No sleep for production time is used. Incoming
production and nonzero-ID XOR messages remain serviceable while producing.
After completion the station returns to IDLE with the same configuration.
Configuration and jobs are RAM-only; reset loses them. No NVS writes.

Step 5A adds a separate active-operation record, accepted high-water mark and
eight completed results. Identical active requests return running status;
identical completed requests return historical results without side effects.
Old evicted operations cannot execute during the same boot. Read docs/history.md
before integrating: retries require stable op_no AND full suffixed IDs, and
RAM history does not persist across restart. Step 5B rejects unchanged old-boot
requests before history lookup/effects; explicit rebinding to a new boot is
not persistent duplicate protection. Step 5C adds bounded Python retries only;
no batching, inspection or gateway queue management. Heartbeats/session rules:
docs/session.md. A retransmission keeps the payload identical but uses a new
ATR seq; the original delayed completion may still use the first attempt seq.
Both are correlated to the same immutable logical operation and counted once.

The production hardware runner measures receipt of ACCEPTED to receipt of
PART_PRODUCED with time.monotonic(). Allowed elapsed interval is requested
time minus 100 ms through requested time plus 500 ms. This accounts for UART
serialization, host scheduling/read latency and 20 ms polling; it still
distinguishes 1000 ms from 2500 ms. It is functional timing verification, not
Milestone 2 benchmarking. It resets the board on every run so the initial
unconfigured check is repeatable. See docs/run.md for commands.
