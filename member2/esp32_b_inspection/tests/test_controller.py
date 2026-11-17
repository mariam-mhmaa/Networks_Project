"""Deterministic scripted-peer checks for bounded gateway recovery."""
import asyncio
from pathlib import Path
import sys
import unittest
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from gateway.inspection.controller import Controller, Evidence, Outcome, Policy
from gateway.inspection.client import BClient
from gateway.inspection.coordinator import InspectionGateway, GatewayFault
from gateway.inspection.wire import Ids, Restarted, encode

POLICY = Policy(receipt_s=.025, acceptance_s=.025, completion_allowance_s=.035,
                query_window_s=.025, absolute_allowance_s=.25)
REQUEST = {"v": 1, "type": "INSPECT", "job_id": "job-1", "boot_id": "b"*32,
           "batch_id": "batch-1", "run_no": 1, "part_id": 1, "config_version": 1}


def reply(request, stage, **fields):
    key = "job_id" if request["type"] == "INSPECT" else "cmd_id"
    return {"v": 1, "type": stage, "action": request["type"], key: request[key],
            "boot_id": request["boot_id"], "batch_id": request["batch_id"],
            "run_no": request["run_no"],
            **({"part_id": request["part_id"]} if request["type"] == "INSPECT" else {}), **fields}


class Peer:
    def __init__(self, behavior):
        self.routes, self.sent, self.handles = {}, [], []
        self.failure = None
        self.counter = 0
        self.behavior = behavior
        self.log = lambda kind, body: None

    def route(self, identifier, queue):
        self.routes[identifier] = queue

    def unroute(self, identifier):
        self.routes.pop(identifier, None)

    def next_query_no(self):
        self.counter += 1
        return self.counter

    def emit(self, message, delay=0):
        def deliver():
            queue = self.routes.get(message.get("job_id", message.get("cmd_id")))
            if queue and not queue.full():
                queue.put_nowait(message)
        self.handles.append(asyncio.get_running_loop().call_later(delay, deliver))

    async def send(self, request, payload):
        self.sent.append((dict(request), payload))
        await self.behavior(self, request)

    def close(self):
        for handle in self.handles:
            handle.cancel()


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def run_peer(self, behavior, policy=POLICY, duration=0):
        peer = Peer(behavior)
        self.addCleanup(peer.close)
        controller = Controller(peer, Ids(), policy)
        started = asyncio.get_running_loop().time()
        outcome = await controller.run(REQUEST, duration_ms=duration)
        elapsed = asyncio.get_running_loop().time() - started
        return peer, outcome, elapsed

    async def test_no_responses_has_exact_finite_budgets_and_identical_request_bytes(self):
        async def behavior(peer, request):
            pass
        peer, outcome, elapsed = await self.run_peer(behavior)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertEqual(outcome.evidence.request_attempts, 3)
        self.assertEqual(outcome.evidence.query_attempts, 2)
        originals = [payload for request, payload in peer.sent if request["type"] == "INSPECT"]
        self.assertEqual(originals, [encode(REQUEST)]*3)
        self.assertLess(elapsed, .5)
        self.assertFalse(peer.routes)

    async def test_pending_validation_cannot_reset_the_budget(self):
        async def behavior(peer, request):
            if request["type"] == "INSPECT":
                for i in range(30):
                    peer.emit(reply(request, "STATUS", state="PENDING_VALIDATION"), i*.005)
        _, outcome, elapsed = await self.run_peer(behavior)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertEqual(outcome.evidence.request_attempts, 3)
        self.assertEqual(outcome.evidence.query_attempts, 2)
        self.assertLess(elapsed, .5)

    async def test_repeated_accepted_and_in_progress_do_not_extend_execution(self):
        async def behavior(peer, request):
            if request["type"] == "INSPECT":
                for i in range(35):
                    peer.emit(reply(request, "ACCEPTED"), i*.005)
                    peer.emit(reply(request, "STATUS", state="IN_PROGRESS"), i*.005)
        _, outcome, elapsed = await self.run_peer(behavior)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertEqual(outcome.evidence.request_attempts, 1)
        self.assertEqual(outcome.evidence.query_attempts, 2)
        self.assertLess(elapsed, .3)

    async def test_stalled_transport_writes_cannot_escape_absolute_limit(self):
        async def behavior(peer, request):
            await asyncio.Event().wait()
        peer, outcome, elapsed = await self.run_peer(behavior)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertLessEqual(len(peer.sent), 5)
        self.assertLess(elapsed, .5)

    async def test_restart_stops_original_request_replay(self):
        async def behavior(peer, request):
            peer.failure = Restarted("receiver boot changed")
            raise peer.failure
        peer, outcome, _ = await self.run_peer(behavior)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertEqual(len(peer.sent), 1)
        self.assertIn("boot changed", outcome.reason)

    async def test_later_completion_does_not_fabricate_ack_observations_or_retry(self):
        result = {"job_id": "job-1", "action": "INSPECT", "batch_id": "batch-1",
                  "run_no": 1, "part_id": 1, "state": "COMPLETED", "elapsed_ms": 0,
                  "config_version": 1, "verdict": "PASS",
                  "settings": {"inspection_time_ms": 1, "N": 2, "K": 0}}
        async def behavior(peer, request):
            peer.emit(reply(request, "COMPLETED", result=result), .005)
            peer.emit(reply(request, "RECEIVED"), .01)
            peer.emit(reply(request, "ACCEPTED"), .015)
        peer, outcome, _ = await self.run_peer(behavior)
        await asyncio.sleep(.08)
        self.assertEqual(outcome.state, "COMPLETED")
        self.assertIsNone(outcome.evidence.received_observed_at)
        self.assertIsNone(outcome.evidence.accepted_observed_at)
        self.assertEqual(len(peer.sent), 1)

    async def test_conflicting_result_is_uncertainty_not_product_fail(self):
        result = {"job_id": "job-1", "action": "INSPECT", "batch_id": "another-batch",
                  "run_no": 1, "part_id": 1, "state": "COMPLETED", "elapsed_ms": 0,
                  "config_version": 1, "verdict": "FAIL"}
        async def behavior(peer, request):
            peer.emit(reply(request, "COMPLETED", result=result))
        _, outcome, _ = await self.run_peer(behavior)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertIsNone(outcome.result)

    async def test_late_first_acceptance_remains_under_original_absolute_limit(self):
        async def behavior(peer, request):
            if len(peer.sent) == 1:
                peer.emit(reply(request, "ACCEPTED"), .095)
                peer.emit(reply(request, "ACCEPTED"), .12)
        policy = Policy(receipt_s=.025, acceptance_s=.025, completion_allowance_s=.2,
                        query_window_s=.025, absolute_allowance_s=.08)
        _, outcome, elapsed = await self.run_peer(behavior, policy, duration=100)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertIn("absolute", outcome.reason)
        self.assertLess(elapsed, .35)

    async def test_boolean_configuration_version_is_not_valid_completion(self):
        result = {"job_id": "job-1", "action": "INSPECT", "batch_id": "batch-1",
                  "run_no": 1, "part_id": 1, "state": "COMPLETED", "elapsed_ms": 0,
                  "config_version": True, "verdict": "PASS",
                  "settings": {"inspection_time_ms": 1, "N": 2, "K": 0}}
        async def behavior(peer, request):
            peer.emit(reply(request, "COMPLETED", result=result))
        _, outcome, _ = await self.run_peer(behavior)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertIsNone(outcome.result)

    async def test_explicit_reconciliation_cannot_regress_accepted_work_to_rejected(self):
        client = BClient("127.0.0.1")
        async def query(identifier):
            target = {**REQUEST, "action": "INSPECT", "state": "REJECTED", "error": "BUSY"}
            return Outcome("COMPLETED", "query-1", {"target": target}, Evidence())
        client.query = query
        with tempfile.TemporaryDirectory() as local:
            core = InspectionGateway(client, queue_capacity=1, full_policy="block",
                                     ledger_path=Path(local)/"state.sqlite3")
            core.state = "FAULT"
            core.requests["job-1"] = REQUEST
            core.unresolved["job-1"] = Outcome("UNRESOLVED", "job-1", None,
                Evidence(acceptance_established_by="ACCEPTED"), "completion missing")
            with self.assertRaises(GatewayFault):
                await core.reconcile("job-1")
            self.assertIn("job-1", core.unresolved)
            self.assertEqual(core.state, "FAULT")
