# Milestone 1 report evidence in progress

These are real application measurements from T02 / Batch 8, not formal
Milestone 2 protocol benchmark results. Further state/queue/recovery tests and
the current A raw serial review are still pending.

## Files and interpretation

- `measurements.csv`: one row per production or inspection job, copied from
  `../Evidences/T02_Normal_Capture/batch-8.json`. Eight rows: four A jobs and
  four B jobs. Includes original IDs, settings, actual gateway-observed stage
  timestamps, device-reported execution duration and attempt/query counts.
  Gateway timestamps are monotonic seconds within that gateway process, not
  wall-clock times. Missing observations remain empty; clocks are not mixed.
- `timing-comparison.png`: mean device-reported production versus inspection
  execution time in milliseconds, with four completed jobs per station.
  A's mean is 2000 ms; B's mean is 1000.5 ms. These closely match the configured
  2000 ms and 1000 ms timers. Inspection takes roughly half the production time
  under these settings; the plot does not establish that TCP is faster than
  serial. It excludes queue wait, network delay and configuration/closure time.
  Batch elapsed time, separately measured by the gateway, was 11172 ms.
- `normal-b-tcp-annotated.pcapng`: a derived 89-packet excerpt with comments on
  21 packets. It preserves original packet bytes/timestamps from B's stream,
  original-capture relative seconds 1518-1532. Original frame numbers are in
  the comments; excerpt frame numbers differ. The original is retained at
  `../Evidences/T02_Normal_Capture/T02_Normal_Capture.pcapng` and is not modified.
  Source SHA256 and extraction scope are also recorded inside the excerpt.
  This excerpt covers B TCP, not HTTP/WebSocket or A USB serial.

In Wireshark, the display filter `frame.comment` selects annotated packets.
Right-click a packet and use Follow > TCP Stream; choose ASCII. Read the JSON
message types and IDs, not the TCP ACK flag. Part 33's INSPECT, RECEIVED,
ACCEPTED and COMPLETED/PASS packets are excerpt frames 19, 22, 24 and 30.
The four-byte length prefix appears before each JSON message. Different
application messages may share one TCP packet.

The original capture also reveals a startup presentation issue: pending
configuration was temporarily published as Fault, with mixed previous/new
batch counts. Preserve it as pre-fix evidence. The software correction keeps
the last coherent idle batch view while Start is pending, switches to the new
batch after both stations confirm settings, and still exposes real failures
as Fault. Software verification passed 28 backend and 9 frontend checks;
physical verification of the correction is pending. No ESP firmware changed.

## Reproduce the CSV and plot on the operator PC

From the repository root, using Python with the report dependencies installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tools/requirements-report.txt
.\.venv\Scripts\python.exe -B tools/export_batch_measurements.py Test_Cases/Evidences/T02_Normal_Capture/batch-8.json --output Test_Cases/Report
```

The exporter reads the source report and replaces the two generated output
files. It does not contact hardware, change the application, or edit evidence.
Additional reports can be passed before `--output` to compare multiple batches
in the same two files. Repeated input batch IDs are rejected.

For submission, use selected annotated packet/GUI images, the plot and its
written interpretation in the report. Retain raw PCAP/serial logs, reports and
CSV as supporting files. The general PDF checklist still requires diagrams,
message specifications, reproducible instructions, protocol rationale and a
specific-task contribution table; these assets alone do not complete it.
