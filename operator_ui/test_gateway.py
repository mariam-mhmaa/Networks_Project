"""Repeatable wire-level tests against the Member 3 test gateway (no ESP32s)."""
import asyncio
import unittest
from aiohttp.test_utils import AioHTTPTestCase
from mock_gateway import create_app, Factory


class FactoryTests(unittest.TestCase):
    def body(self, f, **settings):
        return {"schema_version": 1, "gateway_id": f.gateway_id, "cmd_id": "start-1",
                "batch_size": 8, "production_time_ms": 10, "inspection_time_ms": 40, "N": 4, "K": 0, **settings}

    def test_duplicate_and_conflicting_id(self):
        f = Factory(); body = self.body(f)
        first, code = f.command("start", body); batch = f.batch_id
        again, again_code = f.command("start", body)
        self.assertEqual((again, again_code), (first, code)); self.assertEqual(f.batch_id, batch)
        conflict, code = f.command("start", {**body, "batch_size": 7})
        self.assertEqual(code, 409); self.assertFalse(conflict["accepted"])
        self.assertEqual(len(f.parts), 8)

    def test_queue_reservation_and_complete_counts(self):
        f = Factory(capacity=2); f.command("start", self.body(f))
        maximum = 0
        for _ in range(1000):
            f.advance(10); maximum = max(maximum, len(f.queue))
            self.assertLessEqual(len(f.queue) + int(f.production is not None), f.capacity)
        self.assertEqual(maximum, 2)
        self.assertEqual((f.state, f.outcome, f.produced, f.passed, f.failed), ("Idle", "completed", 8, 6, 2))

    def test_pause_drains_accepted_work_resume_and_stop(self):
        f = Factory(); f.command("start", self.body(f)); f.advance(1)
        control = {"schema_version": 1, "gateway_id": f.gateway_id, "batch_id": f.batch_id}
        f.command("pause", {**control, "cmd_id": "pause-1"})
        f.advance(100)
        self.assertEqual(f.produced, 1); self.assertIsNone(f.production); self.assertIsNone(f.inspection)
        self.assertEqual(list(f.queue), [1]); self.assertEqual(f.state, "Paused")
        f.command("resume", {**control, "cmd_id": "resume-1"}); f.advance(1)
        self.assertIsNotNone(f.inspection)
        f.command("stop", {**control, "cmd_id": "stop-1"})
        before = f.snapshot()["counts"]; f.advance(10000)
        self.assertEqual(before, f.snapshot()["counts"])
        self.assertEqual(f.outcome, "aborted"); self.assertIsNone(f.production); self.assertIsNone(f.inspection)

    def test_invalid_settings_and_wrong_boot(self):
        f = Factory()
        rejected, code = f.command("start", self.body(f, N=0))
        self.assertFalse(rejected["accepted"]); self.assertEqual(code, 422); self.assertIsNone(f.batch_id)
        f.reset()
        rejected, code = f.command("start", {**self.body(f), "gateway_id": "old-boot"})
        self.assertFalse(rejected["accepted"]); self.assertEqual(code, 409); self.assertIsNone(f.batch_id)


class WireTests(AioHTTPTestCase):
    async def get_application(self):
        return create_app(allow_origin="http://127.0.0.1:8765", test_controls=True)

    async def start(self, **overrides):
        body = {"schema_version": 1, "gateway_id": self.app["factory"].gateway_id, "cmd_id": "wire-start",
                "batch_size": 4, "production_time_ms": 20, "inspection_time_ms": 30, "N": 4, "K": 0, **overrides}
        response = await self.client.post("/api/start", json=body)
        return body, response

    async def test_http_ws_batch_and_duplicate(self):
        ws = await self.client.ws_connect("/ws/status")
        initial = await ws.receive_json(timeout=2)
        self.assertEqual(initial["state"], "Idle")
        body, response = await self.start()
        self.assertEqual(response.status, 202); self.assertEqual((await response.json())["phase"], "accepted")
        batch_id = self.app["factory"].batch_id
        duplicate = await self.client.post("/api/start", json=body)
        self.assertTrue((await duplicate.json())["accepted"])
        self.assertEqual(self.app["factory"].batch_id, batch_id)
        result = await (await self.client.get("/api/commands/wire-start")).json()
        self.assertEqual(result["phase"], "completed")
        sequences = [initial["status_seq"]]
        for _ in range(20):
            s = await ws.receive_json(timeout=2); sequences.append(s["status_seq"])
            if s["batch"]["outcome"] == "completed": break
        self.assertEqual(s["batch"]["outcome"], "completed")
        self.assertEqual(s["counts"], {"produced": 4, "inspected": 4, "passed": 3, "failed": 1})
        self.assertEqual(sequences, sorted(set(sequences)))
        await ws.close()

    async def test_fault_restart_and_reconnect_snapshot(self):
        old = self.app["factory"].gateway_id
        await self.start(production_time_ms=1000)
        await self.client.post("/test/scenario", json={"action": "disconnect_b"})
        s = await (await self.client.get("/api/status")).json()
        self.assertEqual(s["state"], "Fault"); self.assertFalse(s["stations"]["inspection"]["connected"])
        await self.client.post("/test/scenario", json={"action": "restart"})
        ws = await self.client.ws_connect("/ws/status")
        fresh = await ws.receive_json(timeout=2)
        self.assertNotEqual(fresh["gateway_id"], old); self.assertEqual(fresh["batch"]["outcome"], "none")
        self.assertEqual((await self.client.get("/api/commands/wire-start")).status, 404)
        await ws.close()

    async def test_cors_malformed_rejection_and_static_assets(self):
        response = await self.client.options("/api/start", headers={"Origin": "http://127.0.0.1:8765", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status, 204)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:8765")
        self.assertEqual((await self.client.get("/api/status", headers={"Origin": "http://other.invalid"})).status, 403)
        self.assertEqual((await self.client.post("/api/start", json=[])).status, 400)
        _, response = await self.start(N=0)
        self.assertEqual(response.status, 422)
        self.assertEqual((await response.json())["phase"], "rejected")
        self.assertEqual((await self.client.get("/app.js")).status, 200)
        self.assertEqual((await self.client.get("/mock_gateway.py")).status, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
