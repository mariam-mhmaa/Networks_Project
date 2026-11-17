# ESP32 B integration decisions

Date: 2026-11-17.

Status: Focused discussion in normal chat at the user's request. Completion of B is authorized; the concrete choices below remain recommendations until agreed. No firmware/application change or branch merge is included in this documentation update.

## Current source

Reviewed origin/member2/inspection-b at fb17631f09e54f77d37c0aae5f6575031ae3c6af after fetching updates. The ESP-IDF/C project configures Wi-Fi and reports its address; it does not implement TCP, inspection, rule configuration, or lifecycle/result recovery. Retain its project/Wi-Fi foundation while adding the approved behavior.

## First decisions to settle

Integration network is also a joint decision: recommend the gateway PC's hotspot as the official brief's default, subject to verifying the actual PC supports it and B can connect. A suitable small router is the documented alternative. Keep Wi-Fi credentials configurable; the current iPhone-hotspot test is evidence of association/IP acquisition, not proof of the final integration network or peer TCP reachability. Do not hard-code the historical address 172.20.10.3. No hotspot/security setting is changed by this proposal.

1. B listens as a TCP server; the gateway connects as its client. Recommend this arrangement: the gateway controls connection/recovery timing and B need not be configured with a changing gateway application address. Use one active gateway control connection; a new connection must not silently replace an active controller. B remains a Wi-Fi station while acting as a TCP server; these are different layers. Gateway-side B address/port are configuration, not hard-coded claims about the current hotspot address.
2. Use a four-byte unsigned big-endian length prefix followed by UTF-8 JSON. The length counts JSON bytes only, excluding the prefix. Recommend a bounded maximum of 1024 JSON bytes for the production-control interface, subject to validation against final schemas/IDs. Accumulate partial reads and parse back-to-back frames. A recv call is not a message boundary; enforce limits before allocating/reading an oversized payload.
3. At most one active inspection job on B; the waiting inspection queue belongs to the gateway. Recommend rejecting a distinct extra job as BUSY before acceptance instead of hiding another accepted queue on B. Exact rejection caching/reissue semantics remain open. Duplicate existing jobs report existing state/result rather than become new jobs. Status handling and allowed controls remain responsive during inspection. A and B can work concurrently on different parts.

The server role, four-byte size/JSON representation, production payload bound, and single-job policy are team choices. The official M1 requirement mandates TCP with length-prefix framing, but does not prescribe these particular field sizes, role, encoding, or queue placement details.

## Next contract topics after those choices

- Configure inspection time and deterministic rule parameters at runtime; agree exact rule, integer ranges, application/configuration version, and behavior when settings change around active work. Never calculate production verdicts on the gateway.
- Agree full part identity and its numeric rule input before freezing the inspection-request schema. Preserve original job/batch/part identity through request, acceptance, result, cache, and query.
- Settle receipt registration O02 and one authoritative local operation record. The already approved R01-R10 apply; do not reopen them as optional B behavior.
- Implement independent accepted execution, prompt cache-before-publication of completion, and explicit technical failure outcomes distinct from FAIL product verdicts. Do not block inspection progress on ACK transmission or gateway receipt.
- Agree operation-specific read-only query, boot/active-run context, cache capacity/retention, and reconnect behavior. A TCP reconnect is not a reboot and cannot renew operation IDs/deadlines or automatically rerun a job.
- Define deadline anchors, numeric limits, response windows, absolute horizon, and late-result accounting with the gateway controller. One sender owns application recovery; no competing automatic receiver retry loop is introduced silently.
- Start with a standalone PC test client and simulated gateway-side tests, then validate TCP reachability and real functional behavior. Wi-Fi association/IP acquisition alone is not proof of a usable peer TCP connection. Keep credentials out of source and shared artifacts.

## Proposed first functional checkpoint

Once the required contracts are agreed: B accepts a configured TCP connection, receives a runtime configuration, accepts one identified inspection job, remains responsive while its timer runs, and publishes/caches the matching B-calculated result. Failure tests and batch integration follow; the checkpoint alone is not full M1 compliance.

Other planning questions about Pause, Stop, and unresolved-operation recovery remain open unless explicitly answered. Discuss choices in normal chat now; the user can ask questions or suggest alternatives before approval.
