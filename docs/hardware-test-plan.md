# Milestone 1 hardware tests and report evidence

This checklist is a plan and evidence index, not a claim that every case passed.
Run one case at a time. Matching expected results permits moving to the next
assigned case; a mismatch, unexpected Fault, missing evidence or uncertain work
requires review before another case. Only instructions explicitly assigned in
the chat are ready for execution. Timing limits are hardware observations to
review against the agreed controller profile, not a reason to silently widen it.

## Evidence workflow

- Keep one folder per named case under `Test_Cases/Evidences`, ultimately on the
  operator PC. Use `T02_normal_capture` for the next captured normal batch.
- Save raw packet captures during the case. Start before runtime configuration
  and Start, keep recording through final acknowledgements and closure, then
  stop and save `capture.pcapng`. Capture on the gateway Wi-Fi interface with
  `tcp port 5001 or tcp port 8080`. Keep the raw capture even after adding
  annotations; screenshots alone cannot replace it.
- For the first captured normal case, take `01-settings.png` before Start,
  `02-final-gui.png` after Idle/completion, and `03-history.png` showing the
  selected batch, totals and representative A/B acknowledgement rows.
- For subsequent cases, save `final-gui.png`; add an `event.png` while the
  defining condition is visible (queue full, Paused, Fault, unresolved result).
  Configuration changes need before/after settings evidence. Do not capture
  every animation frame or every settings field individually.
- Download the relevant `batch-N.json` into that case's folder. If a case tests
  rejected input without creating a batch, save its rejection evidence instead
  of inventing a batch report.
- Save Wireshark screenshots from the retained `.pcapng` after the case, using
  exact packets/streams identified during review. The normal-capture report
  needs runtime B configuration and its acknowledgement, plus an inspection
  request and B-generated verdict with the same original ID. Include HTTP
  command/WebSocket evidence where it substantiates the case. TCP ACK alone
  does not establish application acceptance or job completion.
- A's `serial.local.jsonl` and `gateway.sqlite3` remain on the gateway PC and
  span cases. Preserve a stopped-session copy at the end and index cases by
  batch ID/time. Do not repeatedly duplicate the whole serial file for every
  batch. Do not overwrite/delete the gateway's active database.
- At least the normal end-to-end case and selected fault/recovery cases need
  network captures. GUI-only invalid-input checks do not each need a PCAP.
  Decide the evidence needed before assigning each case.
- Annotate packet screenshots and assemble the report after tests; capture raw
  packets and transient GUI states now. Previously uncaptured packets cannot
  be reconstructed. Old normal tests remain functional evidence; T02 provides
  deliberately captured normal-operation protocol evidence.

## Case index

| Case | Purpose | Status / evidence |
|---|---|---|
| T01 | Normal batch after UI update: 4 parts, production 2 s, inspection 1 s, N=2, K=0, queue=2, block | Functional PASS verified read-only against gateway API: Batch 7, parts 29-32, 4 produced/inspected, 2 PASS/2 FAIL, zero unresolved/unstarted/not inspected. All eight jobs have three observed stages, one request attempt, zero queries. Report saved as `Test_Cases/Evidences/T01_normal/batch-7.json`. GUI screenshot not yet collected; no Wireshark capture for this run. |
| T02 | Full normal batch with deliberate TCP/HTTP/WS and serial evidence | Batch 8 processing/results PASS: parts 33-36, 4 produced/inspected, 2 PASS/2 FAIL, no missing work. All 12 station operations have three actually observed stages, one request attempt and zero recovery queries. B's six request/response exchanges match the report exactly in the raw capture. STARTUP STATUS ISSUE: configuration waiting is published as Fault, with briefly mixed old/new batch counters. Not a clean overall case pass until corrected/rechecked. History screenshot, annotated packet pictures and eventual A raw-serial review remain pending. |
| T03 | Consecutive batches, distinct identities and preserved History | Pending. Confirm each batch's actual totals independently. |
| T04 | Production faster than inspection, smallest queue, Wait for space | Pending. Must show bounded queue and automatic continuation of same target; no loss/duplicate/fault. |
| T05 | Full queue with Raise Fault and explicit subsequent recovery/closure | Pending. In-flight work may finish; pending target does not become PASS/FAIL. Record defining Fault before recovery. |
| T06 | Pause and Resume with production/inspection already active | Pending. Accepted jobs finish; queued/remaining work waits; Resume keeps original batch and identities. |
| T07 | Graceful Stop with active and waiting work | Pending. No fresh dispatch, finite completion/recovery, truthful incomplete totals and confirmed closure. |
| T08 | Paused runtime production/inspection/N/K changes | Pending. Both idle stations confirm settings; future jobs use new versions, old results retain old settings. |
| T09 | Operator disconnect/reconnect and lease expiry | Pending. Accepted jobs finish; new dispatch pauses; reconnect alone does not resume. |
| T10 | A USB interruption / detected restart | Pending. Choose a fault mechanism explicitly: unplugging its sole USB power normally reboots A and must not be called a same-boot test. |
| T11 | B network interruption/reconnection without resetting B | Pending. Specify and capture a controlled network interruption that preserves power; distinguish it from reboot. |
| T12 | A/B reboot between closed batches | Pending, test stations separately. Verify new idle boot confirmation and old History retention. |
| T13 | A/B reboot during open work | Pending, test stations separately. Old work stays uncertain where appropriate; no blind replay on new boot. |
| T14 | Gateway restart with open work | Pending. History persists, execution is not restored automatically, old scopes require explicit recovery. |
| T15 | Rule boundaries and deterministic verdicts | Pending: N=1, large N, positive/negative K and arithmetic bounds; derive expectations from actual part IDs. |
| T16 | Batch/queue/timing boundaries | Pending: one part, 64-part/history limit, queue 1/64, unequal/equal times and supported timing extremes. Long runs require explicit time budgeting; do not launch all extremes together. |
| T17 | Invalid/out-of-range/malformed controls | Pending. Reject with explanation and no execution/configuration change. |
| T18 | Same-ID replay, changed-content conflicts, lost ACK/completion and bounded recovery | Native software tests already exist; controlled integration/physical mechanism must be designed before assigning these cases. Ordinary repeated Start clicks are not a duplicate-ID test. Preserve original IDs/contents and prove no duplicate execution. |
| T19 | Multiple operator panels and stale status | Pending. One controller lease, other panels view-only; no competing mutation or stale display presented as live. |
| T20 | Evidence audit and full demonstration | Pending. Correlate report original IDs with B packets and A decoded serial frames; review required states, counts and provenance of each verdict. |

## Planned cards T02-T04: currently execute T02 only

The user subsequently requested that we complete and review each case together.
This supersedes the earlier permission to advance through the three-card group.
Only T02 is currently assigned. Review its JSON, raw capture and GUI screenshots,
then guide the meaningful Wireshark screenshots from that same capture before
assigning T03. T03 and T04 remain planned, not authorized for execution yet.

Only proceed to the next card after the current case and evidence have been
reviewed together and the next case is explicitly assigned. A mismatch stops
the sequence for review. Keep the
gateway and ESPs running throughout this group. The current Wi-Fi capture was
visually confirmed: filter `tcp port 5001 or tcp port 8080`, traffic between
gateway 172.20.10.2 and B 172.20.10.3 plus operator 172.20.10.5. It may include
idle heartbeats/status updates before T02; that does not invalidate the capture.

All three use N=2, K=0, Wait for space. These are test-case labels, not GUI batch
numbers. Preserve the actual Batch N and actual part IDs in reports.

| Case / folder | Parts | Production seconds | Inspection seconds | Queue | Final produced / inspected | PASS / FAIL |
|---|---:|---:|---:|---:|---|---|
| T02 / `T02_normal_capture` | 4 | 2 | 1 | 2 | 4 / 4 | 2 / 2 |
| T03 / `T03_consecutive_batch` | 4 | 2 | 1 | 2 | 4 / 4 | 2 / 2 |
| T04 / `T04_queue_wait` | 6 | 1 | 4 | 1 | 6 / 6 | 3 / 3 |

Every final state must be Idle, outcome Completed, with zero unresolved,
not-started and not-inspected. Odd IDs PASS, even IDs FAIL. B is responsible for
the actual verdict. Matching a deterministic expectation does not substitute
for retaining B's messages.

### Per-case recording and saving

1. Before Start, ensure gateway ready/Idle, A/B connected and Wireshark capture
   running on the selected Wi-Fi interface. T02 uses the currently running
   capture. For T03/T04 start a fresh Wireshark capture using the blue fin/Capture
   Start after the previous capture has been stopped and saved. Keep the same
   capture filter and interface. After each fresh capture starts, refresh the
   operator browser with Ctrl+F5 while Idle, wait for live/ready, then enter
   settings. This records the HTTP/WebSocket handshake as well as later status;
   it does not require gateway or ESP restart.
2. Set the card's inputs and click GUI Start once. T02 additionally needs
   `01-settings.png` before Start. Do not press other workshop controls.
3. T04 must visibly reach queue 1/1 with B inspecting and A waiting, without
   Fault. Save `event-queue-full.png` while this is visible. B's in-progress part
   is outside the waiting queue. Production automatically continues as B frees
   waiting capacity, within the same batch and original target.
4. When Idle/Completed appears and final counts match, save `final-gui.png`
   showing state, counters, actual batch label and individual verdicts. Use
   `02-final-gui.png` for T02 to match its earlier assigned naming.
5. Open History, Refresh, select the just-ended batch and download its actual
   `batch-N.json`. T02 needs `03-history.png` with summary and representative
   A/B stage rows. T03 needs `history.png` showing the newer batch and retained
   earlier History entry; its actual part IDs must differ from T02's.
6. Wait about two seconds after confirmed Idle/Completed, then stop Wireshark
   with its red Stop square (not GUI Stop), File > Save As, and save in pcapng
   format as `Test_Cases/Evidences/<case-folder>/capture.pcapng` on the gateway
   PC. Never overwrite another case's capture or close an unsaved capture.
7. Store GUI screenshots and the report under the matching case folder on the
   operator PC. Transfer the gateway capture into that folder for review. The
   raw capture can be reopened to make exact report packet screenshots later;
   do not substitute a screenshot of unrelated idle traffic for job evidence.

Typical durations are about 10-15 s for T02/T03 and 25-35 s for T04. These are
guidance, not modified controller deadlines. Stop the test group for review if
T02/T03 is unfinished after 30 s, T04 after 60 s, or any unexpected Fault/error
occurs. Preserve the current state and capture; do not click Start repeatedly
or reset devices to clear uncertainty.

### What the Wireshark pictures will demonstrate

Using the saved normal-case capture, select meaningful exchanges rather than
random packet rows: runtime B configuration (time, N, K), matching application
acknowledgements, an inspection request and B's matching PASS/FAIL result, and
HTTP Start/WebSocket status. The detailed selection/stream-following steps will
be given after the raw capture has been checked. Later fault captures should
show the interruption and bounded recovery without inventing lost ACK times.

## Report use

Report sections will explain architecture/topology, reproducible settings,
protocol/framing and message identity, operating states/queue policy, reliability,
test method and expected-versus-observed results, selected annotated evidence,
limitations and contributions. Formal multi-protocol benchmarking, MQTT access
control and Milestone 2 measurements are separate work and are not claimed by
this Milestone 1 checklist. A functional PASS does not by itself prove every
timeout/retry/duplicate corner case or replace raw protocol evidence.

## Official PDF scope review (19 November 2026)

Source: `reference/MCT431 Project Fall 26.pdf`, requirements on pages 2-3,
general submission checklist on page 3, explicit Milestone 1 scope on page 5.
The tests below are evidence categories, not instructions to execute them now.

| Explicit Milestone 1 item | Evidence we must retain/review |
|---|---|
| A-to-gateway framed USB serial: SLIP, ATR, CRC, sequence numbers | Raw A serial trace, decoded representative valid frames, framing/CRC/sequence explanation. Current-session raw file remains on gateway PC; review is pending. |
| B-to-gateway custom TCP with length prefix | Saved PCAP and annotated request/reply examples, including the length prefix. T02's B messages decode correctly. |
| Requested batch, unique parts, finite queue, four states, completion counts | Normal run, both relative timing arrangements, queue-full behavior and focused state-transition cases. One completed batch does not prove all of these. |
| HTTP Start/Pause/Resume/Stop and WebSocket status | T02 captures Start and live WebSocket status. Pause/Resume and Stop need their own focused cases. |
| Unique IDs, distinct delivery/acceptance/completion, bounded retries/timeouts, duplicate suppression | Normal three-stage exchanges plus controlled lost-response, duplicate and disconnection/stale-data checks. A successful first attempt does not demonstrate retry bounds. |
| TCP captures, framed-link serial logs, live full-batch demonstration | Keep the raw files as supporting evidence; use selected annotated screenshots in the report. Prepare the live demonstration separately. |

The runtime inspection rule and its parameters must be applied on B, not inferred
from GUI counts alone. T02's network results contain B's explicit verdicts under
the same original job IDs as their requests. Runtime production and inspection
times must also be demonstrated, including production faster than inspection.

The PDF's general submission checklist also calls for source/configuration and
scripts, reproducible instructions, architecture/state diagrams, message
specifications, raw CSV measurements, annotated captures/serial logs, plots with
units and interpretation, justified protocol choices, and a specific-task
contribution table plus individual oral explanations. Track these in report
preparation; do not treat screenshots alone as the submission. The Milestone 1
section explicitly defers formal benchmarking to Milestone 2. Keep ordinary
application timing data/plots distinct from the later multi-protocol benchmark;
do not silently discard the general CSV/plot checklist or claim that benchmark
work has already been performed.

## T02 evidence review: actual Batch 8

Folder: `Test_Cases/Evidences/T02_Normal_Capture`.
Reviewed `01-settings.png`, `02-final-gui.png`, `batch-8.json`, and
`T02_Normal_Capture.pcapng`. `03-history.png` is not present yet. The final GUI
picture shows correct totals and Idle but crops off individual part cards;
the report records 33 PASS, 34 FAIL, 35 PASS, 36 FAIL. A History screenshot can
show these without repeating the physical run.

Settings: target 4, production 2000 ms, inspection 1000 ms, N=2, K=0, queue 2,
Wait for space. Gateway-reported batch elapsed time: 11172 ms. All actual stage
observations exist for B configuration, A configuration, four production jobs,
four inspection jobs and both close commands. Every operation has one request
attempt and zero queries. B reports inspection execution times 1000, 1001,
1000 and 1001 ms. Network requests and results match the report's full IDs and
contents. This establishes matching evidence, not a claim that this normal
run exercised retry/duplicate/recovery paths.

Useful original-capture packet numbers for later annotated screenshots:

| Exchange | Request | RECEIVED | ACCEPTED | COMPLETED |
|---|---:|---:|---:|---:|
| B settings: inspection=1000 ms, N=2, K=0 | 46826 | 46830 | 46842 | 46842 |
| Inspect part 33: PASS | 46891 | 46897 | 46903 | 46930 |
| Inspect part 34: FAIL | 46966 | 46973 | 46979 | 47005 |
| Inspect part 35: PASS | 47037 | 47045 | 47045 | 47080 |
| Inspect part 36: FAIL | 47114 | 47121 | 47124 | 47153 |
| Close B run | 47169 | 47171 | 47177 | 47177 |

These are distinct application messages even when two occupy the same TCP
packet. TCP packet ACK flags do not substitute for these messages. B traffic
is TCP stream 1 in this original capture. HTTP Start is frame 46821; the
WebSocket upgrade is frame 1005, Running status is visible at 46850, and
Idle/Completed at 47182. The long capture includes idle time before/after the
roughly eleven-second batch; preserve the original and filter it for pictures.

### Finding: misleading configuration-pending status

Frames 46832 and 46841 publish Fault / "batch configuration incomplete" while
Start is pending, with Batch 7's old completed counts temporarily shown as
active. Frame 46847 has the new ID but still mixes old production totals with
new inspection totals. Frame 46850 is coherently Running with the new batch.
`gateway/production/coordinator.py::BatchGateway.start_run` deliberately sets
Fault as its pre-dispatch guard while awaiting station configuration; the
operator snapshot exposes the partially transitioned core directly. This is
not evidence of a network disconnection, but it misrepresents normal startup.

Recommended correction for subsequent implementation: present an explicit
pending-Start explanation while the required four-state model remains intact,
publish a coherent batch identity/counter view, keep dispatch blocked until
both settings complete, and publish a real Fault if configuration fails or
expires. Preserve this original capture as evidence of the finding. No code
behavior was changed as part of this evidence review.

### Follow-up correction and report assets

The startup presentation correction has now been implemented. While Start is
pending, the operator receives a coherent previous idle batch view and an
explicit settings-loading explanation. Both station configurations must still
complete before dispatch. A's old production accounting is cleared when B has
established the new batch, so a later A-configuration failure cannot attribute
old production counts to the new batch. Real failures still expose Fault.
Verification: 28 backend and 9 frontend checks passed, including pending
configuration on each station and failed A configuration after a prior batch.
Physical verification remains pending; keep the original T02 evidence.

`Test_Cases/Report` now contains an eight-row measurement CSV, a unit-labelled
production/inspection execution-time comparison plot, an annotated B TCP
excerpt, and written interpretation/provenance/reproduction instructions.
These are Milestone 1 application evidence; they do not claim to perform the
formal Milestone 2 protocol benchmark. A's current raw serial file still needs
to be collected once for the testing session and checked.

### User-named T01_NORMAL_CAPTURE: Batch 9 review and closure correction

The user saved the follow-up run in `Test_Cases/Evidences/T01_NORMAL_CAPTURE`.
Its final GUI and History screenshots, `batch-9.json`, and raw capture agree:
parts 37/39 PASS, 38/40 FAIL; four produced/inspected; no missing work. B's six
request/three-stage-response exchanges match the report exactly; all 12 station
operations have one request attempt, zero queries and observed R/A/C stages.
The captured HTTP Start confirms target 4, production 2000 ms, inspection
1000 ms, N=2, K=0, queue 2/block. The settings image is an older Batch 7 image;
do not label it as a fresh Batch 9 setup screenshot.

The new capture verifies corrected startup: pending Start is Idle with a
coherent empty view, then Running with Batch 9. It also reveals a separate
closure issue: frames 3082/3090 publish Fault / "batch closure in progress"
before frame 3098 correctly becomes Idle/Completed. Final results are correct;
retain this as pre-correction evidence rather than claiming a fault-free run.

The closure correction now gates A using `ending` and B using its paused
dispatcher without manufacturing a Fault. Normal automatic closure remains
Running / Closing batch until both stations confirm; a normal Stop remains
Paused / Stopping while current jobs finish. Read-only recovery is invoked
only when uncertainty actually exists. Real closure failure or conflicting /
stale station evidence remains Fault and requires explicit recovery.
Software verification passed 30 backend, 19 native A/B integration and 9
frontend checks. These include withheld B closure confirmation (not completed
early), failed B closure after A closes (results retained, explicit recovery),
and normal Stop without a false Fault. Hardware verification of this closure
correction remains pending and can accompany the next assigned case; do not
restart the entire test sequence. Neither ESP firmware was changed.
