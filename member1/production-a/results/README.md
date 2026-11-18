# Serial check evidence

Store actual build, flash and serial output here. These checks establish that
the tools and board run; they do not measure production or link performance.

Step 1: `setup_serial.log` and the original build/flash/probe logs.
Step 2: `step2_serial.json` has full TX/expected RX/actual RX bytes and case
outcomes. `step2_hardware_test.log` has the console summary. Other `step2_*`
logs record build, partition validation, flash, host tests and port release.

Final physical acceptance: `physical_acceptance_idle.json/.csv` records the
idle cable removal/reconnection and completed explicit recovery job; it retains
overall passed=false because a fixture reporting TypeError occurred afterward.
`physical_acceptance_producing.json/.csv` passes the remaining production phase,
including old-session rejection, zero retransmission of stopped work and new
explicit recovery completion. `physical_acceptance_attempt1.json/.csv` preserves
the first discovery failure; `physical_discovery_diagnostic.json` records the
subsequent successful read-only check. The original physical_acceptance.json is
also retained as the incomplete idle fixture attempt. See docs/acceptance.md
for operator-confirmed unplug timing, receive-pause limits, and physical
same-session/external-power NOT RUN coverage. Firmware source hashes match in
physical_firmware_before.csv and _after.csv. COM3 is closed.

Step 3: `step3_software_tests.log` is software-only validation.
`step3_hardware.json` contains all 29 actual hardware exchanges, full wire
bytes and outcomes. Other `step3_*` files record identity, partition capture,
build/flash, pre-flash bounds, hardware console summary and port release.

Approved continuation follow-up: `continuation_software_tests.log` has 48
passing software tests. `continuation_hardware.json` and `.log` record five
passing targeted hardware groups, exact frames, omissions/releases, status
queries, eligibility decisions and immutable retry outcomes. The verification
logs summarize confirmations, audit ordering, unchanged firmware hashes and
independent COM3 reopen/close. Physical unplug/replug is NOT RUN. Existing
unchanged hardware suites were not rerun; their earlier evidence remains below.

Step 5C: `step5c_software_tests.log` has 34 passing software tests;
`step5c_retries.json` and `step5c_retries.csv` contain exact operation identity,
attempts, ignored/quarantined responses, deadlines and final operation outcomes.
`step5c_retry_test.log` summarizes nine passing hardware test groups.
Existing regressions are in step5c_*_regression JSON/log files. Firmware hashes
before/after and final verification confirm no firmware edits or flashing and
COM3 release. Expected unresolved/fault/rejection outcomes are not test failures.

Step 5B: `step5b_software_tests.log` has 19 passing software tests;
`step5b_protocol_regression.json`, `step5b_production_regression.json` and
`step5b_history_regression.json` preserve previous hardware coverage with
session fields/heartbeat routing. `step5b_sessions.json` has six new hardware
groups, statuses, raw bytes and controlled heartbeat-loss evidence.
`step5b_history_attempt1.*` retains the original too-short active-test window
failure. Other step5b logs record build/flash, board/layout, watcher and final
port release. See docs/progress.md for results and physical-test limitations.

Step 5A: final `step5a_software_tests.log` has 13 passing software tests;
`step5a_c_history.log` executes actual C history code on the PC;
`step5a_target_ram.log` measures ESP32 ELF type sizes offline.
`step5a_protocol_regression.json`, `step5a_production_regression.json` and
`step5a_history.json` contain final hardware evidence. Initial history runs
with test-harness errors are retained as `step5a_history_attempt1.*` and
`step5a_history_attempt2.*`. See docs/progress.md for their explanation.

Step 4: `step4_protocol_regression.json` records the 29 retained protocol
cases; `step4_production.json` records actual production TX/RX/events,
1000/2500 ms timings and check outcomes. Other step4 logs contain software,
build/flash, identity/layout checks, console summary and port verification.
