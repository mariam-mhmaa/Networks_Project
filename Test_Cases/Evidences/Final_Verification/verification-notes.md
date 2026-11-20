# Final verification evidence review

Current gateway code: main commit 1902e8e. These notes record reviewed evidence,
not unexecuted tests. Original evidence files are unchanged. A raw USB serial
trace is still to be collected once from the gateway testing session; operation
reports alone do not prove CRC/SLIP/ATR bytes.

## T01_Normal - Batch 10

Reviewed all five supplied files: `01-settings.png`, `01-finalGUI.png`,
`History.png`, `batch-10.json`, `T01_Normal_Capture.pcapng`.

Production/inspection functional PASS: target 4, production 2000 ms, inspection
1000 ms, N=2, K=0, capacity 2/block. Parts 41/43 PASS, 42/44 FAIL. Final Idle,
4 produced, 4 inspected, 2 PASS, 2 FAIL, zero unresolved/unstarted/not-inspected.
Elapsed 11062 ms. All 12 station operations have actual R/A/C observations,
one request attempt and zero recovery queries. B's six framed request/response
exchanges match report contents and IDs exactly. HTTP Start is packet 2041;
the B configuration request is 2044; part 41 request/R/A/C are
2113/2114/2118/2147; B closure request/result are 2387/2398.

Limitation: capture starts mid-WebSocket connection with compressed messages
whose prior compression context is absent. No HTTP Upgrade is captured. It is
not valid to claim every transient GUI state was independently verified from
this capture. The subsequent T02 capture covers those state transitions.

## T02_Queue_Wait - Batch 11

Reviewed all six supplied files: `02-Settings.png`, `02-QueueFull.png`,
`Result.png`, `Batch_result.png`, `batch-11.json`,
`T02_Queue_Wait_Capture.pcapng`.

PASS: target 6, production 1000 ms, inspection 4000 ms, N=2, K=0, capacity
1/block. Parts 45/47/49 PASS, 46/48/50 FAIL; all distinct from T01. Final Idle,
6 produced/inspected, 3 PASS/3 FAIL, zero missing work. Elapsed 27141 ms.
All 16 station operations have actual R/A/C observations, one request attempt,
zero queries. All eight B request/response exchanges match the report exactly.
A reports 1000 ms for all six production executions; B reports 4000 ms for
five inspections and 4010 ms for one. Timer scheduling overhead is distinct
from gateway observation/network timing.

HTTP Upgrade response is original packet 1239; HTTP Start 9487. B configuration
request/R/A/C: 9489/9501/9504/9504. Part 45 inspection request/R/A/C:
9541/9548/9551/9677. B closure request/R/A/C: 10356/10362/10369/10369.
Distinct messages sharing a packet remain distinct application stages.

Decoded 992 server status samples after Start. There are 73 samples of a full
1/1 waiting queue with B busy and A idle. No Batch 11 sample exceeds one queued
or reserved slot, and none has A busy with the waiting queue already full.
The queue-full screenshot shows the same condition, with part 48 inspecting,
49 queued and the final target position still unstarted. Remaining production
continues automatically within the same batch.

Captured startup samples 9495/9506 keep the previous completed Batch 10 view
coherent while settings are pending. Packet 9511 switches to the new batch
with zero production/inspection counts. Automatic-closure status packets
10358/10366 are Running with `control_pending:completing_batch` and no fault;
the final view is Idle/Completed. No Fault status was observed after Start.
This physically verifies the startup/closure status corrections in this case.
Final serial capture-health status reports zero dropped records and no error;
actual raw-frame review is still pending.

## T03_Pause_Resume - Batch 12

Reviewed all six supplied files: `03-Settings.png`, `Pause.png`, `Final_GUI.png`,
`History.png`, `batch-12.json`, `T03_Pause_Resume_Capture.pcapng`.

PASS: target 6, production 3000 ms, inspection 5000 ms, N=2, K=0, capacity
2/block. Original part IDs 51-56 are preserved: 51/53/55 PASS, 52/54/56 FAIL.
Final Idle/Completed, 6 produced/inspected, 3 PASS/3 FAIL, zero missing work.
All 16 station operations have actual R/A/C observations, one request attempt
and zero queries. All eight B exchanges match original requests and results.
Start/Pause/Resume controls completed under the same original batch ID. Their
HTTP request packets are 8071/8256/13087, respectively.

Pause completed at gateway monotonic second 870948.734; Resume was accepted
at 871106.250 (157.516 s later). A's part 52 and B's part 51 were already
accepted before Pause and completed afterwards. No job's receipt observation
falls between completed Pause and Resume, and no B INSPECT request was sent
on the captured TCP link during the paused interval. The decoded status stream
includes 8 Paused samples with both stations still active, then 760 settled
Paused samples spanning 153.680 s. Settled counters remain 2 produced,
1 inspected, 1 PASS/0 FAIL, zero unresolved, 4 unstarted and 5 not inspected;
one queued part (52) is retained. Resume completes this same batch/target.
No Fault status was observed for Batch 12.

Total batch elapsed time is 189467 ms (3:09.467), including the deliberate long
pause; it must not be described as uninterrupted production performance.
Capture-health status reports 6716 serial records written, zero dropped and
no error. Actual raw A serial-frame review is still pending.

## Remaining verification categories

Three final cases do not complete Milestone 1 verification. Remaining evidence
includes graceful Stop/incomplete accounting; runtime setting/rule changes and
invalid inputs/bounds; implemented queue-Fault behavior; A/B disconnection,
stale-data and restart recovery; same-ID replay and changed-content conflicts;
lost acknowledgement/result recovery with explicit finite retry/query limits.
Some paths already have automated C-peer/controller tests; preserve their
results as software evidence and distinguish them from physical tests. A second
Start with a fresh ID is not a duplicate-execution test. Assign controlled
replays/interruption mechanisms before executing those cases.

The gateway command stores `serial.local.jsonl` (raw A USB bytes) and
`gateway.sqlite3` (application journal/history) in the gateway PC repository
root. They span cases. Collect a consistent stopped-session copy once; do not
delete/reset them to clean individual evidence folders. Use decoded serial
excerpts and database-derived tables/plots in the report, retaining original
files as supporting evidence. A status saying zero dropped records does not
replace actual raw-frame validation.

## T04_Graceful_Stop - PASS on Batch 14 (corrected repeat)

Folder `T04_Graceful_Stop`; target 8, production 3000 ms, inspection 5000 ms,
N=2, K=0, capacity 2/block. Press Stop during the first overlap with both A
producing and B inspecting. Stop gates new jobs, allows existing accepted jobs
to finish and confirms both scopes closed. A's current produced part is not
automatically sent for inspection after Stop; waiting inventory gets no
invented verdict. Expect Idle/Incomplete with confirmed partial PASS/FAIL
counts, zero unresolved under healthy links, fewer than 8 produced/inspected,
positive unstarted and not-inspected counts. Exact partial totals depend on
click timing; inspected must equal PASS+FAIL and produced must be at least
inspected. Not-inspected includes target positions not yet produced, so it
overlaps unstarted. No Resume or new Start in this case. Capture before browser
refresh (confirm HTTP 101), then save settings, stopping if possible, final GUI,
History/Stop outcome, batch JSON and PCAP. Preserve any unexpected Fault and
seek review rather than resetting/retrying. Keep serial/database logging.

### T04 first attempt: Batch 13 Fault - not a pass

User stopped the procedure when Fault appeared; local evidence initially held
`Settings.png` and `Stopping.png`. Read-only HTTP inspection confirmed current
Fault / "Operator stop requires recovery: Stop needs station recovery/confirmed
idle closure", both original station boots connected and idle, no job-level
unresolved outcomes. Part 57 was produced/inspected PASS; 58 was produced and
queued without inspection. Counts 2 produced, 1 inspected, 1 PASS/0 FAIL,
6 unstarted, 7 not inspected, zero unresolved. No CLOSE operation had been sent.
Stop was accepted at monotonic 872617.515 and failed at 872621.484, well before
the configured idle-wait bound. This is an unsuccessful Stop, not an incomplete
batch closure already confirmed. Read-only snapshots were saved locally as
`batch-13-fault.json` and `status-before-recovery.json`; no HTTP control was sent
by the assistant.

A reproducible gateway defect was found: B's old `Link.failure` survived a
valid same-boot reconnect, although `fresh` reported true. Stop could therefore
reject the short idle-heartbeat wait because of that obsolete exception. A
new regression failed before the fix and passed afterwards. The transport
now clears old failures only on a validated same-boot heartbeat and excludes
current failures from freshness; detected restarts stay latched. Verification
passed 32 operator/backend, 19 A/B integration, 53 B application/controller/
transport and 9 frontend checks. Firmware unchanged. The old HTTP snapshot
does not expose the exact stored exception, so the capture is still required
to investigate whether this physical attempt also had a transient disruption.
Do not claim this hardware failure's complete root cause proved from the
screenshots alone.

Preserve the Fault capture before changing state. With fresh idle original
stations, the intended manual recovery is End incomplete batch, not Continue
remaining and not a forced restart. Confirm the recovered batch's actual
Incomplete outcome and partial counts before stopping/restarting the gateway
to install the new code. Then repeat T04 only with the fix; do not redo T01-03.
Before assigning guarded continuation after a failed Stop, review its ending
gate: the current continuation routine does not explicitly clear/refuse
`ending`; it must not be used for this Stop recovery.

### T04 later recovery: both boot identities changed

Read-only live status after the user confirmed restarted A and B and selected
End incomplete batch shows Idle, ready=true, fault=null; Batch 13 is Incomplete.
Confirmed totals remain 2 produced, 1 inspected, 1 PASS, 0 FAIL, 0 unresolved,
6 unstarted, 7 not inspected. Gateway process identity is unchanged.
A boot changed from a781a66f80c66efd3defeffa4c4c3d8f to
f7100699df012d1186548e385a1317df; B changed from
4e10697350ee20b9e1556f5709c37bb4 to fb87aa41402d632406e183cdf82ec192.
This establishes later station restarts, not their cause. Long idle time alone
is not an expected reason to reboot. No new capture or screenshots were present
in this operator folder when reviewed. Saved status-after-recovery.json and
batch-13-after-recovery.json using GET only. This is restart recovery evidence,
not a passing ordinary graceful Stop test. Install e3bda04 before repeating T04.


### T04 final accepted evidence: Batch 14 PASS

Accepted files remain in T04_Graceful_Stop/Retest: Settings.png, Final_GUI.png,
History.png, batch-14.json, T04_Graceful_Stop.pcapng. Automatic approval review
blocked the attempted move/delete cleanup command before it ran; no evidence
files were moved or deleted. Earlier Batch13 files remain at the parent level.

Batch14 target8, P3000ms/I5000ms, N2/K0, capacity2/block. Final Idle/Incomplete,
2 produced, 1 inspected, 1 PASS, 0 FAIL, 0 unresolved, 6 unstarted,
7 not inspected. Part59 PASS, part60 produced/uninspected. All seven station
operations show observed RECEIVED/ACCEPTED/COMPLETED, one request attempt,
zero recovery queries; A and B CLOSE results both closed=true.
Stop completed in5344ms; elapsed batch9890ms. Both production jobs and the only
inspection were accepted before Stop. Device durations A3000ms each/B5000ms.

PCAP SHA256 d04de3aeda04db91dea969027b633f613e354fd6b9d7579bdc6d97582cda6555.
9035 packets; HTTP101 frame667, Start2951, Stop3095; B stream1.
B CONFIGURE2954, RECEIVED2961, ACCEPTED/COMPLETED2969.
INSPECT59 request3069, RECEIVED3073, ACCEPTED3076, COMPLETED3247 PASS.
B CLOSE3271, RECEIVED3278, ACCEPTED/COMPLETED3285. Length-prefixed TCP messages
reassembled without gaps; outgoing B requests match report contents.
Decoded 976 Batch14 status snapshots: Running20/Paused27/Idle929; no Fault.
Pending Stop stays Paused while accepted work finishes; final Idle/Incomplete
matches report totals. No new B inspection after Stop. Final serial logger
status written919/dropped0/error=null. Raw A serial validation deferred until
stopped-session log collection. This passes ordinary graceful Stop; the old
Batch13 restart recovery is not included as successful normal Stop evidence.

## T05_Paused_Settings_Change - assigned, not yet executed

Start six parts P3000ms/I5000ms N2/K0 queue2/block. Pause during first A/B
overlap; let accepted jobs finish, wait both Ready while still Paused. Record
counts P0/F0/I0 and original batch identity. Change P1000ms/I2000ms N1/K0,
keeping target/capacity/full policy fixed. Apply while Paused and idle, wait
both confirmations, then explicit Resume. All later inspections including
previously queued uninspected parts use N1, hence FAIL. Past verdicts remain;
final total6/6, PASS=P0, FAIL=6-P0, zero unresolved/unstarted/uninspected,
Idle/Completed, same batch. If first overlap pause, normally I0=1 and next
part61 PASS, hence final1PASS/5FAIL; use actual prechange retained counts.
Future production elapsed1000ms and future inspection2000ms; earlier3000/5000
remain frozen in operation results. Capture before CtrlF5; collect settings,
Paused-before-change, settings-confirmed-while-Paused, final GUI, History,
selected batch JSON and T05_Settings_Change.pcapng. Fault: preserve and stop,
no recovery/reset/new Start. No firmware/GW restart needed for this case.


### T05 first submission: Batch15 does not demonstrate reconfiguration

Six PNG/JSON files present; no PCAP in T05 at review. Batch15 completed 6/6,
3PASS/3FAIL, no missing results. Controls only Start/Pause/Resume; no Configure.
Only initial two station CONFIGURE operations; all later jobs still use
config_version2, production3000ms, inspection5000ms, N2/K0. No job receipts
during completed Pause to accepted Resume. Paused screenshot shows 1PASS/0FAIL.
New_Settings_Applied.png shows edited inputs 1s/2s/N1/K0, but feedback remains
Paused: current jobs may finish; remaining work stays in this same batch.
No station-settings confirmation appears. Final inputs still show edits,
while actual report/results prove original settings stayed active. This is
not a passing T05. Awaiting user clarification whether Apply was clicked
and whether any confirmation/error appeared. No cause/user mistake assumed;
no code edit or evidence deletion made.

T05 clarification: user confirmed Apply settings was not pressed before Resume.
No settings-command failure established; original values correctly stayed active.
Repeat only T05, without gateway/ESP restart, using Retest subfolder. Require
explicit settings-confirmed message before Resume and collect missing PCAP.

### T05 accepted repeat: Batch16 PASS

User placed the new files directly in T05_Paused_Settings_Change, replacing the
first JSON/final/applied/history images, rather than in the empty Retest folder.
Accepted report batch-16.json and capture T05_Paused_Setting_Change_Capture.pcapng.
Settings1.png and Paused_Before_Change.png remain old first-attempt screenshots;
the latter visibly names Batch15 and must NOT illustrate Batch16 in the report.
Use New_Settings_Applied.png (Batch16, both confirmations, still Paused, 1PASS)
and Final_GUI.png/History.png with Batch16; sufficient alongside raw capture,
so no repeat is required to replace the historical Paused-before screenshot.

Same Batch16 target6 throughout Start/Pause/Configure/Resume, all completed.
Initial A3000ms/B5000ms N2/K0 config_version3; confirmed update A1000ms/B2000ms
N1/K0 config_version4 with run_no3 unchanged. Part67 PASS stays unchanged.
Part68 was produced under original settings, then inspected under new settings
and FAIL; parts69-72 produced1000ms and inspected new N1/2000ms, all FAIL.
Five later inspection durations2000ms except71=2010ms; first67=5000ms.
Final Idle/Completed6/6,1PASS/5FAIL,0unresolved/unstarted/not_inspected.
18 station operations all original RECEIVED/ACCEPTED/COMPLETED observed,
one request attempt, zero queries; A and B CLOSE confirmed. No job receipts
between completed Pause and accepted Resume. Overall elapsed109719ms includes
long manual pause; do not treat it as uninterrupted execution throughput.

Capture SHA256 fd74095357640d1fa97afc7e2348499268b55bc48aa557c78d4371ddeb745fb5.
HTTP101394/635; Start3617/Pause3781/Configure5114/Resume6680; B stream1.
All nine B exchanges exactly match requests and COMPLETED result contents in
report; every exchange has one RECEIVED, ACCEPTED and COMPLETED. Reassembled
length-prefixed TCP both directions without gaps. B initialconfigure3624/3629/
3639, firstinspect3755/3758/3763/3919; reconfigure5125/5136/5145;
queuedpart68inspect6691/6701/6711/6766; CLOSE7111/7114/7117.
Decoded862 Batch16 WS snapshots Running76/Paused465/Idle321, zeroFault.
248 Paused snapshots show confirmed new settings with original1PASS retained,
frames5152 through6683 (last pending Resume); final counts match report.
Serial logger final written4372,dropped0,error=null; raw A USB frame analysis
still deferred until stopped-session log collection. No firmware/code edits.

## T06_Duplicate_Protection - software PASS; live HTTP replay pending capture

User requested duplicate protection next, ahead of the planned Raise Fault case.
Eight focused checks pass using actual portable C A/B firmware applications over
native localhost transports and the real Python gateway. Covers duplicate Start,
changed-content Start conflict, A active retry/completed replay, A changed-part
same-ID conflict, A fresh-ID duplicate part, B active retry, B cached replay,
B changed-part same-ID conflict and fresh-ID duplicate part. Some checks include
multiple assertions/scenarios. Outputs: software-duplicate-tests.log and
software-duplicate-summary.json with test IDs/source hashes. Initial drafts of
two new A checks waited only0.6s and read an old execution-counter heartbeat;
corrected to wait1.1s for A's one-second heartbeat. Required conflict/rejection
assertions already passed; final eight-check run passes, no firmware correction.
New tests/runner/reproduction document pushed in commit4584513; no runtime or
firmware code changed, so gateway restart/pull is not needed for this live case.

Live replay plan prepared from exact Start HTTP payload at T05 PCAP frame3617,
original Batch16 Start ID8256165647369776c4b2671231d8ce9b-000001.
GET preflight verified same gateway boot, retained completed Start and current
Idle/Completed Batch16. live-replay-plan.json holds original body and changed
batch-size conflict body. NO physical POST has yet been sent. Wait for user's
fresh gateway Wi-Fi capture before sending exact original twice and conflict
once; expect202/202/409 and no new batch/work. Recheck preflight immediately
before POST; abort on identity/state mismatch, never replace original IDs.
This physical HTTP test proves gateway command deduplication, not physical ESP
job deduplication. Native station-code results must stay labelled software.

### T06 live HTTP replay PASS; raw capture transfer/review pending

After user explicitly confirmed a fresh Wireshark capture was ready, repeated
GET preflight verified retained completed original Start, unchanged gateway
GW-46dc14268a54485fa845fc7582410ee7, healthy Idle/Completed Batch16.
Assistant then sent exactly three POST /api/start requests: original Batch16
Start twice (HTTP202 identical cached acks), then same cmd_id with batch_size
changed6 to7 (HTTP409 ID_CONFLICT). No new identity or execution was submitted.
The two identical requests retained original settings3s/5s/N2 even though
current applied settings are1s/2s/N1; those current settings stayed unchanged.
No station job was directly injected; this is command deduplication at the
live gateway, separate from the eight native station/software checks.

After every request and12 additional status reads spanning3s, gateway identity,
Idle state/noFault, batch identity/outcome, settings, counts and part records
were unchanged. Original command record remained identical, history total
stayed16, and the entire Batch16 report was identical. Final6produced/6inspected,
1PASS/5FAIL, no missing work. Evidence saved live-before.json, live-after.json,
live-duplicate-result.json (three requests/replies with UTC times and latency).
User must now save After GUI and raw T06 capture for packet-level review.
No extra batch JSON download is needed because the Batch16 report is unchanged
and already retained under T05. No physical ESP duplicate-job proof claimed.

### T06 final capture and screenshots reviewed: PASS

Accepted files Before.png/After.png/T06_Duplicate_Capture.pcapng are present.
Capture SHA256 e574c4135fd3676d449695393071a508c5ba377f4a230e47e56985110bc51f22.
HTTP/WebSocket handshake frame441. Exact request/response pairs:
3036->3039 HTTP202 original target6, 3085->3089 HTTP202 identical target6,
3135->3139 HTTP409 same cmd_id changed target7. Parsed HTTP JSON request bodies
and response bodies match live-duplicate-result.json exactly. Both first
requests identical to original captured Batch16 Start; conflict only changes
batch_size. Source operator172.20.10.5 -> gateway172.20.10.2.

B existing stream1 decoded without gaps/partial length-prefixed messages;
501 messages all HEARTBEAT, one unchanged boot and executions counter13
throughout; no B CONFIGURE/INSPECT/CLOSE/query issued during this capture.
1165 decoded gateway WS snapshots frames445-9535 all Idle/Completed Batch16,
1PASS/5FAIL/6produced/6inspected, original applied1s/2s/N1 settings unchanged,
no Fault/new batch. Screenshots agree on state/results/batch. After screenshot
has queue-capacity draft field5 after refresh, while actual queue display stays
0/2; this is next-batch input, not an applied queue change. Use results/state
area for report comparison; do not describe draft input as changed active config.
Eight native software duplicate tests pass separately; physical ESP job
injection not performed. Live cached HTTP command protection now evidenced
in raw capture; no repeat or additional batch JSON needed for this case.
