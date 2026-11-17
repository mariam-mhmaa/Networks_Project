# Command and job identifiers

Status updated 2026-11-18: the finalized origin-ID design is implemented for gateway–B and verified in software. Member 1's different ID/serial contract still needs separate integration agreement.

Consistency review: 2026-11-17. The confirmed rules in [job-lifecycle.md](job-lifecycle.md) apply to all command/job IDs. Recovery bounds, exact query/receiver-context fields, and crash durability remain open in [reliability-open-decisions.md](reliability-open-decisions.md).

## Purpose and scope

Give every command and job a stable, unique identity while keeping logs readable. This is a team design choice implementing official requirements VII and VIII; requirement IX additionally requires stale/restart handling that IDs alone do not provide.

The implemented B subsystem allocates batch IDs as BATCH-GW-full_UUID4 and positive uint32 part IDs from a durable SQLite counter that never resets between batches. A command/job ID remains distinct from batch ID, part ID, ATR sequence or production count. Full operator Start deduplication and Member 1 compatibility are separate integration work.

The separate batch_id field itself is now agreed (D009): preserve it on batch-scoped requests, responses, and status and validate it before effects/accounting. A retried Start must map to its existing batch rather than allocate another. Issuer/action counters do not reset when a new batch begins. Exact batch ID generation and part-number uniqueness are still open; adding batch context is not permission to silently reuse a supposedly unique full part identity.

## Fields and representation

- Commands carry `cmd_id`.
- Production and inspection jobs carry `job_id`.
- Keep an explicit action/type field and the relevant batch/part references. The complete ID is opaque to normal business logic; receivers do not choose actions by dissecting the prefix.
- Canonical ID shape: `ACTION-ISSUER-SESSION-COUNTER`.
- `ACTION` is an explicit, centrally defined prefix for the requested action. Initial prefixes: `START`, `PAUSE`, `RESUME`, `STOP`, `CFG`, `PROD`, and `INSP`. Final external message action names will be documented in the message contracts.
- `ISSUER` identifies the originating application role, initially `GW` or `OP`. It does not change when a message is forwarded.
- `SESSION` is a full random UUID version 4, rendered as 32 lowercase hexadecimal characters, generated once when an issuing application initializes its ID generator. This provides practical uniqueness across independent applications and restarts, with a negligible rather than mathematically impossible collision probability. Short labels such as `S8` are explanatory aliases only, never substitutes for the canonical ID.
- `COUNTER` is a positive decimal sequence starting at 1, independent for each action within the issuer session. Six-digit padding is a minimum display width, not a maximum or permission to wrap. Do not reset counters between batches within the same session or reuse a counter within its action/session.

Example: `INSP-GW-7eaf4ce379f4496d95f4b932ec02a615-000001`.

## Generation and ownership

Use one small ID-generator component per issuing application. It owns the session token and action-counter mapping. The gateway core requests IDs for new operations; serial, TCP, and web adapters do not independently construct or replace them.

The operator application creates command IDs before its first transmission, so an HTTP retry can retain its original command identity. Generate IDs at the operation's origin. ESP32 replies echo the original command/job ID.

If generator state is lost, create a fresh session for new operations. Previously issued operations retain their existing IDs if recovered. If an outstanding operation's identity cannot be recovered, treat its outcome as uncertain; do not silently create a replacement request and assume duplicate execution is prevented. Restart and recovery policy remains a separate decision.

## Identity invariants

1. A new logical operation gets a new ID. Production and inspection of the same part are different jobs and have different job IDs.
2. Every retransmission of the same operation retains its complete original ID and semantic request contents. Transport-attempt metadata may change separately.
3. Direct acceptance, rejection, status, and completion responses reference the original request ID. A completion also carries the explicit result and relevant part/batch references. A status-query response additionally correlates with its own query and separately identifies the target operation; query identity must not replace the original target cmd_id/job_id. Exact query schema remains open.
4. Preserve an existing operation's ID across protocol translation and forwarding. A newly derived operation, such as configuring B because Start was accepted, is a separate command with its own identity and a recorded relationship to the triggering command; it is not a renamed transport copy of Start.
5. A receiver must not re-execute a duplicate. If the same ID arrives with different action or semantic request contents, reject and log the conflict rather than treating it as new work. Duplicate-status/result retention and restart behavior remain to be designed.
6. Action-counter values are not used to calculate produced or inspected totals. They count issued operations of that action, including those later rejected or aborted. Retrying does not consume a new operation ID.
7. An accepted job executes and its original-ID completion is promptly published/cached even if the gateway misses both intermediate ACKs. A later valid result establishes prior facts without inventing missing ACK timestamps.
8. Issuer session identifies the creator's ID-generator lifetime. It is not receiver boot identity, batch identity, or proof that duplicate history survives a device restart; that requires the separately agreed O04 mechanism.

## Modularity and protocol boundaries

The generator centralizes the naming scheme; duplicate handling compares complete IDs, and routing uses explicit message fields. This keeps the scheme out of transport-specific code. Account for full ID lengths in serial/TCP payload bounds when finalizing message contracts. A later protocol must preserve the canonical identity, using an agreed lossless representation if necessary; do not silently truncate or replace it with an unrelated transport sequence.

## Verification still required

- Independent action counters and consecutive new IDs.
- Different sessions and issuers do not accidentally reuse IDs in test scenarios.
- Retries and all related replies retain the original ID.
- Translation preserves IDs and complete semantic request contents.
- Same-ID/different-request conflicts are rejected.
- Duplicate execution and result counting are prevented, including uncertain/restart cases under the eventual recovery policy.
- Full ID representation fits each agreed message format and maximum payload.

No checks above have been claimed as passed.

## Sources

- Official project PDF, page 2 requirement VII, page 3 requirements VIII-IX, and page 5 Milestone 1 item 5.
- Python UUID documentation: https://docs.python.org/3/library/uuid.html
