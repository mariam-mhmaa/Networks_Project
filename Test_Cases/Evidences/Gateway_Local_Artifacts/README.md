# Gateway local artifacts

These are byte-for-byte copies of the files found at the repository root on
2026-11-19. The originals remain there for local use. The two files have
different last-modified times, so they are preserved as separate artifacts;
do not assume they form one simultaneous snapshot.

| File | Purpose | SHA-256 |
| --- | --- | --- |
| `gateway.local.jsonl` | Gateway event log; not the raw ESP32 A serial trace | `63a0446ea96d59d06e8443e0c4d08c68db31b4a70a0fcd5f70d3f67df59dba18` |
| `gateway.sqlite3` | Durable gateway journal and batch history | `2a30c015e94d299d205794649da68ae1f5b2a4698e661c73236d0fbed7dba8d2` |

The SQLite copy passed `PRAGMA integrity_check` when collected. The JSONL copy
contained 33,397 parseable records. Correlate batch identifiers and times with
the accepted case reports before citing these files as evidence for a run.
