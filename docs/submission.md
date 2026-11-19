# Milestone 1 submission and report material

The official assignment is `reference/MCT431 Project Fall 26.pdf`; the original
team guide is a proposal. Milestone 1 is the working USB/TCP/HTTP/WebSocket
application. Formal multi-protocol benchmarking is deferred to Milestone 2.

## Package the current tree

From the repository root:

```powershell
.\.venv\Scripts\python.exe -B tools/package_submission.py
```

The command creates `submission/MCT431_Milestone1.zip` and a SHA256 sidecar.
The archive contains source/configuration inputs, one root README and one root
requirements.txt, the current documents, original assignment references, test
sources/fixtures, available evidence and verification records. A per-file hash
manifest is inside the ZIP. Git history stays in the development repository;
the archive excludes `.git`, local environments, build trees, caches, local
credential-bearing sdkconfig, machine-specific editor settings and its own ZIP.

The package is a source/evidence snapshot. It does not claim a finished report,
completed pending physical tests or possession of gateway-only log/database
files that have not yet been transferred. Packaging must not edit raw captures,
reports, measurements, logs or databases. Preserve the original raw files
separately when creating annotated excerpts or figures.

## Required report coverage

| Assignment item | Current source material / remaining work |
|---|---|
| Source and configuration | `gateway`, `stations`, `shared`, `operator_ui`, root dependency file and verification tools |
| Reproducible setup/test instructions | Root README and [Testing](testing.md) |
| Architecture/state diagrams | [Architecture](architecture.md), including two Mermaid diagrams |
| Message specifications | [Station protocol](station-protocol.md) and [operator API](operator-protocol.md) |
| Raw CSV measurements | Export from accepted original batch JSON reports; keep units and provenance |
| Annotated Wireshark and serial logs | Accepted raw PCAPs available; selected packet annotations and current A serial-frame review still needed |
| Comparison plots and interpretation | Export tools available; distinguish configured execution time from protocol/network latency |
| Justified protocol choice | Explain UART framing, custom TCP and HTTP/WebSocket responsibilities; do not claim unperformed M2 benchmarks |
| Specific contribution table | [Contributions](contributions.md), using recorded author identities |
| Full-batch live demonstration and explanation | Normal batches were reviewed; rehearse and demonstrate the actual integrated system |

## Current evidence and provenance

Use the accepted run table in [Testing](testing.md), not every old batch visible
in History. Wireshark packet numbers in existing review notes refer to their
original capture files. A TCP ACK alone does not prove application acceptance;
show matching original IDs in request, RECEIVED, ACCEPTED and COMPLETED/result.
Use B-generated verdicts and A's separate raw framed serial evidence.

The existing files in `Test_Cases/Report` are explicitly **earlier Batch 8
material**, not the accepted final sequence: `measurements.csv`,
`timing-comparison.png`, and `normal-b-tcp-annotated.pcapng`. Their source JSON
was deleted during the user's earlier evidence reset. They are retained unchanged
because they are measurements/figures, but must not be relabelled as Batch10-16
or treated as complete final-submission evidence. Generate current outputs into
a different output directory from the accepted JSON files instead.

Example export using accepted reports, without overwriting earlier assets:

```powershell
.\.venv\Scripts\python.exe -B tools/export_batch_measurements.py Test_Cases/Evidences/Final_Verification/T01_Normal/batch-10.json Test_Cases/Evidences/Final_Verification/T02_Queue_Wait/batch-11.json Test_Cases/Evidences/Final_Verification/T05_Paused_Settings_Change/batch-16.json --output submission/report-measurements
```

The exporter reads reports only; it does not contact hardware. CSV contains
original identities, frozen settings, device elapsed times, observed gateway
stage times and attempt/query counts. Missing ACK observations remain empty.
Monotonic gateway times are local to their gateway process, not wall-clock
timestamps to compare across independent boots.

A production/inspection execution-time plot mostly reflects the configured
software timers. It does not show that TCP is faster than USB. Paused batch
elapsed time includes the manual pause and must not be reported as uninterrupted
throughput. State the sample count, units, settings and interpretation for each
figure. The full protocol speed comparison belongs to Milestone 2.

## Final evidence collection

The available six reviewed cases and software logs are not a claim that every
pending failure scenario passed. Further physical tests are postponed until
report work is complete. Current-session `serial.local.jsonl` and
`gateway.sqlite3` still need a consistent stopped-session copy from the gateway.
Do not substitute the old contributor logs or JSON operation summaries for
actual current raw USB frame validation.

When creating the final report, use selected annotated figures and readable
tables. Keep full PCAP/serial/JSON/CSV/database files as supporting evidence;
do not paste pages of raw JSON or screenshots of database internals. All original
assignment references, licences and available raw evidence remain preserved.
