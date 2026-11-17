# Recovery and subsequent batch proposal

Date: 2026-11-17.

Status: Clarification for the unresolved-operation planning question, not an approved implementation policy. The user asked what recovery would do and how it affects later batches; that question is not a Yes/No approval. The exact mechanisms remain O01/O03/O04/O05 in reliability-open-decisions.md.

## Meaning of recovery

First establish trustworthy information about the original job and station state. The initial recovery work is observation: restore transport if necessary, verify receiver boot identity/liveness, and perform read-only operation/result queries. It does not start new manufacturing, assign a new ID to uncertain old work, reset/reflash automatically, or reset the original deadlines/retry budget.

Automatic recovery already occurs within the agreed bounded attempt/response/absolute limits. Explicit operator recovery is the procedure after those limits are exhausted or a device fault is latched. Any additional diagnostic exchange is separately bounded and recorded as reconciliation, not a renewed automatic execution retry allowance for the stopped operation.

## Proposed behavior while unresolved

After the agreed automatic limits are exhausted, stop dispatching new production and inspection jobs and show Fault with the affected operation and an explicit uncertainty reason. Preserve queued parts, original IDs, confirmed results, counters, and immutable timeout/audit records. Already accepted ESP32 work may still finish and must promptly publish/cache its outcome independently of gateway ACK reception. Fault does not imply physical cancellation.

Do not inspect an uncertain-produced part without actual production-completion evidence. Do not reconstruct a missing inspection verdict on the gateway, infer it from settings/status, or label uncertainty FAIL. B must provide the verdict.

## Recovery outcomes

| Finding | Current batch | Next batch |
| --- | --- | --- |
| Same receiver boot; cached matching result available | Reconcile once with provenance; retain original timeout record. Explicit resume may be permitted after all unresolved outcomes, queue/configuration consistency, and device readiness checks pass. | Finish/explicitly close the current batch first; new work must not overlap an unclosed old run. |
| Same boot; original operation still running | Observe only inside a separate finite reconciliation allowance. Progress does not restart the old execution deadline. Remain stopped if unresolved. | Block start while old work is still active or old execution requests remain valid. |
| Receiver reboot/history lost or result permanently unavailable | Retain the old part/job as uncertain and the batch incomplete. Recommend explicit abort/closure instead of rerunning that uncertain part. | Permit a fresh batch only after a safe transition establishes no active old work, invalidates old execution requests, confirms fresh device context, and applies verified new settings. |

Resume of a retained batch is a candidate policy, not already approved. If all its target work is later conclusively resolved, final reporting must still preserve the recovery history and comply with the agreed late-result accounting policy. Never silently rewrite the original operation timeout as though it succeeded on time.

## Isolation of a following batch

Assign a fresh batch identity. Keep old queued/active/uncertain records in the old batch's history; never silently transfer them or recreate their logical operation with new IDs. Validate every incoming result against the original job, part, batch, device context, and freshness policy before accounting.

Confirmed IDLE alone is insufficient: a delayed old execution request must not become runnable after the next Start. The transition needs the agreed receiver run/session or sequencing protection, and confirmed quiescence before new work. A's current boot/high-water design is relevant, but the cross-device transition and B behavior must be explicitly specified and tested.

After the new batch starts, old completions are old-batch audit/reconciliation evidence only. They never increase the new batch's counts or automatically resume either run. A previous incomplete batch does not permanently prohibit future batches once the safe transition has been established.

## Tradeoff and recommendation

Stopping new dispatch reduces availability while an outcome is uncertain, but keeps the M1 queue/accounting/recovery behavior explicit. The alternative in Member 1's handoff permits expressly authorized different work after fresh same-boot idle checks, while retaining uncertainty; it is not inherently forbidden by the PDF, but requires additional scheduler/cache/freshness/closed-run rules.

Recommendation for discussion: stop new dispatch after bounded recovery exhaustion; read-only reconciliation first; explicitly resume only a demonstrably consistent retained batch, otherwise close it as incomplete and establish a safe fresh-run transition. Do not implement this until the user answers the policy question and the required mechanism details are agreed.
