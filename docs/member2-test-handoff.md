# Member 2–gateway test handoff

The B firmware and gateway B subsystem are implemented. Host software tests
and ESP-IDF builds pass. Real-board/network tests have NOT been run here.
No board was flashed. This handoff lets the assigned teammate test them.

## Physical functional test

1. Use current main. Build member2/esp32_b_inspection with ESP-IDF for the
   actual ESP32 board. Enter the real hotspot credentials locally through
   menuconfig. Keep INSPECTION_TRANSPORT_DIAGNOSTIC disabled: echo firmware
   cannot process inspection jobs. Our build-evidence images use obvious
   non-secret placeholder credentials; configure/rebuild before flashing.
2. Identify B's actual USB port/chip before flashing. Connect B and the gateway
   PC to the approved PC hotspot (2.4 GHz/WPA2), or the agreed router fallback.
   Obtain B's current IP from its serial log; never assume historical COM/IP.
3. From the repository root, run Python 3.11+ (standard library only):

```powershell
python -B -m gateway.inspection B_CURRENT_IP --parts 6 --inspection-ms 100 --rule-n 3 --rule-k -1 --queue-capacity 2 --full-policy block --state-file gateway-test.sqlite3 --events run.local.jsonl
```

Equivalent entry point:
member2/esp32_b_inspection/tools/exercise_application.py, with the same options.
The command configures B, reserves/queues identified parts, collects B's
verdicts, reports inspection counts, and explicitly closes the run.

The test source deliberately marks virtual parts produced. It does not
exercise Member 1's USB link, prove a full production batch, or replace the
operator UI. The real A adapter must call produced(ticket) only after its
matching completed production operation.

4. Capture Wireshark traffic with tcp.port == 5001. Preserve the four-byte
   length prefix, complete JSON messages, original IDs, part/batch/run/boot
   context, three distinct lifecycle events, and B's matching verdicts.
   TCP packet boundaries are not message boundaries.
5. Keep the JSONL log and local SQLite ledger. Part numbers persist between
   invocations using that database, so verify the rule using the actual
   returned numeric part_id, not an assumed reset to one. Do not share
   credential-bearing sdkconfig or firmware binaries.

## Hardware cases to record

- Runtime changes to duration/N/K and both PASS/FAIL results.
- Production faster/slower than inspection, with queue reservation/blocking.
  To test the other implemented full policy, select --full-policy fault.
- Disconnect during accepted inspection, then reconnect and retrieve its
  original cached result; one execution only.
- Same ID/same contents versus same ID/changed contents.
- Same part under a fresh job ID; no second inspection.
- Missing intermediate ACKs, missing completion, bounded no-response failure.
- Reboot B after acceptance; detect the new boot and refuse old job replay.
- Full history and stale/closed-run requests; retain accepted outcomes.

Controlled omission/blocked-TX switches in tests/application_host.c belong
only to the native host harness. They are not enabled in physical firmware;
use an identified network fault/proxy or a separately documented test build
for hardware fault injection and report exactly how the fault was applied.

## Software verification

On Windows with MSVC 2022 installed:

```powershell
Set-Location member2/esp32_b_inspection
python -B -m unittest discover -s tests -v
```

The suite compiles the actual C application/protocol/transport and exercises
it through real loopback TCP and the actual Python gateway. It covers
bounded recovery, missing ACKs/completion, independent execution despite
blocked sends, duplicates, busy configuration, history, malformed messages,
multiple runs, queue policies, reconciliation, and late conflicting verdicts.
Host clocks/socket/hash backends differ from ESP32; software PASS is not
radio, hardware timing, power-loss, or Wireshark evidence.

See [the message contract](member2-protocol.md) and
[local SDK setup](esp-idf-testing.md). Evidence summaries and the actual test
log are in member2/esp32_b_inspection/verification.

## Recovery API

For a running InspectionGateway, use reconcile(job_id), then explicitly
resume_after_reconciliation, or close_incomplete after fresh idle evidence.
None of those methods dispatches a replacement inspection automatically.

For a process restarted while B still has a run, inspect the SQLite events/
JSONL for its original boot, batch, run and job IDs. A new start is refused.
Use BClient.connect(), compare the recorded boot, select_run(original_batch,
original_run), and query(original_job_id). Review the target snapshot;
explicitly close only after resolving/archiving the old work and confirming
idle. If the boot changed, keep old outcomes uncertain rather than assigning
those old requests to the new boot.
