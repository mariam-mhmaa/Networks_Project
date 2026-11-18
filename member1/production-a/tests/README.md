# Serial acceptance checks

1. Build the minimal firmware for the directly detected chip target.
2. Flash only the identified physical ESP32 port.
3. For Step 3 run `pc_test/framed_test.py --port COM3` and require exact
   framed responses, silence for invalid inputs and valid recovery.
4. Confirm the PC program exits and releases the port.

Actual outcomes and commands belong in `docs/progress.md`; captures belong in
`results/`. This is a smoke check, not Milestone 2 benchmarking. Production,
SLIP/ATR/CRC are tested in Step 3. Production duplicate handling and device
fault behavior remain deferred.

Step 4: `python pc_test/production_test.py --port COM3` resets the station,
checks UNCONFIGURED rejection, validates both timing configurations, tests
invalid/busy requests and verifies matching IDs, event ordering and measured
1000/2500 ms completion. Evidence is actual hardware, separate from Python
parser software tests. See docs/run.md and docs/protocol.md.

Run `python -m unittest discover -s tests -v` to check host accumulation,
partial writes, finite incomplete-read timeout and bad/extra-byte rejection.
The old Step 1 reader and logs remain as historical evidence only.

`test_protocol.py` is software-only Python validation. It includes the full
29-case input matrix in a subtest loop and a fixed shared ATR/SLIP fixture.
The separately logged 29 hardware exchanges test the flashed C code. C also
runs a silent CRC/reference-example startup self-test before accepting input.

Step 5A software tests compile/execute actual history.c with the existing host
GCC and verify that explicit invalid-input probes are not repaired by the PC
client. Hardware: `python pc_test/history_test.py --port COM3` runs eight
history groups. Read docs/history.md for operation/identifier requirements and
RAM/restart limitations. Intentional duplicate probes are not automatic retries.

Step 5B: `session_test.py --port COM3` runs discovery/heartbeat/session hardware
groups, controlled RX-heartbeat suppression, ordinary reopen, deliberate
restart and explicit configure/start recovery. Physical unplug/replug is NOT
RUN. `test_session.py` checks exact monotonic deadlines and response routing;
`test_gateway_run.py` checks explicit recovery/start gates. All regressions now
route heartbeats separately, rather than treating all serial traffic as replies.

Final physical acceptance uses pc_test/physical_acceptance.py, a guided fixture
that asks for real unplug/replug actions. It does not change firmware or client
behavior. Read docs/acceptance.md before repeating: raw idle runner retains a
reporting failure after a completed recovery, the remaining production phase
passed, and physical timing is operator-confirmed rather than instrumented.
Physical external-power/same-session recovery remains NOT RUN.

Approved continuation follow-up: test_dispatch.py adds deterministic status,
late-evidence, deduplication, stale-status, explicit-action and fault tests.
The full software suite now passes 48 tests. continuation_test.py runs five
targeted hardware groups; it preserves exhausted budgets and uses explicitly
logged withheld real results/synthetic stale status. See docs/continuation.md.
Unchanged hardware suites were not rerun; physical unplug/replug remains NOT RUN.

Step 5C: test_retry.py executes the real controller with fake monotonic time,
including shared acceptance/completion retry budgets and irrevocably stopped
operations. retry_test.py runs nine hardware response-omission/safety groups.
See docs/retries.md for deterministic frame omission, deadlines, station-based
non-duplication evidence and CSV/JSON interpretation. Firmware is unchanged.

Repository portability: the host C history test now builds/runs in a temporary
directory and leaves archived results untouched. Use existing host GCC on PATH.
See ../docs/repository_setup.md for software-only verification from this checkout.
