## Historical API review before this approved implementation

| Question | Assessment |
| --- | --- |
| 1. Separate unresolved work from station unavailability? | YES in core data; PARTIAL in the public run wrapper |
| 2. Read-only status without resending exhausted work? | YES at protocol/low-level client; no dedicated run-level status helper |
| 3. Record validated post-deadline completion once, without resuming? | PARTIAL before the deadline; GAP after the operation has stopped |
| 4. Safely submit different work after explicit health/idle check? | Building blocks exist; GAP in a supported high-level continuation gate |

### 1 Operation outcome versus station health

RetryController.execute distinguishes COMPLETED, REJECTED, FAULT and
UNRESOLVED. Its ledger keeps the original outcome/deadlines and prevents
re-entry from granting extra transmissions. SessionGuard separately maintains
available, fault, intended boot_id, observed_boot_id and the monotonic last
valid heartbeat. Therefore an UNRESOLVED operation can coexist with a healthy
same-session station; there is no rule equating timeout confirmation with
station failure or with proof that work did not occur.

However, RetryStopped inherits SessionFault, and ProductionRun.produce catches
all these cases together and clears configured/started. Its configure method
also disarms before acting. This is a conservative submission gate, not batch
abort behavior. A generic `except SessionFault` cannot distinguish the cases
without inspecting RetryStopped.result and the separate SessionGuard state.
The wrapper does not directly express the agreed isolated-unresolved versus
unavailable-station decision.

Evidence: pc_test/retry.py (finish/ledger/terminal outcomes),
pc_test/session.py (SessionGuard), pc_test/gateway_client.py (RetryStopped and
ProductionRun.produce). No batch implementation exists to inspect or change.

### 2 Existing read-only status path

GET_STATUS requires no boot_id or operation number and does not configure,
produce or modify accepted history. Client.send can send it with
bind_session=False, while Receiver tracks its outstanding ATR seq. The response
is still validated and checked against the already-bound session by normal
Client.next processing. A different boot must fault the old run, never be
silently adopted to make continuation possible.

Do not call execute on the exhausted production request to obtain status.
Do not call connect_or_recover merely as a status refresh: it creates a new
client/guard and changes run permissions as part of explicit recovery.

ProductionRun.observe pumps observations and returns availability/fault/boot
information. It does NOT return a correlated current state/active operation/
configuration snapshot, nor does it drain and reconcile pending application
completions. The existing status-query code inside configure expects its next
response to be STATUS; an intervening late application response can make that
expectation fail. A public read-only helper needs a shared response dispatcher
that preserves such intervening evidence instead of dropping it.

### 3 Late-completion behavior and its limit

While execute is still waiting within its absolute deadline, it accepts a
matching original or replayed completion, checks request identity/allowed ATR
seqs and credits its completion set once. Known-completed re-entry returns a
local result without transmitting or double-counting. These behaviors already
work and were tested in Step 5C.

AFTER execute has returned UNRESOLVED, its first ledger result remains fixed.
With a healthy guard, calling execute again returns that stopped result without
sending or reading for a late confirmation. A current session fault can instead
be reported on re-entry, but it does not overwrite the original saved UNRESOLVED
outcome or restore its budget. Receiver can validate a later frame and queue it.
ProductionRun.observe leaves application frames in Receiver.pending; a later
different operation may instead quarantine the old response in its trace.
Neither path updates a dedicated late-evidence record or credits that part's
production confirmation. completion_count also includes configuration operations
and is NOT a produced-part or inspected-part count.

Thus frame/CRC validation and queuing already exist, but an exposed passive
late-completion reconciliation API does not. Do not treat a queued/quarantined
frame as a fully validated part result merely because its JSON parsed: it also
needs the original session/op/IDs, payload semantics and allowed ATR seq.

Proposed accounting distinction, for approval before implementation: preserve
the immutable retry attempt outcome UNRESOLVED and spent budget, while storing
validated late station evidence separately. A future gateway could then
recognize that a part is confirmed produced once without rewriting the retry
history, retransmitting, clearing a fault or automatically resuming. Confirmed
part versus remaining-unresolved-part accounting must be distinct from the
count of retry records that ended UNRESOLVED. No such counters are added here.

Old/different-boot frames must not clear restart faults or be credited to the
current session automatically. Retain them, if needed, as quarantined historical
evidence for explicit review; this proposal does not weaken the boot fence.

### 4 Different work after an isolated unresolved operation

At the low level, RetryController can execute a different operation when its
existing SessionGuard permits sends. GET_STATUS and fresh heartbeats provide
the station facts needed for an explicit gateway decision. Firmware still
rejects new work while busy. No existing check guarantees that a newly supplied
op_no/job_id represents a genuinely DIFFERENT part: using new IDs for the same
batch_id/part_id can bypass that logical distinction. The future gateway must
retain an immutable part-to-operation association; station idle status cannot
provide that association or turn an unresolved part into new work.

The current ProductionRun high-level API does not expose an explicit
assess-and-authorize-different-work path after UNRESOLVED. It disarms, and
start requires configuration permission. Reconfiguration/start are possible
explicit actions, but are not the requested read-only same-session health/
idle continuation check. Do not toggle flags, replace the guard/ledger, reset
the station, or recreate old work as a workaround.

An eventual continuation gate must require all of:

1. The originally intended boot remains the current boot.
2. A fresh valid heartbeat establishes available=true, with no latched session
   fault. available=true alone is insufficient after same-session recovery.
3. A correlated read-only STATUS confirms IDLE, active_op_no=null and the
   expected applied configuration. A status snapshot alone cannot refresh
   heartbeat liveness.
4. The gateway explicitly authorizes a genuinely different part/operation,
   preserving the unresolved record and its exhausted budget. An accepted
   high-water mark constrains the new number; it is not a completion count.

This is an eligibility check at a point in time, not a guarantee against a
later communication failure/state change. Continue monitoring, retain firmware
BUSY/session rejection handling, and stop new production if health becomes
uncertain. A latched heartbeat/restart fault still requires the established
explicit recovery flow; reconnecting alone never resumes it.

## Historical proposal (subsequently approved and implemented above)

No firmware or wire-interface change appears necessary. Proposed follow-up:

- Add an explicit operation-stop category/result at the high-level API so
  isolated uncertainty is distinguishable from link/session failure without
  interpreting a generic SessionFault as batch abort.
- Add a public correlated read_status helper using the EXISTING guard and
  GET_STATUS, plus a single dispatcher for status and application responses.
- Add passive late-evidence reconciliation against retained requests/allowed
  sequences, with deduplication. Preserve stopped retry outcomes/budgets and
  do not resume a run as a consequence of evidence arrival.
- Add an explicit same-session health/idle continuation assessment and
  authorization for different work. Keep liveness/restart faults latched and
  retain the ledger. Do not implement batch scheduling or inspection here.

Names/signatures and the late-evidence/accounting distinction above are
proposals, not existing APIs. Implementation requires user approval. Batch
part identity tracking, inspection selection, operator abort and incomplete
batch reporting remain responsibilities for later gateway management.

## Historical static-review verification boundary

This review is static inspection only. No implementation files were edited;
no tests, serial access, resets, firmware builds or flashing were performed.
Previous Step 5C PASS results remain historical evidence, not verification of
the proposed follow-up. COM3 was not opened. Physical unplug/replug remains
NOT RUN.

