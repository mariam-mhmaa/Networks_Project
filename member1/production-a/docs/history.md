# Step 5A gateway contract and RAM history

Production JSON uses ATR test_id 0 and now REQUIRES `op_no` on every request.
Existing SLIP, ATR, CRC, 1024-byte payload limit and nonzero-ID XOR behavior
are unchanged. No persistent history exists. Bounded Python retries are now
implemented in Step 5C (docs/retries.md). Step 5B's
session requirements in docs/session.md also apply: retain boot_id with op_no
and full IDs on a retry. Current wire examples include that required field.

## Required identifiers for the gateway member

```json
{"type":"CONFIGURE_PRODUCTION","boot_id":"0123456789abcdef0123456789abcdef","op_no":1,"cmd_id":"cfg-1:1","production_time_ms":1000}
{"type":"PRODUCE_PART","boot_id":"0123456789abcdef0123456789abcdef","op_no":2,"job_id":"job-1:2","batch_id":"batch-1","part_id":1}
```

- op_no is a positive JSON integer from 1 through 4294967295, shared by
  configurations and production jobs. No booleans, strings, fractions,
  exponent notation, negative values or wraparound. JSON `01` is malformed.
- cmd_id/job_id MUST end with `:<op_no>` in canonical decimal, no leading
  zeros. The prefix must be nonempty. The COMPLETE ID, including suffix,
  stays within 48 characters and `[A-Za-z0-9_.:-]`.
- A retry retains BOTH op_no AND its original full cmd_id/job_id, plus all
  meaningful application fields. Do not allocate a new number for a retry.
- A used ID cannot be submitted unchanged at a higher op_no: its suffix will
  mismatch and be rejected even after cache eviction. Changing both the full
  ID and number represents a new operation; the station cannot infer intent.
- batch_id keeps its existing rules and has no operation-number suffix.
- Missing op_no is rejected, not derived from ATR seq. Current Step 5B gateway
  payloads require five config / six job fields, including discovered boot_id.

## Ordering and duplicate processing

One accepted high-water mark covers both command types. Fully validate the
record, schema, integer types/ranges and suffix before operation lookup.
Requests with usable application IDs receive RECEIVED. If op_no is usable it
is echoed, including in semantic rejection events. Malformed JSON, unusable
identifiers or failed framing/ATR/CRC get no application response.

The decision order is:

1. Matching active number: compare parsed request fields. Identical returns
   OPERATION_RUNNING; conflicts return REJECTED/OPERATION_CONFLICT. Do not
   change the original sequence, applied duration or deadline.
2. Matching completed number: identical returns the stored terminal result
   with replayed=true, using this arriving request's ATR seq. Conflicting
   contents return OPERATION_CONFLICT. No configuration or production effect.
3. Uncached number at/below high-water: STALE_RESULT_UNAVAILABLE. This says
   neither that the request definitely ran nor that it did not run.
4. Higher number: apply BUSY and NOT_CONFIGURED rules. Only acceptance records
   the operation, advances high-water and then allows settings/timer effects.

Gaps are allowed. Accepting 10 after 6 permanently closes 7-9 during this
boot, even if those numbers never arrived. Rejection never advances progress:
a rejected 100 while busy does not block a later valid 4 when high-water is 3.
An invalid request for 11 can be corrected and accepted as 11 if no accepted
higher number has made it stale. At UINT32_MAX, no new higher number exists.

Meaningful comparison includes type, full cmd_id/job_id, batch_id/part_id for
jobs and production_time_ms for configuration. Parsed values are compared;
JSON whitespace/key order and ATR seq are excluded. A job's duration is frozen
from the applied configuration at acceptance and stored separately from its
request contents.

Responses are framed JSON. New operations keep RECEIVED, ACCEPTED, then
PRODUCTION_CONFIGURED or PART_PRODUCED. Terminal events include replayed=false.
Duplicate requests get RECEIVED, then OPERATION_RUNNING or the stored terminal
event with replayed=true; they do not generate another ACCEPTED. Results
preserve the original full application IDs and operation number.

An arriving duplicate/status response echoes that request's ATR seq. The
original delayed PART_PRODUCED retains the initially accepted request's seq,
even if a running-status query used a different seq. Match operations by
op_no and full IDs; ATR seq correlates individual exchanges.

Replaying an old cached configuration reports its historical applied time,
even while another job is active. It NEVER reinstalls that old setting or
changes a job's deadline. Replay does not refresh FIFO cache position.

## Bounded storage and actual ESP32 RAM

Eight completed results are stored FIFO by completion time. A ninth completion
replaces the oldest result. The active record is a separate member and never
uses a completed slot. Eviction loses result details, not high-water; old
operations remain unable to execute. No heap allocation is used by history.

Actual sizes from the built ESP32 ELF, inspected offline with installed GDB:

| Structure/member | Bytes |
| --- | ---: |
| Parsed operation_t | 116 |
| Result entry result_t | 124 |
| Eight completed entries | 992 |
| Separate active result | 124 |
| High-water/FIFO/count/active flag including padding | 16 |
| Complete history_t | 1132 |
| Separate int64 deadline | 8 |
| History plus deadline | 1140 |

These are history-related static data sizes, not total firmware RAM or peak
stack use. Existing UART/protocol buffers, configuration/callback variables
and temporary parser/event stack buffers are additional. The host GCC test
reported the same structure sizes; target evidence is step5a_target_ram.log.

## Restart limitation

Everything here is RAM-only. Reset/power loss clears the cache, high-water,
active work and configuration. Step 5B rejects unchanged old-session requests
using boot_id. An old operation deliberately REBOUND to the new boot_id can
still execute after configuration, because its RAM history is gone. There is
no persistent work ledger or at-most-once claim across explicit rebinding.
The history regression intentionally rebinds after reset to verify RAM loss;
the session suite separately proves an unchanged old-session request cannot
execute. Do not silently rebind or replay uncertain work after reconnecting.

## Tests and repeat commands

Software: tests/history_core_test.c compiles the actual portable history.c
with the already installed Windows GCC; test_history_core.py executes it.
Existing Python parser/CRC/stream tests also run. No separate Python model is
used as evidence for the C history core.

Hardware: history_test.py resets state and explicitly probes duplicates,
conflicts, suffixes, integer/length bounds, gaps, unchanged active deadline,
historical configuration replay, eviction, continued work and RAM reset.
It checks transport IDs and full application fields, uses finite waits,
records wire/event evidence and closes the port. Intentional duplicate probes
are tests; the client does not automatically retry failed/uncertain requests.

```powershell
. .\docs\activate_idf.ps1
python -m unittest discover -s tests -v
python pc_test/framed_test.py --port COM3 --log results/step5a_protocol_regression.json
python pc_test/production_test.py --port COM3 --log results/step5a_production_regression.json
python pc_test/history_test.py --port COM3 --log results/step5a_history.json
```

Each hardware runner resets/drains startup as needed and releases COM3.
Close all monitors first. Run/build/flash and actual outcomes: docs/run.md and
docs/progress.md. No batching, inspection, gateway queue logic or heartbeats
were added.
