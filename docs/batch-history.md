# Batch history and readable evidence

The live dashboard shows the current/latest batch. Open **Batch history** to
select an earlier batch. This is read-only: it does not pause, resume or restart
anything. Every batch keeps its own parts, confirmed PASS/FAIL totals and unknown
outcomes. No automatic report file is created after a batch.

The gateway keeps application history and display-name mappings in the existing
`gateway.sqlite3`. Keep using that same file across gateway updates. Earlier
request/outcome events are read into History, including journals created before
this update. A missing old timestamp stays missing. An interrupted/open batch
does not become Completed just because the gateway restarted.

Select a batch in History, then click **Download batch report** only when you
want a JSON file, such as `batch-1.json`. This is the single batch download;
it works for historical batches even when the live dashboard has no active
batch after a restart. It stays disabled while no valid report is selected.
The browser chooses the download folder; the gateway does not create a report
directory or one file per run. The downloaded JSON is formatted with indentation.

## What to look for

- Batch outcome and totals: Completed requires all target inspections; an
  Incomplete batch still shows every confirmed PASS and FAIL.
- Part IDs: production and inspection must refer to the same original part.
- Operations: production, inspection, configuration, closure and recovery queries
  have separate identities. COMPLETED inspection can have a FAIL verdict.
- Received, Accepted, Completed: these are actual gateway observations. The
  readable table shows milliseconds from the first observed stage of each
  operation. `Not observed`/JSON null means no matching original ACK was observed.
  A later valid response can establish an earlier stage without inventing an ACK
  timestamp. Technical evidence names what established those stages.
- Attempts / queries: original-request attempts and bounded read-only recovery
  queries are distinct. Query ACK times belong to the query, not the original job.
- On-screen Details use labelled fields: short ID, station, part, settings
  revision, applied settings, device execution time, stage observations and
  recovery information. No raw JSON, full protocol IDs or boot UUIDs are exposed
  in the GUI. The downloadable technical report retains the original requests,
  validated results, full identities and controller evidence for correlation.
  Unvalidated wire observations alone never become a confirmed verdict.

Short labels such as `PROD-GW-S01-5` and `Batch 1` are for reading. The full IDs
remain unchanged in messages, the database and downloaded technical evidence.
Only short labels appear in the GUI, including Details. Session aliases are allocated in SQLite and are not reused for
different sessions when the gateway restarts with the same database. Copy the
database along with history when moving to another gateway; a new database has
its own display-name namespace.

The table names each action and station explicitly: Start batch, Apply settings
for A or B, Produce part, Inspect part, Close station batch, and any recovery
queries. Each row has its own clock. The Timing starts at column identifies
which observed stage is +0 ms. This is not time since request submission or
batch start. A row containing only Completed at +0 ms does not imply instant
execution. Device-reported execution time appears separately in Details.
Newer page/Older page only navigate groups of 20 batches, and are hidden if all
saved batches fit on one page. The dropdown selects an individual batch.

## Which output to use

For ordinary test review, start with the GUI totals and `batch-N.json` from
History. Its top-level `batch` and `counts` give the summary; `parts` lists the
individual outcomes; `operations` contains A/B requests, acknowledgements,
results and retry/query evidence. `controls` contains operator commands.
Full identities in this technical file allow matching against raw captures;
the GUI displays their persistent short aliases.

The old three buttons had different targets: Download log exported only recent
browser messages; Download selected batch exported the selected historical batch;
Download batch evidence exported the live dashboard batch. The last two used the
same report format, but the live-batch button silently did nothing when no live
batch existed after a gateway restart. They are replaced by the single History
download. The optional **Download browser messages** remains inside
**Troubleshooting: browser messages**, writing `operator-browser-log.json`.
It is useful for UI connection problems, not the main device/batch evidence.

## Three useful evidence sources

1. `gateway.sqlite3`: application requests, stage observations, validated outcomes,
   retries, controls and compact batch views. Reports exclude periodic heartbeats.
2. `serial.local.jsonl`: raw A serial TX/RX with timestamps. RX is a byte chunk;
   a TX record confirms a write, not a device acknowledgement. This file can
   contain several batches; there is no need to create one for every batch.
3. Wireshark capture: actual TCP/HTTP/WebSocket evidence requested by the PDF.
   A JSON report does not replace a packet capture, and packet capture does not
   replace the gateway's application accounting.

A communicates with the gateway through USB serial. Its raw binary frames are
hex-encoded in `serial.local.jsonl` on the gateway PC, alongside the repository's
`gateway.sqlite3`. The assistant can decode those frames when needed; the
operator does not have to read hex. A's decoded application facts also appear
in the database and exported batch report.

B communicates with the gateway through Wi-Fi TCP port 5001. Its decoded
requests, acknowledgements and inspection results are in the same database and
batch report, marked station B. There is no raw B serial inspection trace:
its USB cable supplies power during normal operation. USB monitor startup/Wi-Fi
diagnostics are separate and are not currently saved automatically. B's raw
network evidence will be a Wireshark `.pcapng` file created during the relevant
capture test; no such new file is created merely by launching the gateway.

## Confirm restarted A/B

These controls were called Recover restarted A/B. They do not reboot or reflash
an ESP, restart a batch or reproduce a part. They explicitly verify a detected
different boot and fresh idle status before replacing that station's old client.
Between closed batches, successful confirmation allows a new Start. If a station
restarted during an open batch, old uncertain results stay unresolved and the
old batch must be explicitly ended before a new batch starts. Use the controls
only when the GUI reports the relevant restart and enables them.

The old `gateway.local.jsonl` remains useful for the two tests already performed.
Keep it. It contains combined decoded/raw traffic from the previous version.
The new launcher defaults to a separate raw serial trace. `--events` remains an
alias of `--serial-trace` so an old launch command still works, but a new file is
clearer than mixing the two formats. Capture/history errors appear in status;
they do not manufacture an operation outcome.

## Updating the gateway PC

Do this with the workshop idle. If a batch is active, finish it or use the GUI's
Stop workflow first. Wait for closure before Ctrl+C in the gateway terminal.

From the repository root on the gateway PC:

```powershell
git switch main
git pull --ff-only
.\.venv\Scripts\python.exe -B -m gateway.operator COM3 172.20.10.3 --host 172.20.10.2 --port 8080 --inspection-port 5001 --state-file gateway.sqlite3 --serial-trace serial.local.jsonl
```

Keep the same `gateway.sqlite3`; do not replace it with this operator PC's file.
The addresses above are the last confirmed phone-hotspot addresses; check them
again if the hotspot has reassigned them. Refresh the operator browser with
Ctrl+F5 after updating. No ESP32 reflash is needed for these changes.

## Transferring the old log

Git push/pull is for sharing the code; this local runtime log is ignored by Git.
Use an ordinary file transfer instead. With the old gateway process stopped, in
the gateway repository root you can make a compressed copy:

```powershell
Compress-Archive -LiteralPath .\gateway.local.jsonl -DestinationPath .\gateway-log.zip -Force
```

Keep the original. Transfer the ZIP to the operator PC and extract it into
`Test_Cases\Evidences`, alongside `batch-evidence.json`. The filename is
`gateway.local.jsonl`: a dot before `jsonl`, ending with a lowercase letter L.
The assistant can read that local file directly once it is there. A stopped
gateway's `gateway.sqlite3` can also be copied for historical review; do not copy
a live database casually or overwrite the gateway's original state file.

## Limits

The journal and aliases survive restarts; running work is never restored or
replayed automatically. History reads do not control stations. Existing raw
captures and this update cannot reconstruct transport bytes or timestamps that
were never recorded. List pages contain 20 batches by default (maximum 100 via
API). History projection is incremental in memory and replays the durable journal
when the service starts; large long-term archives would need separate scaling
work beyond this bounded Milestone 1 workshop.
