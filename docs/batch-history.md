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

Click **Download selected batch** only when you want a JSON file, such as
`batch-1.json`. Download batch evidence in the command notebook downloads the
current batch using the same report format. The browser chooses the download
folder; the gateway does not create a report directory or one file per run.

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
- Technical details contain the full original identity, frozen request, validated
  result and controller evidence. Unvalidated wire observations alone never
  become a confirmed verdict.

Short labels such as `PROD-GW-S01-5` and `Batch 1` are for reading. The full IDs
remain unchanged in messages and technical evidence. Expand **Technical details**
to copy a full ID. Session aliases are allocated in SQLite and are not reused for
different sessions when the gateway restarts with the same database. Copy the
database along with history when moving to another gateway; a new database has
its own display-name namespace.

## Three useful evidence sources

1. `gateway.sqlite3`: application requests, stage observations, validated outcomes,
   retries, controls and compact batch views. Reports exclude periodic heartbeats.
2. `serial.local.jsonl`: raw A serial TX/RX with timestamps. RX is a byte chunk;
   a TX record confirms a write, not a device acknowledgement. This file can
   contain several batches; there is no need to create one for every batch.
3. Wireshark capture: actual TCP/HTTP/WebSocket evidence requested by the PDF.
   A JSON report does not replace a packet capture, and packet capture does not
   replace the gateway's application accounting.

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
