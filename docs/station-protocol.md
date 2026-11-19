# Station protocols and operation reliability

This is the implemented Milestone 1 A/B contract. The original assignment is
in `reference/`; agreed numeric bounds are implementation choices, not values
quoted from the assignment. The real operator API is specified separately in
[operator-protocol.md](operator-protocol.md).

## A: UART, ATR, CRC and SLIP

Production A uses UART0 through USB at **115200 baud, 8N1**. Each ATR record is
SLIP-encoded, with the following big-endian decoded layout:

| Field | Bytes | Meaning |
|---|---:|---|
| test_id | 2 | Zero for integrated application JSON |
| sequence | 4 | Transport-attempt sequence, nonzero for application requests |
| payload_length | 2 | JSON byte count, at most 1024 |
| payload | 0-1024 | UTF-8 JSON for test_id zero |
| CRC | 2 | CRC-16/CCITT-FALSE over header and payload |

CRC polynomial is 0x1021, initial value 0xFFFF, no reflection/final XOR.
SLIP END is 0xC0; payload 0xC0 becomes 0xDB 0xDC and 0xDB becomes 0xDB 0xDD.
Both ends validate frame bounds and CRC before trusting application contents.
The retained nonzero-test-ID diagnostic path XORs payload bytes with 0xA5.
It is not production work or an inspection verdict.

ATR sequences identify transmission attempts; they are not job identities.
A retry may use a new transport sequence while preserving the entire original
application ID and contents. A's actual production result is `produced:true`;
A never calculates PASS/FAIL.

## B: TCP length framing

Inspection B is a Wi-Fi station and one-owner TCP server, default port **5001**.
A second TCP client cannot replace the current owner. Every frame is a
four-byte unsigned big-endian length, followed by **1-1024 bytes of UTF-8 JSON**.
The prefix excludes itself. Reads can be fragmented or contain several frames;
neither a socket read nor a TCP packet is assumed to equal one message.

TCP success/ACK is transport evidence, not application acceptance/completion.
Malformed length, UTF-8/JSON, duplicate keys, embedded NUL or an untrustworthy
envelope closes the connection without inventing an acknowledgement identity.
An otherwise trustworthy invalid request can receive a retained rejection when
admission has capacity.

## Common identities and context

Every request has `v:1`, `type`, `boot_id`, `batch_id`, `run_no` and either
`cmd_id` (commands) or `job_id` (PRODUCE/INSPECT).
Opaque IDs contain 1-96 ASCII letters, digits, underscore, colon or hyphen.
They are preserved unchanged in requests, replies, logs and protocol adapters.

Origin-generated IDs use `ACTION-ISSUER-SESSION-COUNTER`: issuer GW/OP,
32 lowercase hexadecimal UUID4 session, independent positive per-action
counters with minimum six-digit padding. Action is also an explicit message
field; receivers do not route work by dissecting an ID. Production and
inspection of one part are different operations with different job IDs.

`boot_id` identifies the receiver's current boot, distinct from the issuer's
session. `batch_id` identifies the whole batch. Positive uint32 `run_no` fences
work within a receiver boot. CONFIGURE opens exactly the next run after the
previous run is closed, or reconfigures the current idle batch/run.
`config_version` identifies the applied settings confirmed by that station.
None of these fields is a substitute for another.

Short labels such as `S40` and `Batch 16` are persistent display aliases in
SQLite. Full identities stay authoritative on the wire and in exported reports.
Counters do not wrap or reset between batches within an issuer session.

## Request fields

| Type | Station | Additional fields | Effect |
|---|---|---|---|
| CONFIGURE | A | production_time_ms | Validate/apply production time; return settings/version |
| CONFIGURE | B | inspection_time_ms, N, K | Validate/apply inspection time and rule; return settings/version |
| PRODUCE | A | part_id, config_version | Produce one part with the confirmed configuration |
| INSPECT | B | part_id, config_version | Inspect one part with the confirmed configuration |
| QUERY | Both | target_id, query_no | Read-only snapshot of existing work; never initiates it |
| RETIRE | Both | target_id, part_id | Retain known outcome or fence safely unknown work/part |
| CLOSE | Both | none | Require idle, close this scope and return closed:true |

Times are integer milliseconds in 1-600000. N is 1-2147483647; K is
-2147483648 through 2147483647; part_id is positive uint32.
Boolean JSON values do not count as integers. config_version is positive
uint32. query_no is positive, monotonic uint32 within the receiver boot.
Part numbers are allocated durably by the gateway and retain the same meaning
through A production, queueing and B inspection.

An active job freezes its settings and configuration at acceptance. Busy
reconfiguration is rejected; it cannot change the timer/rule of accepted work.
The gateway requires both stations' confirmations before resuming after an
operator settings change. An already produced but uninspected queued part uses
the new B settings when it is subsequently submitted.

B computes FAIL exactly when `(int64(part_id) + K) % N == 0`; otherwise PASS.
The verdict must come from B with the matching job/part/context. Timers are
software timers with scheduler granularity, not hard real-time guarantees.

Example B configuration, with explanatory shortened operation/batch IDs:

```json
{"v":1,"type":"CONFIGURE","cmd_id":"cfg-example","boot_id":"0123456789abcdef0123456789abcdef","batch_id":"batch-example","run_no":1,"inspection_time_ms":100,"N":3,"K":-1}
```

## Delivery, acceptance, completion and results

Normal requests produce **three replies total**: RECEIVED, ACCEPTED, COMPLETED.
They echo original identity, action, boot, batch and run; job replies also
identify the part. A queryable record exists before RECEIVED. REJECTED/error
does not start work and never becomes a product FAIL.

COMPLETED carries `result` with original identity/context, terminal state,
settings/configuration and elapsed_ms. PRODUCE adds produced:true, INSPECT adds
PASS/FAIL, and CLOSE adds closed:true. QUERY has its own cmd_id/query_no/target_id
and a separate target snapshot; absent work is target:null and stays unexecuted.

Accepted work executes independently of whether the gateway receives either
intermediate acknowledgement. Completion is cached before immediate nonblocking
publication. A full/disconnected transmitter retains unsent outcomes without
blocking execution; a later duplicate/query can recover retained evidence.
TCP reconnect resets framing/TX state, not application timers or retained history.

A same-ID semantically identical request returns existing progress/result or
rejection without another execution. Canonical SHA256 fingerprints ignore JSON
key order/formatting. Changed contents under the same ID produce ID_CONFLICT
without replacing the original record. A new ID cannot process an already
accepted part again in the same run. Rejections remain immutable.

## History, closing and retirement

Both stations retain bounded RAM history per run:

- 64 job records, including distinct rejected requests and retirement tombstones.
- 16 configuration/closure records, with the final slot reserved for CLOSE.
- 8 query snapshots with a monotonic high-water fence; evicted old query numbers
  are refused rather than reevaluated. Pending query transmissions are retained.
- A separate 64-record RETIRE pool, avoiding consumption of configuration slots
  for every uncertain part.

History exhaustion refuses admission before acceptance; it does not evict
accepted outcomes or invent verdicts. Up to 64 accepted jobs fit if rejections
or tombstones have not consumed their slots. Closing retains terminal outcomes
until a new valid run opens. Receiver restart loses RAM history and changes
boot identity; old work is not automatically rebound/reexecuted.

RETIRE is explicit recovery control, not QUERY and not execution. An active
target returns BUSY and continues; a known finished target returns its genuine
outcome. A safely unknown target gets a retained REJECTED/RETIRED tombstone and
part fence. Delayed original or fresh-ID requests cannot execute that fenced part.
RETIRE cannot target its own cmd_id and rejects conflicting target context.

To fit the frame bound, RETIRE results contain a compact target snapshot that
inherits job/batch/run/part identity from the validated enclosing result. The
gateway expands inherited fields after validation. QUERY of RETIRE returns the
same immutable snapshot. RETIRE does not replace unrelated current settings.

Known receipt/acceptance followed by UNKNOWN is inconsistent history, not proof
of nonexecution. Guarded continuation refuses it. Where permitted, continuation
requires fresh same-boot/current-run idle evidence and acknowledged job/part
fences; uncertainty remains visible. Incomplete idle closure is the fallback,
so unknown work need not block every future batch indefinitely.

## One bounded operation controller

The initial configurable A/B profile is:

| Limit | Value |
|---|---|
| Receipt response window | 1 second per original/retransmitted request |
| Acceptance | 1 second from first delivery evidence |
| Completion | Configured duration + 2 seconds from first acceptance evidence |
| Retransmissions before acceptance | At most 2, same original ID/content |
| Read-only recovery queries | At most 2, separate query command IDs |
| Query response window | 1 second |
| Absolute cap | Configured duration + 10 seconds from first submission |

Commands have zero configured execution duration. Queries do not recursively
create recovery queries. Reconnection, duplicate ACKs, PENDING_VALIDATION and
IN_PROGRESS do not reset budgets or deadlines. Later valid evidence establishes
earlier facts without fabricating missing ACK observation timestamps.

Results must match boot/run/batch/action/operation/part/configuration and frozen
settings; inspection adds the explicit verdict and plausible elapsed duration.
The controller returns COMPLETED, REJECTED or UNRESOLVED. Late lookup is recorded
separately from exhausted original deadlines. Conflicting terminal evidence holds
dispatch without silently overwriting the original result.

## Heartbeats and reconnect

Unsolicited heartbeats include v/type, boot, station, run_no/batch_id/run_open,
IDLE/BUSY, config_version, query_high_water, retained record counts, executions
and increasing heartbeat_no. They are availability/context evidence, not a
substitute for the correlated result of a requested part.

| Link | Initial heartbeat period | Gateway stale threshold |
|---|---:|---:|
| A serial | 1 second | 5 seconds without a fresh increasing heartbeat |
| B TCP | 500 ms when transmitter permits | 1.5 seconds |

A duplicates/old heartbeat numbers and ordinary replies do not refresh its
liveness. Serial I/O failure can hold dispatch earlier. B initial connection
discovery has three bounded one-second attempts, separated by 30 ms.
Operation reconnects are owned by their controller and consume existing bounds.

A validated same-boot B heartbeat clears an obsolete failure from a prior
connection. Invalid/failed greetings do not establish freshness. A changed boot
remains latched until explicit recovery. Physical serial-port opening can toggle
board reset lines despite requested DTR/RTS state; new boot evidence is handled
rather than assuming the boot survived reopening.

Heartbeat and deadline values are initial engineering settings. Hardware tuning
must preserve bounded attempts, independent execution and explicit reconciliation.
