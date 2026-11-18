"""Real C station peers with the actual FastAPI/asyncio operator service."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import unittest
import httpx
import uvicorn
import websockets

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "member1/production-a/tests"))
import test_integrated as native
FAST = native.FAST
from gateway.production.client import AClient
from gateway.inspection.client import BClient
from gateway.production.coordinator import BatchGateway
from gateway.operator.service import OperatorService
from gateway.operator.server import create_app


class OperatorTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(native.IntegratedTests.setUpClass.__func__)
    host = native.IntegratedTests.host

    async def asyncSetUp(self):
        await native.IntegratedTests.asyncSetUp(self)
        self.services, self.http, self.keepalives = [], [], []

    async def asyncTearDown(self):
        for task in self.keepalives:
            task.cancel()
        await asyncio.gather(*self.keepalives, return_exceptions=True)
        for client in self.http:
            await client.aclose()
        for service in self.services:
            await service.shutdown()
        await native.IntegratedTests.asyncTearDown(self)

    async def service(self, *aflags, bflags=(), lease_s=5, keepalive=True, start_monitor=True, evidence=None):
        aport, bport = self.host(*aflags), self.host(*bflags, inspection=True)
        factories = {"A": lambda: AClient(f"socket://127.0.0.1:{aport}", policy=FAST, log=evidence.logger("A") if evidence else None),
                     "B": lambda: BClient("127.0.0.1", bport, policy=FAST, log=evidence.logger("B") if evidence else None)}
        core = BatchGateway(factories["A"](), factories["B"](), queue_capacity=2, full_policy="block",
                            ledger_path=Path(self.state_dir.name)/f"operator-{len(self.services)}.sqlite3")
        service = OperatorService(core, simulation=True, factories=factories, lease_s=lease_s, evidence=evidence)
        self.services.append(service)
        if start_monitor: await service.start()
        await core.a.connect(); await core.b.client.connect()
        app = create_app(service)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.http.append(client)
        self.owner = "OP-tests"
        def alive():
            snapshot = service.snapshot()
            service.alive(self.owner, service.gateway_id, snapshot["status_seq"])
        alive()
        if keepalive:
            async def keep():
                while True:
                    alive(); await asyncio.sleep(.1)
            self.keepalives.append(asyncio.create_task(keep()))
        return service, client, app

    def request(self, service, action, **fields):
        identifier = f"{action.upper()}-OP-tests-{len(service.records)+1:06d}"
        body = {"schema_version": 1, "gateway_id": service.gateway_id, "operator_id": self.owner, "cmd_id": identifier}
        if action == "start":
            body.update(batch_size=4, production_time_ms=60, inspection_time_ms=180, N=3, K=0,
                        queue_capacity=2, full_policy="block")
        else:
            body["batch_id"] = service.core.b.batch_id
        body.update(fields)
        return body

    async def command(self, service, client, action, **fields):
        body = self.request(service, action, **fields)
        response = await client.post("/api/"+action, json=body)
        self.assertEqual(response.status_code, 202, response.text)
        result = await self.until(lambda: service.lookup(body["cmd_id"])["phase"] not in {"received", "accepted"})
        record = service.lookup(body["cmd_id"])
        self.assertEqual(record["phase"], "completed", record)
        return record

    async def until(self, condition, timeout=8):
        end = asyncio.get_running_loop().time()+timeout
        while not condition():
            if asyncio.get_running_loop().time() > end:
                self.fail("Condition did not become true before its finite test deadline")
            await asyncio.sleep(.02)
        return True

    async def test_consecutive_batches_have_separate_read_only_downloads_and_restart_history(self):
        from gateway.operator.history import History
        service, client, _ = await self.service()
        ids = []
        for _ in range(2):
            await self.command(service, client, "start", batch_size=2)
            await self.until(lambda: service.core.state == "IDLE" and service.auto_close.done())
            await self.until(lambda: service.snapshot()["ready"])
            ids.append(service.core.b.batch_id)
        page = (await client.get("/api/history")).json()
        self.assertEqual([item["batch"]["id"] for item in page["items"]], ids[::-1])
        reports = []
        for number, identifier in enumerate(ids, 1):
            reply = await client.get(f"/api/history/{identifier}?download=true")
            self.assertEqual(reply.headers["content-disposition"], f'attachment; filename="batch-{number}.json"')
            report = reply.json()
            self.assertEqual(report["batch"]["outcome"], "completed")
            self.assertEqual(report["counts"]["inspected"], 2)
            jobs = [op for op in report["operations"] if op["id"].startswith(("PROD-", "INSP-"))]
            self.assertEqual(len(jobs), 4)
            self.assertTrue(all(op["evidence"]["completed_observed_at"] is not None for op in jobs))
            self.assertEqual(len(report["controls"]), 1)
            reports.append(report)
        self.assertTrue(set(p["part_id"] for p in reports[0]["parts"]).isdisjoint(p["part_id"] for p in reports[1]["parts"]))
        self.assertEqual(await History(service.core.b.ledger).report(ids[0]), reports[0])
        self.assertEqual(service.core.state, "IDLE")
        self.assertEqual((await client.get('/api/history?limit=101')).status_code, 422)
        self.assertEqual((await client.get('/api/history/unknown')).status_code, 404)

    async def test_http_start_full_batch_and_distinct_command_stages(self):
        service, client, _ = await self.service()
        record = await self.command(service, client, "start")
        self.assertIsNotNone(record["received_at"])
        self.assertIsNotNone(record["accepted_at"])
        self.assertIsNotNone(record["completed_at"])
        await self.until(lambda: service.core.state == "IDLE")
        view = (await client.get("/api/status")).json()
        self.assertEqual(view["batch"]["outcome"], "completed")
        self.assertEqual((view["counts"]["passed"], view["counts"]["failed"]), (3, 1))
        self.assertTrue(view["simulation"])
        self.assertNotIn(service.core.b.batch_id, view["batch"]["display_id"])
        asset = await client.get("/")
        self.assertIn("The Toy", asset.text)
        self.assertEqual((await client.get("/mock_gateway.py")).status_code, 404)

    async def test_pause_finishes_current_jobs_then_resume_same_batch(self):
        service, client, _ = await self.service()
        await self.command(service, client, "start", batch_size=6, production_time_ms=200, inspection_time_ms=350)
        await self.until(lambda: service.core.active and service.core.b.active)
        original = service.core.b.batch_id
        await self.command(service, client, "pause")
        await self.until(lambda: not service.core.active and not service.core.b.active)
        before = service.snapshot()
        await asyncio.sleep(.4)
        after = service.snapshot()
        self.assertEqual(before["counts"], after["counts"])
        self.assertEqual(after["state"], "Paused")
        self.assertLess(after["counts"]["inspected"], 6)
        await self.command(service, client, "resume")
        await self.until(lambda: service.core.state == "IDLE")
        self.assertEqual(service.core.b.batch_id, original)
        self.assertEqual(service.snapshot()["counts"]["inspected"], 6)

    async def test_graceful_stop_retains_partial_totals_and_new_batch_gets_new_ids(self):
        service, client, _ = await self.service()
        await self.command(service, client, "start", batch_size=8, production_time_ms=200, inspection_time_ms=300)
        await self.until(lambda: service.core.active and service.core.b.active)
        old_batch = service.core.b.batch_id
        await self.command(service, client, "stop")
        stopped = service.snapshot()
        self.assertEqual(stopped["batch"]["outcome"], "incomplete")
        self.assertEqual(stopped["state"], "Idle")
        self.assertEqual(stopped["counts"]["inspected"], stopped["counts"]["passed"]+stopped["counts"]["failed"])
        self.assertGreater(stopped["counts"]["not_inspected"], 0)
        last = max(p["part_id"] for p in stopped["parts"])
        await self.until(lambda: service.snapshot()["ready"])
        await self.command(service, client, "start", batch_size=2)
        await self.until(lambda: service.core.state == "IDLE")
        self.assertNotEqual(service.core.b.batch_id, old_batch)
        self.assertTrue(all(p.part_id > last for p in service.core.b.parts.values()))

    async def test_operator_loss_pauses_and_reconnection_needs_explicit_resume(self):
        service, client, _ = await self.service(lease_s=.25, keepalive=False)
        await self.command(service, client, "start", batch_size=8, production_time_ms=200, inspection_time_ms=300)
        await self.until(lambda: service.core.state == "PAUSED")
        await self.until(lambda: not service.core.active and not service.core.b.active)
        before = service.snapshot()["counts"]
        current = service.snapshot(); service.alive(self.owner, service.gateway_id, current["status_seq"])
        await asyncio.sleep(.1)
        self.assertEqual(service.core.state, "PAUSED")
        self.assertEqual(service.snapshot()["counts"], before)
        await self.until(lambda: service.snapshot()["can_resume"])
        current=service.snapshot(); service.alive(self.owner,service.gateway_id,current["status_seq"])
        await self.command(service, client, "resume")
        self.assertEqual(service.core.state, "RUNNING")

    async def test_paused_reconfiguration_keeps_past_verdicts_and_updates_future_jobs(self):
        service, client, _ = await self.service()
        await self.command(service, client, "start", batch_size=5, production_time_ms=80, inspection_time_ms=300)
        await self.until(lambda: service.core.b.active is not None)
        await self.command(service, client, "pause")
        await self.until(lambda: service.snapshot()["can_edit"])
        known = dict(service.core.b.results)
        await self.command(service, client, "configure", batch_size=5, production_time_ms=10, inspection_time_ms=10, N=1, K=0)
        self.assertEqual(service.core.state, "PAUSED")
        await self.command(service, client, "resume")
        await self.until(lambda: service.core.state == "IDLE")
        for identifier, original in known.items():
            self.assertEqual(service.core.b.results[identifier].result, original.result)
        future = [out.result for key, out in service.core.b.results.items() if key not in known]
        self.assertTrue(future)
        self.assertTrue(all(r["settings"]["N"] == 1 and r["verdict"] == "FAIL" for r in future))

    async def test_partial_configuration_failure_cannot_continue_with_mixed_settings(self):
        from unittest.mock import patch
        from gateway.inspection.coordinator import GatewayFault
        service,client,_=await self.service()
        await self.command(service,client,"start",batch_size=6,production_time_ms=100,inspection_time_ms=200)
        await self.command(service,client,"pause")
        await self.until(lambda: service.snapshot()["can_edit"])
        with patch.object(service.core.b.client,"configure",side_effect=GatewayFault("B configuration unavailable")):
            body=self.request(service,"configure",batch_size=6,production_time_ms=50,inspection_time_ms=50,N=1,K=0)
            response=await client.post("/api/configure",json=body)
            self.assertEqual(response.status_code,202)
            await self.until(lambda: service.lookup(body["cmd_id"])["phase"]=="unresolved")
        self.assertTrue(service.snapshot()["configuration_hold"])
        self.assertEqual(service.core.state,"FAULT")
        response=await client.post("/api/continue",json=self.request(service,"continue"))
        self.assertEqual(response.status_code,409)
        await self.command(service,client,"stop")
        self.assertEqual(service.snapshot()["batch"]["outcome"],"incomplete")

    async def test_duplicate_post_has_one_execution_and_conflict_does_not_replace_it(self):
        service, client, _ = await self.service()
        body = self.request(service, "start", batch_size=2)
        first = await client.post("/api/start", json=body)
        second = await client.post("/api/start", json=body)
        self.assertEqual(first.json(), second.json())
        conflict = await client.post("/api/start", json={**body, "batch_size": 3})
        self.assertEqual(conflict.status_code, 409)
        await self.until(lambda: service.lookup(body["cmd_id"])["phase"]=="completed")
        await self.until(lambda: service.core.state == "IDLE")
        self.assertEqual(service.snapshot()["counts"]["produced"], 2)
        self.assertEqual(len(service.records), 1)

    async def test_rejections_keep_identity_and_validate_bounds_without_effects(self):
        service, client, _ = await self.service()
        body = self.request(service, "start", batch_size=65)
        first = await client.post("/api/start", json=body)
        self.assertEqual(first.status_code, 422)
        self.assertEqual((await client.post("/api/start", json=body)).json(), first.json())
        self.assertEqual(service.core.state, "IDLE")
        response = await client.post("/api/start", json=self.request(service, "start"), headers={"Origin": "http://elsewhere.invalid"})
        self.assertEqual(response.status_code, 403)
        malformed = await client.post("/api/start",json=self.request(service,"start",full_policy=[]))
        self.assertEqual(malformed.status_code,422)
        response = await client.post("/api/start", content='{"cmd_id":"x","cmd_id":"y"}', headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)

    async def test_unknown_production_continue_retains_incomplete_counts(self):
        service, client, _ = await self.service("--drop-first-request")
        await self.command(service, client, "start")
        await self.until(lambda: service.core.state == "FAULT")
        await self.until(lambda: service.core._ready(service.core.a) and service.core._ready(service.core.b.client))
        await self.command(service, client, "reconcile")
        self.assertEqual(service.core.state, "FAULT")
        await self.command(service, client, "continue")
        await self.until(lambda: service.core.state == "IDLE")
        view = service.snapshot()
        self.assertEqual(view["batch"]["outcome"], "incomplete")
        self.assertEqual((view["counts"]["inspected"], view["counts"]["unresolved"]), (3, 1))
        self.assertEqual((view["counts"]["passed"], view["counts"]["failed"]), (2, 1))

    async def test_gateway_restart_exposes_old_scopes_and_closes_before_new_batch(self):
        old, client, _ = await self.service()
        await self.command(old, client, "start", batch_size=6, production_time_ms=100, inspection_time_ms=200)
        await self.command(old, client, "pause")
        await self.until(lambda: not old.core.active and not old.core.b.active)
        await old.shutdown()
        core=BatchGateway(old.factories["A"](), old.factories["B"](), queue_capacity=2,
                          full_policy="block", ledger_path=old.core.b.ledger.path)
        service=OperatorService(core,simulation=True,factories=old.factories)
        self.services.append(service)
        await service.start();await core.a.connect();await core.b.client.connect()
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(service)),base_url="http://test")
        self.http.append(client)
        current=service.snapshot();service.alive(self.owner,service.gateway_id,current["status_seq"])
        self.assertEqual(current["state"],"Fault")
        self.assertTrue(current["orphaned"]);self.assertTrue(current["can_close_orphans"])
        self.assertFalse(current["ready"])
        rejected=await client.post("/api/start",json=self.request(service,"start"))
        self.assertEqual(rejected.status_code,409)
        await self.command(service,client,"close_orphans")
        await self.until(lambda: service.snapshot()["ready"])
        view=service.snapshot();self.assertEqual(view["batch"]["outcome"],"none")
        self.assertEqual(view["counts"]["inspected"],0) # No invented reconstruction of old outcomes.

    async def test_duplicate_liveness_does_not_renew_lease_or_steal_live_owner(self):
        service, _, _=await self.service(lease_s=.15,keepalive=False)
        view=service.snapshot();service.alive(self.owner,service.gateway_id,view["status_seq"])
        self.assertFalse(service.alive("OP-second",service.gateway_id,view["status_seq"]))
        await asyncio.sleep(.1)
        service.alive(self.owner,service.gateway_id,view["status_seq"])
        await asyncio.sleep(.08)
        self.assertFalse(service.owner_live)
        service.alive("OP-second",service.gateway_id,service.snapshot()["status_seq"])
        self.assertEqual(service.owner,"OP-second")

    async def test_idle_restart_rebind_keeps_finished_batch_and_allows_new_start(self):
        from gateway.inspection.wire import Restarted
        service,client,_=await self.service()
        await self.command(service,client,"start",batch_size=1)
        await self.until(lambda: service.core.state=="IDLE")
        await self.until(lambda: service.snapshot()["control_pending"] is None)
        before=service.snapshot()
        service.core.a.link.failure=Restarted("Native injected new boot")
        aport=self.host("--new-boot")
        service.factories["A"]=lambda:AClient(f"socket://127.0.0.1:{aport}",policy=FAST)
        await self.command(service,client,"recover_a")
        after=service.snapshot()
        self.assertEqual(after["batch"],before["batch"])
        self.assertEqual(after["counts"],before["counts"])
        self.assertEqual(service.core.state,"IDLE")
        await self.until(lambda: service.snapshot()["ready"])
        await self.command(service,client,"start",batch_size=1)
        await self.until(lambda: service.core.state=="IDLE")
        self.assertNotEqual(service.core.b.batch_id,before["batch"]["id"])

    async def test_remote_origin_commands_and_raw_serial_evidence(self):
        from gateway.operator.evidence import EventLog
        capture=EventLog(Path(self.state_dir.name)/"station.local.jsonl")
        try:
            service,client,_=await self.service(evidence=capture)
            body=self.request(service,"start",batch_size=1)
            response=await client.post("/api/start",json=body,
                headers={"Host":"192.168.137.1:8080","Origin":"http://192.168.137.1:8080"})
            self.assertEqual(response.status_code,202)
            await self.until(lambda: service.lookup(body["cmd_id"])["phase"]=="completed")
            await self.until(lambda: service.core.state=="IDLE")
            await service.shutdown()
        finally: capture.close()
        records=[json.loads(line) for line in capture.path.read_text().splitlines()]
        self.assertTrue(any(r["event"]=="serial_tx" for r in records))
        self.assertTrue(any(r["event"]=="serial_rx" for r in records))
        for station in ("A","B"):
            self.assertTrue(any(r["station"]==station and r["event"]=="receive" and r["data"].get("type")=="COMPLETED" for r in records))
        self.assertIsNone(capture.error)

    async def test_real_websocket_full_snapshots_acknowledged_lease_and_http_command(self):
        service, _, app = await self.service(start_monitor=False, keepalive=False)
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on"))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            await self.until(lambda: server.started)
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws/status", origin=f"http://127.0.0.1:{port}") as ws:
                snapshot = json.loads(await ws.recv())
                await ws.send(json.dumps({"type": "alive", "operator_id": self.owner, "gateway_id": service.gateway_id, "status_seq": snapshot["status_seq"]}))
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http:
                    body = self.request(service, "start", batch_size=1)
                    self.assertEqual((await http.post("/api/start", json=body)).status_code, 202)
                newer = json.loads(await ws.recv())
                self.assertGreater(newer["status_seq"], snapshot["status_seq"])
                self.assertEqual(newer["operator"]["controller_id"], self.owner)
                await ws.send("null")
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    while True: await asyncio.wait_for(ws.recv(),2)
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 8)
