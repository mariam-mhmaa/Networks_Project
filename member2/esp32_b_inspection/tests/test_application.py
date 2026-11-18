"""Actual B C firmware application over loopback, plus its real Python gateway.

No ESP32, flash, radio, A station, or operator UI is simulated as hardware proof.
"""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from gateway.inspection.client import BClient, Settings
from gateway.inspection.controller import Policy
from gateway.inspection.coordinator import GatewayFault, InspectionGateway
from gateway.inspection.wire import encode, receive, ProtocolError

FAST = Policy(receipt_s=.15, acceptance_s=.15, completion_allowance_s=.2,
              query_window_s=.15, absolute_allowance_s=1.5)


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="mct431-b-app-")
        cls.addClassCleanup(cls.scratch.cleanup)
        build = Path(cls.scratch.name)
        cls.exe = build / "inspection_host.exe"
        files = [ROOT / "main" / name for name in (
            "tcp_frames.c", "tcp_service.c", "inspection_app.c", "inspection_protocol.c",
            "vendor/cjson/cJSON.c")] + [ROOT / "tests/application_host.c"]
        args = ["cl", "/nologo", "/TC", "/std:c11", "/W4", "/WX",
                "/D_CRT_SECURE_NO_WARNINGS", "/DCJSON_NESTING_LIMIT=8",
                "/DCJSON_HIDE_SYMBOLS", "/I" + str(ROOT / "main"),
                *map(str, files), "/Fe" + str(cls.exe), "/link", "ws2_32.lib", "bcrypt.lib"]
        vcvars = r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
        (build / "compile.cmd").write_text(
            f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n' +
            subprocess.list2cmdline(args) + "\nexit /b %errorlevel%\n", encoding="utf-8")
        result = subprocess.run(["cmd.exe", "/d", "/c", "compile.cmd"], cwd=build,
                                capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    async def asyncSetUp(self):
        self.processes, self.clients, self.gateways, self.writers = [], [], [], []

    async def asyncTearDown(self):
        for gateway in self.gateways:
            await gateway.shutdown()
        for client in self.clients:
            await client.close()
        for writer in self.writers:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def host(self, *faults):
        process = subprocess.Popen([str(self.exe), *faults], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return int(process.stdout.readline())

    async def client(self, *faults, duration=40):
        port = self.host(*faults)
        client = BClient("127.0.0.1", port, policy=FAST)
        self.clients.append(client)
        status = await client.connect()
        client.select_run("batch-test", status["run_no"] + 1)
        configured = await client.configure(Settings(duration, 3, -1))
        self.assertEqual(configured.state, "COMPLETED", configured.reason)
        return client, port

    async def raw(self, port):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        self.writers.append(writer)
        heartbeat = await asyncio.wait_for(receive(reader), 1)
        self.assertEqual(heartbeat["type"], "HEARTBEAT")
        return reader, writer

    async def until(self, reader, identifier, stage):
        while True:
            message = await asyncio.wait_for(receive(reader), 2)
            if message.get("job_id", message.get("cmd_id")) == identifier and message["type"] == stage:
                return message

    async def test_normal_configuration_inspection_and_separate_evidence(self):
        client, _ = await self.client()
        outcome = await client.inspect(1)
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.result["verdict"], "FAIL")  # (1-1) % 3
        self.assertGreaterEqual(outcome.result["elapsed_ms"], 40)
        self.assertIsNotNone(outcome.evidence.received_observed_at)
        self.assertIsNotNone(outcome.evidence.accepted_observed_at)
        self.assertIsNotNone(outcome.evidence.completed_observed_at)

    async def test_both_acknowledgements_lost_execution_and_completion_continue(self):
        client, _ = await self.client("--drop-receipt", "--drop-acceptance")
        outcome = await client.inspect(2)
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.result["verdict"], "PASS")
        self.assertIsNone(outcome.evidence.received_observed_at)
        self.assertIsNone(outcome.evidence.accepted_observed_at)
        self.assertEqual(outcome.evidence.acceptance_established_by, "COMPLETED")
        self.assertEqual(outcome.evidence.request_attempts, 1)

    async def test_configuration_ack_loss_recovered_without_reapplying_settings(self):
        client, _ = await self.client("--drop-configuration")
        self.assertEqual(client.config_version, 1)
        outcome = await client.inspect(1)
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.result["config_version"], 1)

    async def test_close_ack_loss_recovered_without_reopening_old_run(self):
        client, _ = await self.client("--drop-close")
        outcome = await client.close_run()
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.evidence.query_attempts, 1)
        client.select_run("batch-two", 2)
        self.assertEqual((await client.configure(Settings(10, 2, 0))).state, "COMPLETED")

    async def test_missing_completion_recovered_by_read_only_query(self):
        client, _ = await self.client("--drop-completion")
        outcome = await client.inspect(1)
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.evidence.query_attempts, 1)
        self.assertIsNone(outcome.evidence.completed_observed_at)
        self.assertEqual(outcome.evidence.request_attempts, 1)

    async def test_blocked_ack_and_completion_transmitter_never_blocks_execution(self):
        client, _ = await self.client("--block-inspection-tx")
        outcome = await client.inspect(1)
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.result["verdict"], "FAIL")
        self.assertIsNone(outcome.evidence.received_observed_at)
        self.assertIsNone(outcome.evidence.accepted_observed_at)
        self.assertEqual(outcome.evidence.query_attempts, 1)

    async def test_retry_during_active_job_does_not_restart_timer_or_execute_twice(self):
        client, _ = await self.client("--drop-receipt", "--drop-acceptance", duration=400)
        outcome = await client.inspect(2)
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.evidence.request_attempts, 2)
        self.assertEqual(outcome.evidence.acceptance_established_by, "DUPLICATE_IN_PROGRESS")
        self.assertIsNone(outcome.evidence.accepted_observed_at)
        self.assertLess(outcome.result["elapsed_ms"], 550)
        await asyncio.sleep(.55)
        self.assertEqual(client.link.heartbeat["executions"], 1)

    async def test_query_unknown_does_not_create_work(self):
        client, _ = await self.client()
        outcome = await client.query("unknown-job")
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertIsNone(outcome.result["target"])
        normal = await client.inspect(3)
        self.assertEqual(normal.state, "COMPLETED")

    async def test_busy_configuration_rejected_and_active_settings_frozen(self):
        client, _ = await self.client(duration=150)
        job = asyncio.create_task(client.inspect(4))
        await asyncio.sleep(.05)
        busy = await client.configure(Settings(1, 7, 42))
        self.assertEqual(busy.state, "REJECTED", busy.reason)
        self.assertEqual(busy.reason, "BUSY")
        outcome = await job
        self.assertEqual(outcome.result["settings"], Settings(150, 3, -1).fields())
        self.assertGreaterEqual(outcome.result["elapsed_ms"], 150)

    async def test_duplicate_same_job_replays_result_once(self):
        client, _ = await self.client()
        job_id = client.ids.new("INSP")
        first = await client.inspect(4, identifier=job_id)
        second = await client.inspect(4, identifier=job_id)
        self.assertEqual(first.result, second.result)
        await asyncio.sleep(.55)
        self.assertEqual(client.link.heartbeat["executions"], 1)

    async def test_changed_contents_same_id_is_conflict_and_does_not_execute(self):
        client, _ = await self.client()
        job_id = client.ids.new("INSP")
        first = await client.inspect(2, identifier=job_id)
        changed = await client.inspect(3, identifier=job_id)
        self.assertEqual(first.state, "COMPLETED")
        self.assertEqual(changed.state, "UNRESOLVED")
        self.assertIn("ID_CONFLICT", changed.reason)

    async def test_fresh_id_cannot_reinspect_same_part(self):
        client, _ = await self.client()
        self.assertEqual((await client.inspect(2)).state, "COMPLETED")
        duplicate_part = await client.inspect(2)
        self.assertEqual(duplicate_part.state, "REJECTED")
        self.assertEqual(duplicate_part.reason, "PART_ALREADY_ACCEPTED")

    async def test_disconnect_during_execution_recovers_original_cached_result(self):
        client, port = await self.client(duration=160)
        request = client.inspection(8)
        # Use actual adapter send to submit once, then deliberately lose TCP.
        await client.link.send(request, encode(request))
        await asyncio.sleep(.05)
        await client.link.close()
        await asyncio.sleep(.2)
        client.link.failure = None
        recovered = await client.controller.run(request, duration_ms=160,
                                                 expected_settings=client.settings.fields())
        self.assertEqual(recovered.state, "COMPLETED", recovered.reason)
        await asyncio.sleep(.55)
        self.assertEqual(client.link.heartbeat["executions"], 1)

    async def test_rejection_is_retained_and_requires_new_id(self):
        client, _ = await self.client(duration=120)
        job = asyncio.create_task(client.inspect(4))
        await asyncio.sleep(.04)
        request = client.request("CONFIGURE", **Settings(20, 5, 0).fields())
        first = await client.controller.run(request)
        await job
        second = await client.controller.run(request)
        self.assertEqual(first.state, "REJECTED")
        self.assertEqual(second.state, "REJECTED")
        self.assertEqual(first.reason, second.reason)
        self.assertEqual((await client.configure(Settings(20, 5, 0))).state, "COMPLETED")

    async def test_signed_rule_arithmetic_and_maximum_part_id(self):
        client, _ = await self.client()
        self.assertEqual((await client.configure(Settings(10, 2147483647, -2147483648))).state,
                         "COMPLETED")
        outcome = await client.inspect(4294967295)
        self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
        self.assertEqual(outcome.result["verdict"], "FAIL")

    async def test_old_run_rejected_after_close_and_new_configuration(self):
        client, _ = await self.client()
        old = client.inspection(9)
        self.assertEqual((await client.close_run()).state, "COMPLETED")
        client.select_run("batch-two", client.run_no + 1)
        self.assertEqual((await client.configure(Settings(10, 3, 0))).state, "COMPLETED")
        outcome = await client.controller.run(old, duration_ms=40)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertIn("STALE_SCOPE", outcome.reason)
        current = await client.inspect(9)
        self.assertEqual(current.state, "COMPLETED", current.reason)

    async def test_bad_boot_cannot_initiate_work(self):
        client, _ = await self.client()
        request = client.inspection(7)
        request["boot_id"] = "f" * 32
        outcome = await client.controller.run(request, duration_ms=40)
        self.assertEqual(outcome.state, "UNRESOLVED")
        self.assertEqual((await client.query(request["job_id"])).result["target"], None)

    async def test_invalid_settings_rejected_without_affecting_active_configuration(self):
        client, _ = await self.client()
        request = client.request("CONFIGURE", inspection_time_ms=20, N=0, K=1)
        outcome = await client.controller.run(request)
        self.assertEqual(outcome.state, "REJECTED", outcome.reason)
        self.assertEqual((await client.inspect(1)).result["settings"], Settings(40, 3, -1).fields())

    async def test_first_invalid_configuration_is_cached_queryable_and_cannot_be_corrected_under_same_id(self):
        port = self.host()
        client = BClient("127.0.0.1", port, policy=FAST)
        self.clients.append(client)
        await client.connect()
        client.select_run("batch-test", 1)
        invalid = client.request("CONFIGURE", inspection_time_ms=10, N=0, K=0)
        rejected = await client.controller.run(invalid)
        self.assertEqual(rejected.state, "REJECTED")
        status = await client.query(invalid["cmd_id"])
        self.assertEqual(status.state, "COMPLETED", status.reason)
        self.assertEqual(status.result["target"]["state"], "REJECTED")
        configured = await client.configure(Settings(10, 2, 0))
        self.assertEqual(configured.state, "COMPLETED", configured.reason)
        changed = {**invalid, "N": 2}
        conflict = await client.controller.run(changed)
        self.assertEqual(conflict.state, "UNRESOLVED")
        self.assertIn("ID_CONFLICT", conflict.reason)

    async def test_full_job_history_preserves_results_and_does_not_accept_more(self):
        client, _ = await self.client(duration=1)
        first_id = None
        for part_id in range(1, 65):
            outcome = await client.inspect(part_id)
            self.assertEqual(outcome.state, "COMPLETED", outcome.reason)
            first_id = first_id or outcome.identifier
        full = await client.inspect(65)
        self.assertEqual(full.state, "UNRESOLVED")
        self.assertIn("HISTORY_FULL", full.reason)
        cached = await client.query(first_id)
        self.assertEqual(cached.result["target"]["state"], "COMPLETED")
        self.assertEqual((await client.close_run()).state, "COMPLETED")

    async def test_semantically_identical_key_order_is_not_an_id_conflict(self):
        client, _ = await self.client()
        request = client.inspection(4)
        first = await client.controller.run(request, duration_ms=40)
        queue = asyncio.Queue()
        client.link.route(request["job_id"], queue)
        try:
            reversed_message = dict(reversed(list(request.items())))
            body = json.dumps(reversed_message, indent=1).encode("utf-8")
            client.link.writer.write(struct.pack(">I", len(body)) + body)
            await client.link.writer.drain()
            message = await asyncio.wait_for(queue.get(), 1)
            self.assertEqual(message["type"], "COMPLETED")
            self.assertEqual(first.result, message["result"])
        finally:
            client.link.unroute(request["job_id"])

    async def test_malformed_untrusted_envelopes_close_without_execution(self):
        for body in (b'{"v":1,"v":1}', b'{"v":1.}', b'{"v":01}', b'{"v":1}\x0b',
                     b'{"v":1,"x":"\xff"}', b'{"v":1,"x":"\\u0000suffix"}'):
            port = self.host()
            reader, writer = await self.raw(port)
            writer.write(struct.pack(">I", len(body)) + body)
            await writer.drain()
            try:
                self.assertEqual(await asyncio.wait_for(reader.read(1), 1), b"")
            except ConnectionResetError:
                pass

    async def test_queue_reservations_and_batch_accounting(self):
        port = self.host()
        client = BClient("127.0.0.1", port, policy=FAST)
        self.clients.append(client)
        with tempfile.TemporaryDirectory() as local:
            gateway = InspectionGateway(client, queue_capacity=1, full_policy="block",
                                        ledger_path=Path(local) / "state.sqlite3")
            self.gateways.append(gateway)
            await gateway.start_run(Settings(20, 2, 0), 4)
            tickets = []
            for _ in range(4):
                part = await gateway.reserve_part()
                tickets.append(part)
                await gateway.produced(part)
                self.assertFalse(await gateway.produced(part))
            snapshot = await asyncio.wait_for(gateway.wait_inspection(), 3)
            self.assertEqual(snapshot["pass"] + snapshot["fail"], 4)
            self.assertEqual({t.part_id for t in tickets}, {1, 2, 3, 4})
            self.assertEqual(snapshot["pass"], 2)
            self.assertEqual(snapshot["fail"], 2)
            self.assertEqual((await gateway.close_run()).state, "COMPLETED")
            # The same core can start another batch; durable IDs don't reset.
            await gateway.start_run(Settings(10, 2, 0), 1)
            next_part = await gateway.reserve_part()
            self.assertEqual(next_part.part_id, 5)
            await gateway.produced(next_part)
            await gateway.wait_inspection()
            await gateway.close_run()

    async def test_queue_full_fault_policy_preserves_unissued_reservation(self):
        port = self.host()
        client = BClient("127.0.0.1", port, policy=FAST)
        self.clients.append(client)
        with tempfile.TemporaryDirectory() as local:
            gateway = InspectionGateway(client, queue_capacity=1, full_policy="fault",
                                        ledger_path=Path(local) / "state.sqlite3")
            self.gateways.append(gateway)
            await gateway.start_run(Settings(20, 2, 0), 2)
            first = await gateway.reserve_part()
            with self.assertRaises(GatewayFault):
                await gateway.reserve_part()
            self.assertEqual(gateway.snapshot()["state"], "FAULT")
            self.assertFalse(first.dispatched)
            self.assertTrue(await gateway.produced(first))
            self.assertEqual(gateway.snapshot()["queued"], 1)
            self.assertEqual(gateway.snapshot()["pass"] + gateway.snapshot()["fail"], 0)
            await gateway.shutdown()

    async def test_fault_during_request_persistence_prevents_new_dispatch(self):
        port = self.host()
        client = BClient("127.0.0.1", port, policy=FAST)
        self.clients.append(client)
        with tempfile.TemporaryDirectory() as local:
            gateway = InspectionGateway(client, queue_capacity=1, full_policy="block",
                                        ledger_path=Path(local) / "state.sqlite3")
            self.gateways.append(gateway)
            await gateway.start_run(Settings(20, 2, 0), 1)
            entered, release = asyncio.Event(), asyncio.Event()
            original = gateway.ledger.record
            async def record(kind, body):
                if kind == "inspection_request":
                    entered.set()
                    await release.wait()
                await original(kind, body)
            gateway.ledger.record = record
            part = await gateway.reserve_part()
            await gateway.produced(part)
            await asyncio.wait_for(entered.wait(), 1)
            await gateway._fault("injected fault before network submission")
            release.set()
            await asyncio.sleep(.6)
            self.assertFalse(part.dispatched)
            self.assertEqual(gateway.snapshot()["queued"], 1)
            self.assertEqual(client.link.heartbeat["executions"], 0)
            await gateway.resume_after_reconciliation()
            await asyncio.wait_for(gateway.wait_inspection(), 2)
            self.assertEqual((await gateway.close_run()).state, "COMPLETED")

    async def test_explicit_reconciliation_counts_once_and_does_not_resume_dispatch(self):
        port = self.host("--drop-completion")
        policy = replace(FAST, queries=0)
        client = BClient("127.0.0.1", port, policy=policy)
        self.clients.append(client)
        with tempfile.TemporaryDirectory() as local:
            gateway = InspectionGateway(client, queue_capacity=1, full_policy="block",
                                        ledger_path=Path(local) / "state.sqlite3")
            self.gateways.append(gateway)
            await gateway.start_run(Settings(20, 2, 0), 1)
            part = await gateway.reserve_part()
            await gateway.produced(part)
            outcome = await asyncio.wait_for(part.future, 2)
            self.assertEqual(outcome.state, "UNRESOLVED")
            self.assertEqual(gateway.snapshot()["state"], "FAULT")
            self.assertEqual(gateway.snapshot()["pass"] + gateway.snapshot()["fail"], 0)
            recovered = await gateway.reconcile(part.job_id)
            self.assertEqual(recovered.state, "COMPLETED")
            self.assertEqual(gateway.snapshot()["state"], "FAULT")
            self.assertEqual(gateway.snapshot()["pass"] + gateway.snapshot()["fail"], 1)
            await asyncio.sleep(.55)
            await gateway.resume_after_reconciliation()
            self.assertEqual((await gateway.close_run()).state, "COMPLETED")

    async def test_incomplete_close_fences_unissued_work_before_next_run(self):
        port = self.host()
        client = BClient("127.0.0.1", port, policy=FAST)
        self.clients.append(client)
        with tempfile.TemporaryDirectory() as local:
            gateway = InspectionGateway(client, queue_capacity=1, full_policy="fault",
                                        ledger_path=Path(local) / "state.sqlite3")
            self.gateways.append(gateway)
            await gateway.start_run(Settings(20, 2, 0), 2)
            part = await gateway.reserve_part()
            with self.assertRaises(GatewayFault):
                await gateway.reserve_part()
            await asyncio.sleep(.55)
            self.assertEqual((await gateway.close_incomplete()).state, "COMPLETED")
            self.assertEqual((await part.future).state, "NOT_DISPATCHED")
            await gateway.start_run(Settings(20, 2, 0), 1)
            new = await gateway.reserve_part()
            self.assertNotEqual(new.batch_id, part.batch_id)
            self.assertGreater(new.part_id, part.part_id)
            await gateway.produced(new)
            await gateway.wait_inspection()
            await gateway.close_run()

    async def test_standalone_functional_cli_uses_real_b_application(self):
        port = self.host()
        with tempfile.TemporaryDirectory() as local:
            command = [sys.executable, "-B", "-m", "gateway.inspection", "127.0.0.1",
                       "--port", str(port), "--parts", "3", "--inspection-ms", "20",
                       "--rule-n", "2", "--rule-k", "0", "--queue-capacity", "1",
                       "--full-policy", "block", "--state-file", str(Path(local)/"cli.sqlite3"),
                       "--events", str(Path(local)/"events.jsonl")]
            result = await asyncio.to_thread(subprocess.run, command, cwd=ROOT.parents[1],
                                             capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["batch"]["pass"] + report["batch"]["fail"], 3)
            self.assertIn("simulated", report["scope"])
            events = [json.loads(line) for line in (Path(local)/"events.jsonl").read_text().splitlines()]
            self.assertIn("send", {event["kind"] for event in events})
            self.assertIn("receive", {event["kind"] for event in events})

    async def test_conflicting_late_verdict_stops_dispatch_without_overwriting_original(self):
        port = self.host("--conflicting-completion")
        client = BClient("127.0.0.1", port, policy=FAST)
        self.clients.append(client)
        with tempfile.TemporaryDirectory() as local:
            gateway = InspectionGateway(client, queue_capacity=1, full_policy="block",
                                        ledger_path=Path(local) / "state.sqlite3")
            self.gateways.append(gateway)
            await gateway.start_run(Settings(20, 2, 0), 1)
            part = await gateway.reserve_part()
            await gateway.produced(part)
            first = await asyncio.wait_for(part.future, 2)
            await asyncio.sleep(.2)
            self.assertEqual(gateway.state, "FAULT")
            original = first.result["verdict"]
            self.assertEqual(original, "PASS")
            self.assertLessEqual(gateway.accepted + gateway.rejected, 1)
            recovered = await gateway.reconcile(part.job_id)
            self.assertEqual(recovered.result["verdict"], original)
            self.assertEqual(gateway.accepted + gateway.rejected, 1)
            await gateway.shutdown()

    async def test_retirement_unknown_fences_job_and_part_without_inspection(self):
        client,_=await self.client()
        identifier=client.ids.new("INSP")
        retired=await client.retire(identifier,22)
        self.assertEqual(retired.state,"COMPLETED",retired.reason)
        self.assertEqual(retired.result["target"]["error"],"RETIRED")
        old=await client.inspect(22,identifier=identifier)
        self.assertEqual(old.reason,"RETIRED")
        other=await client.inspect(22)
        self.assertEqual(other.reason,"PART_ALREADY_ACCEPTED")
        self.assertEqual((await client.inspect(23)).state,"COMPLETED")

    async def test_retirement_returns_real_verdict_or_busy_without_cancelling(self):
        client,_=await self.client(duration=120)
        identifier=client.ids.new("INSP")
        task=asyncio.create_task(client.inspect(7,identifier=identifier))
        await asyncio.sleep(.04)
        busy=await client.retire(identifier,7)
        self.assertEqual(busy.reason,"BUSY")
        original=await task
        recovered=await client.retire(identifier,7)
        self.assertEqual(recovered.state,"COMPLETED",recovered.reason)
        self.assertEqual(recovered.result["target"],original.result)

    async def test_retirement_capacity_preserves_64_fences_and_close_slot(self):
        client,_=await self.client()
        for part in range(1,65):
            out=await client.retire(client.ids.new("INSP"),part)
            self.assertEqual(out.state,"COMPLETED",out.reason)
        self.assertEqual((await client.close_run()).state,"COMPLETED")
        client.select_run("next-run",2)
        self.assertEqual((await client.configure(Settings(1,3,0))).state,"COMPLETED")
        self.assertEqual((await client.inspect(65)).state,"COMPLETED")
