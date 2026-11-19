"""Focused duplicate tests using native C peers, never physical ESP32 devices."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "gateway.operator.tests.test_operator.OperatorTests.test_duplicate_post_has_one_execution_and_conflict_does_not_replace_it",
    "test_integrated.IntegratedTests.test_retry_new_atr_sequence_same_job_no_reexecution",
    "test_integrated.IntegratedTests.test_changed_part_same_production_id_does_not_execute_again",
    "test_integrated.IntegratedTests.test_fresh_id_cannot_produce_same_part_again",
    "test_application.ApplicationTests.test_retry_during_active_job_does_not_restart_timer_or_execute_twice",
    "test_application.ApplicationTests.test_duplicate_same_job_replays_result_once",
    "test_application.ApplicationTests.test_changed_contents_same_id_is_conflict_and_does_not_execute",
    "test_application.ApplicationTests.test_fresh_id_cannot_reinspect_same_part",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/duplicates")
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    for directory in ("stations/production/tests", "stations/inspection/tests"):
        sys.path.insert(0, str(ROOT / directory))
    with (output / "software-duplicate-tests.log").open("w", encoding="utf-8") as log:
        log.write("Native C station software tests; localhost only, no physical ESP32s.\n")
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromNames(TESTS))
    sources = {}
    for directory in ("gateway", "shared/station", "stations/production/firmware/main",
                      "stations/production/tests", "stations/inspection/main",
                      "stations/inspection/tests"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".c", ".h"}:
                sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {
        "scope": "Software: actual native C station code and Python gateway over localhost; no physical ESP32s",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "tests_run": result.testsRun, "passed": result.wasSuccessful(), "test_ids": TESTS,
        "failures": [(test.id(), reason) for test, reason in result.failures],
        "errors": [(test.id(), reason) for test, reason in result.errors], "sources": sources,
        "reproduce": "python -B tools/verify_duplicates.py --output <evidence-folder>",
    }
    (output / "software-duplicate-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"{'PASS' if result.wasSuccessful() else 'FAIL'}: {result.testsRun} duplicate checks; {output}")
    if not result.wasSuccessful():
        print((output / "software-duplicate-tests.log").read_text(encoding="utf-8"))
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
