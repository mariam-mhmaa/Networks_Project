"""Durable history migration and identity display; no physical station access."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from gateway.inspection.coordinator import Ledger
from gateway.operator.history import History


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "gateway.sqlite3"
        self.ledger = Ledger(self.path)

    async def legacy_batch(self, number, *, closed=True):
        batch = f"batch-{number}"
        session = str(number) * 32
        production = f"PROD-GW-{session}-000001"
        inspection = f"INSP-GW-{session}-000001"
        start = {"cmd_id": f"START-OP-{session}-000001", "batch_size": 1,
                 "production_time_ms": 2, "inspection_time_ms": 1, "N": 2, "K": 0,
                 "queue_capacity": 1, "full_policy": "block"}
        evidence = {"received_observed_at": 10., "accepted_observed_at": 11.,
                    "completed_observed_at": 12., "request_attempts": 1, "query_attempts": 0, "queries": {}}
        await self.ledger.record("operator_received", {"action": "start", "request": start})
        await self.ledger.record("configure", {"identifier": "CFG-" + str(number), "state": "COMPLETED", "result": {"batch_id": batch}, "evidence": evidence})
        await self.ledger.record("reserved", {"batch_id": batch, "part_id": number, "job_id": inspection})
        await self.ledger.record("production_request", {"batch_id": batch, "part_id": number, "job_id": production})
        await self.ledger.record("production_outcome", {"identifier": production, "state": "COMPLETED", "result": {"batch_id": batch, "produced": True}, "evidence": evidence})
        await self.ledger.record("produced", {"batch_id": batch, "part_id": number})
        await self.ledger.record("inspection_request", {"batch_id": batch, "part_id": number, "job_id": inspection})
        if closed:
            await self.ledger.record("accounted", {"identifier": inspection, "state": "COMPLETED", "result": {"batch_id": batch, "verdict": "PASS" if number % 2 else "FAIL"}, "evidence": evidence})
            await self.ledger.record("batch_close", {"batch_id": batch, "target": 1, "inspection_complete": True, "unresolved": 0})
        await self.ledger.record("operator_outcome", {"cmd_id": start["cmd_id"], "phase": "completed", "command": "start"})
        return batch, production, inspection

    async def test_two_legacy_batches_remain_separate_after_restart_without_report_files(self):
        first, *_ = await self.legacy_batch(1)
        second, *_ = await self.legacy_batch(2)
        history = History(self.ledger)
        page = await history.page()
        self.assertEqual([item["batch"]["id"] for item in page["items"]], [second, first])
        self.assertEqual((await history.report(first))["counts"]["passed"], 1)
        self.assertEqual((await history.report(second))["counts"]["failed"], 1)
        restarted = History(Ledger(self.path))
        self.assertEqual(await history.report(first), await restarted.report(first))
        self.assertEqual([p.name for p in Path(self.directory.name).iterdir()], ["gateway.sqlite3"])

    async def test_session_aliases_are_durable_and_never_reused_for_new_sessions(self):
        _, first, _ = await self.legacy_batch(1)
        history = History(self.ledger)
        await history.refresh()
        alias = history.label(first)
        _, second, _ = await self.legacy_batch(2)
        restarted = History(self.ledger)
        await restarted.refresh()
        self.assertEqual(alias, restarted.label(first))
        self.assertNotEqual(restarted.label(first), restarted.label(second))
        self.assertNotIn("1" * 32, alias)

    async def test_open_or_interrupted_batch_is_not_mislabeled_completed(self):
        batch, *_ = await self.legacy_batch(1, closed=False)
        report = await History(self.ledger).report(batch)
        self.assertEqual(report["batch"]["outcome"], "interrupted_or_open")
        self.assertEqual(report["counts"]["produced"], 1)
        self.assertEqual(report["counts"]["inspected"], 0)
        self.assertEqual(report["counts"]["not_inspected"], 1)

    async def test_reconciliation_does_not_fabricate_original_ack_times(self):
        batch, _, inspection = await self.legacy_batch(1, closed=False)
        original = {"received_observed_at": None, "accepted_observed_at": None, "completed_observed_at": None,
                    "request_attempts": 3, "query_attempts": 2, "queries": {}}
        await self.ledger.record("inspection_outcome", {"identifier": inspection, "state": "UNRESOLVED", "result": None, "evidence": original})
        query_evidence = {**original, "received_observed_at": 20., "accepted_observed_at": 21., "completed_observed_at": 22.}
        await self.ledger.record("accounted", {"identifier": inspection, "state": "COMPLETED", "result": {"verdict": "PASS"},
            "evidence": query_evidence, "reason": "explicit historical reconciliation; dispatch remains stopped"})
        report = await History(self.ledger).report(batch)
        op = next(o for o in report["operations"] if o["id"] == inspection)
        self.assertIsNone(op["evidence"]["completed_observed_at"])
        self.assertEqual(op["recovered_result"]["verdict"], "PASS")

    async def test_paging_and_reads_preserve_application_event_count(self):
        for n in (1, 2, 3):
            await self.legacy_batch(n)
        history = History(self.ledger)
        first = await history.page(0, 2)
        self.assertEqual(first["next_offset"], 2)
        self.assertEqual((await history.page(2, 2))["items"][0]["batch"]["display_id"], "Batch 1")
        with closing(sqlite3.connect(self.path)) as db:
            count = db.execute("SELECT count(*) FROM events").fetchone()[0]
        await history.report("batch-1")
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], count)

    async def test_repeated_wire_stages_compact_and_null_ack_times_stay_null(self):
        batch, production, _ = await self.legacy_batch(1)
        observation = {"batch_id": batch, "station": "A", "event": "receive", "observed_at": 10.,
                       "data": {"job_id": production, "type": "COMPLETED"}}
        for _ in range(3):
            await self.ledger.record("station_observation", observation)
        report = await History(self.ledger).report(batch)
        op = next(o for o in report["operations"] if o["id"] == production)
        self.assertEqual(len(op["observations"]), 1)
        self.assertEqual(op["duplicate_observations"], 2)
        self.assertNotIn("heartbeat", json.dumps(report))

    async def test_automatic_query_stages_belong_to_the_query_not_the_original(self):
        batch, production, _ = await self.legacy_batch(1)
        query = "QUERY-GW-" + "1" * 32 + "-000001"
        evidence = {"received_observed_at": None, "accepted_observed_at": None, "completed_observed_at": None,
                    "request_attempts": 3, "query_attempts": 1, "delivery_established_by": "QUERY_COMPLETED",
                    "queries": {query: {"received_observed_at": 20., "accepted_observed_at": 21., "completed_observed_at": 22.}}}
        await self.ledger.record("production_outcome", {"identifier": production, "state": "COMPLETED",
            "result": {"batch_id": batch, "produced": True}, "evidence": evidence})
        report = await History(self.ledger).report(batch)
        operations = {o["id"]: o for o in report["operations"]}
        self.assertIsNone(operations[production]["evidence"]["completed_observed_at"])
        self.assertEqual(operations[query]["evidence"]["completed_observed_at"], 22.)
        self.assertEqual(operations[query]["target_id"], production)

    async def test_new_outcome_after_checkpoint_is_in_history_and_restart_does_not_resume(self):
        batch, _, inspection = await self.legacy_batch(1, closed=False)
        view = {"batch": {"id": batch, "target": 1, "outcome": "active", "elapsed_ms": 100},
            "settings": None, "counts": {"passed": 0}, "queue": {}, "state": "Running",
            "parts": [{"part_id": 1, "production_job_id": "PROD-GW-" + "1"*32 + "-000001", "inspection_job_id": inspection,
                       "produced": True, "status": "inspecting", "isolated": False}]}
        await self.ledger.record("operator_batch_view", view)
        await self.ledger.record("accounted", {"identifier": inspection, "state": "COMPLETED", "result": {"verdict": "FAIL"}, "evidence": {}})
        report = await History(self.ledger).report(batch)
        self.assertEqual(report["batch"]["outcome"], "interrupted_or_open")
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["counts"]["inspected"], 1)
        await self.ledger.record("batch_close", {"batch_id": batch, "target": 1, "inspection_complete": True, "unresolved": 0})
        await self.ledger.record("operator_batch_view", view)  # Late pre-closure checkpoint.
        self.assertEqual((await History(self.ledger).report(batch))["batch"]["outcome"], "completed")
