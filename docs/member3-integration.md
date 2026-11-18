# Member 3 integration review

Reviewed 2026-11-18 at origin/member3/operator-ui commit d1b8e69.
The branch is available locally and remotely; it has not been merged here.
The user's instruction is to preserve the screen's overall shape, interface,
colors and theme while freely adapting controls/content to the integrated
project. Hardware testing is deferred until UI integration is ready.

## Source review

Read index.html, cartoon.css, app.js, protocol.js, transport.js, README and
GATEWAY_HANDOFF. The visual baseline is Little Toy Works: cream panels,
butter-yellow configuration, powder-blue/pink stations, walnut outlines,
cat/puppy cards, station timers, queue, counters and command notebook.
Preserve those visual assets and layout identity. The supplied mock gateway
is standalone test infrastructure, not the integrated production gateway.

The official PDF requires four states and HTTP Start/Pause/Resume/Stop with
WebSocket status (VI, Milestone 1 items 3–5). It requires safe behavior on
disconnection/stale data (IX), but does not prescribe the exact operator
Pause/Stop policy below. The teammate handoff is a proposal, not authority
over the PDF or already-approved project decisions.

## Changes already implied by approved requirements

- Connect the existing screen to the actual authoritative asyncio gateway.
  No browser/mock verdict computation may stand in for B's result.
- Align inputs with the approved 1–64 run size, 1–600000 ms timings,
  positive uint32 part IDs, signed-int32 K, positive signed-int32 N and
  shared identifier limits. Existing proposed UI bounds differ.
- Add unresolved/isolated and unstarted/not-inspected reporting alongside
  unchanged confirmed PASS/FAIL counts; support automatic INCOMPLETE outcome.
- Add explicit lookup, guarded Continue remaining and incomplete closure
  using the agreed recovery rules. Clearing a visual notice never bypasses
  a gateway dispatch hold or establishes an unknown result.
- Keep a stale display visibly historical; separate UI connection health,
  A/B station health, command stages and batch outcome.
- Preserve bounded command attempts/windows/absolute lifetime across UI
  retries/reload. Current manual retry resets issued_at and can replenish
  attempts; current fixed 15 s completion timer cannot represent a graceful
  Stop while a long accepted job finishes. Adapt these to the shared rules.
- The current snapshot validator expects an assigned part_id for every
  requested target before production; the gateway allocates IDs when it
  reserves actual parts. Show unstarted target slots separately without
  fabricating station IDs for them.
- Start completion means configuration is confirmed and Running begins;
  it is separate from actual batch completion. Existing core already follows
  this sequence. Routine API/schema/visual details may be implemented directly.

## Proposed operator decisions — pending user response

1. Pause gates new production and new inspection immediately. Accepted work
   finishes independently; queued inventory is retained. Pause completes once
   both gates are established; the Paused screen can still show draining
   jobs. Resume uses the same batch after freshness/scope/recovery checks.
2. Stop gates new dispatch, lets accepted work finish, performs bounded lookup
   of uncertain outcomes and closes both old scopes. Preserve all known counts;
   classify remaining missing work INCOMPLETE automatically. Show stopping as
   pending control activity within the four states. If closure cannot be
   confirmed, retain Fault and explicit recovery rather than announce success.
3. Loss/staleness of the controlling operator connection requests a pause of
   new dispatch after a bounded configurable liveness window. Accepted work
   finishes. Fresh resynchronization plus explicit Resume is required; no
   automatic restart/resume on browser reconnection. Exact initial UI/gateway
   heartbeat numbers are engineering settings to verify in software/hardware.
4. Permit timing and N/K edits while Paused after both stations are idle.
   Apply through identified acknowledged configurations and require both
   confirmations before dependent work resumes. Future unaccepted jobs use
   the new settings; existing accepted records/results stay frozen. Keep the
   batch target, queue capacity and full policy fixed for the batch. Expose
   queue capacity and block/Fault selection for the next batch at configuration.

## User response and clarification

The user agreed to decisions 1, 3 and 4, with a request to clearly distinguish
an individual station job, remaining work in the same batch, and a new batch.
Pause and operator-link loss gate new dispatch; they do not cancel current
accepted jobs. Resume continues the same batch with the same identities and
retained counts. The user explicitly reaffirmed the recovery controls and
unresolved-part reporting.

Decision 2 (Stop) is still pending: the user asked what accepted work means
and requested a clearer explanation. In this one-active-job-per-station design,
it means the current accepted production job and current accepted inspection
job, not every requested part in the batch or queued inspection work. Already
sent requests with missing replies must also be reconciled/fenced, not assumed
unexecuted. Proposed Stop lets current jobs finish but does not dispatch their
next stages or the waiting queue. It ends the current batch after safe closure,
automatically INCOMPLETE if any target work is missing; another Start creates
a new batch with new part IDs, without silently carrying unfinished parts over.
No new batch may begin before prior-scope closure/restart fencing is established.

The PDF requires runtime-configurable examiner-assigned times and rule
parameters. It does not explicitly require edits during Pause: exposing such
edits is the user's approved extension within that runtime configuration model.
Do not describe the particular pause-edit workflow as a verbatim PDF mandate.

The user subsequently approved all four clarified decisions and directed
implementation. Stop is agreed: finish already accepted individual jobs,
safely close the old batch with retained totals and automatic incomplete
classification, then allow an explicit new Start. Operator-link loss pauses
new dispatch and requires explicit same-batch Resume after resynchronization.
The recovery controls remain required. Implementation now proceeds on main;
no further operator-policy decision is pending from this review.
