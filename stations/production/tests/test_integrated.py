"""New integrated A protocol, real C over ATR/CRC/SLIP and actual Python gateway."""
import asyncio
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from gateway.production.client import AClient,ProductionSettings
from gateway.production.coordinator import BatchGateway
from gateway.inspection.client import BClient,Settings
from gateway.inspection.controller import Policy
from gateway.inspection.coordinator import GatewayFault
FAST=Policy(receipt_s=.15,acceptance_s=.15,completion_allowance_s=.25,query_window_s=.15,absolute_allowance_s=1.8)

class IntegratedTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch=tempfile.TemporaryDirectory(prefix="mct431-a-integrated-")
        cls.addClassCleanup(cls.scratch.cleanup)
        build=Path(cls.scratch.name); cls.exe=build/"production_host.exe"
        A=ROOT/"stations/production/firmware/main"; S=ROOT/"shared/station"
        files=[A/"protocol.c",A/"serial_service.c",S/"station_app.c",S/"station_protocol.c",S/"vendor/cjson/cJSON.c",ROOT/"stations/production/tests/integrated_host.c"]
        args=["cl","/nologo","/TC","/std:c11","/W4","/WX","/D_CRT_SECURE_NO_WARNINGS","/DCJSON_NESTING_LIMIT=8","/DCJSON_HIDE_SYMBOLS","/I"+str(A),*map(str,files),"/Fe"+str(cls.exe),"/link","ws2_32.lib","bcrypt.lib"]
        vcvars=r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
        (build/"compile.cmd").write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'+subprocess.list2cmdline(args)+"\nexit /b %errorlevel%\n")
        result=subprocess.run(["cmd.exe","/d","/c","compile.cmd"],cwd=build,capture_output=True,text=True,timeout=90)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        # Reuse B's real portable C harness, not an invented Python verdict peer.
        sys.path.insert(0,str(ROOT/"stations/inspection/tests"))
        from test_application import ApplicationTests
        ApplicationTests.setUpClass()
        cls.bexe=ApplicationTests.exe
        cls.addClassCleanup(ApplicationTests.doClassCleanups)

    async def asyncSetUp(self):
        self.processes=[]; self.clients=[]; self.batches=[]
        self.state_dir=tempfile.TemporaryDirectory(prefix="mct431-batch-state-")
        self.addCleanup(self.state_dir.cleanup)
    async def asyncTearDown(self):
        for batch in self.batches: await batch.shutdown()
        for client in self.clients: await client.close()
        for process in self.processes:
            if process.poll() is None: process.terminate()
            process.wait(timeout=5); process.stdout.close(); process.stderr.close()

    def host(self,*flags,inspection=False):
        process=subprocess.Popen([str(self.bexe if inspection else self.exe),*flags],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.processes.append(process)
        line=process.stdout.readline()
        if not line: raise RuntimeError(process.stderr.read())
        return int(line)
    async def client(self,*flags,duration=60):
        a=AClient(f"socket://127.0.0.1:{self.host(*flags)}",policy=FAST)
        self.clients.append(a); heartbeat=await a.connect()
        a.select_run("batch-a",heartbeat["run_no"]+1)
        out=await a.configure(ProductionSettings(duration))
        self.assertEqual(out.state,"COMPLETED",out.reason)
        return a
    async def batch(self,*flags,p=30,i=70,target=5,policy="block",bflags=()):
        a=AClient(f"socket://127.0.0.1:{self.host(*flags)}",policy=FAST)
        b=BClient("127.0.0.1",self.host(*bflags,inspection=True),policy=FAST)
        batch=BatchGateway(a,b,queue_capacity=2,full_policy=policy,ledger_path=Path(self.state_dir.name)/"ledger.sqlite3")
        self.batches.append(batch)
        await batch.start_run(ProductionSettings(p),Settings(i,3,0),target,batch_id="batch-integrated")
        return batch

    async def test_real_serial_production_lifecycle_and_no_verdict(self):
        a=await self.client(); out=await a.produce(4294967295)
        self.assertEqual(out.state,"COMPLETED",out.reason)
        self.assertTrue(out.result["produced"]); self.assertNotIn("verdict",out.result)
        self.assertGreaterEqual(out.result["elapsed_ms"],60)
        self.assertIsNotNone(out.evidence.accepted_observed_at)

    async def test_lost_acks_never_gate_production(self):
        a=await self.client("--drop-acks"); out=await a.produce(1)
        self.assertEqual(out.state,"COMPLETED",out.reason)
        self.assertIsNone(out.evidence.accepted_observed_at)
        self.assertIsNone(out.evidence.received_observed_at)

    async def test_completion_query_and_blocked_publication(self):
        a=await self.client("--block-tx"); out=await a.produce(3)
        self.assertEqual(out.state,"COMPLETED",out.reason)
        self.assertEqual(out.evidence.query_attempts,1)
        self.assertIsNone(out.evidence.completed_observed_at)

    async def test_retry_new_atr_sequence_same_job_no_reexecution(self):
        a=await self.client("--drop-acks",duration=400); out=await a.produce(3)
        self.assertEqual(out.state,"COMPLETED",out.reason)
        self.assertEqual(out.evidence.request_attempts,2)
        same=await a.produce(3,identifier=out.identifier)
        self.assertEqual(same.result,out.result)
        await asyncio.sleep(1.1); self.assertEqual(a.link.heartbeat["executions"],1)

    async def test_changed_part_same_production_id_does_not_execute_again(self):
        a=await self.client()
        original=await a.produce(7)
        self.assertEqual(original.state,"COMPLETED",original.reason)
        changed=await a.produce(8,identifier=original.identifier)
        self.assertEqual(changed.state,"UNRESOLVED")
        self.assertIn("ID_CONFLICT",changed.reason)
        await asyncio.sleep(1.1)  # A publishes its execution counter once per second.
        self.assertEqual(a.link.heartbeat["executions"],1)

    async def test_fresh_id_cannot_produce_same_part_again(self):
        a=await self.client()
        original=await a.produce(7)
        self.assertEqual(original.state,"COMPLETED",original.reason)
        duplicate=await a.produce(7)
        self.assertNotEqual(original.identifier,duplicate.identifier)
        self.assertEqual(duplicate.state,"REJECTED",duplicate.reason)
        self.assertEqual(duplicate.reason,"PART_ALREADY_ACCEPTED")
        await asyncio.sleep(1.1)
        self.assertEqual(a.link.heartbeat["executions"],1)

    async def test_retirement_active_busy_then_actual_completion(self):
        a=await self.client(duration=200)
        task=asyncio.create_task(a.produce(5)); await asyncio.sleep(.06)
        # Active original production is known to its caller before submission.
        identifier=next(k for k in a.link.routes if k.startswith("PROD-"))
        busy=await a.retire(identifier,5)
        self.assertEqual(busy.state,"REJECTED"); self.assertEqual(busy.reason,"BUSY")
        out=await task; retired=await a.retire(identifier,5)
        self.assertEqual(retired.state,"COMPLETED",retired.reason)
        self.assertEqual(retired.result["target"],out.result)

    async def test_retired_unknown_blocks_original_and_new_id_for_part(self):
        a=await self.client(); identifier=a.ids.new("PROD")
        retirement=await a.retire(identifier,9)
        self.assertEqual(retirement.state,"COMPLETED",retirement.reason)
        self.assertTrue(retirement.result["target"]["retired"])
        out=await a.produce(9,identifier=identifier)
        self.assertEqual(out.state,"REJECTED"); self.assertEqual(out.reason,"RETIRED")
        another=await a.produce(9)
        self.assertEqual(another.state,"REJECTED"); self.assertEqual(another.reason,"PART_ALREADY_ACCEPTED")
        self.assertEqual((await a.produce(10)).state,"COMPLETED")

    async def test_config_busy_frozen_settings_and_cached_rejection(self):
        a=await self.client(duration=250)
        task=asyncio.create_task(a.produce(8)); await asyncio.sleep(.06)
        req=a.request("CONFIGURE",production_time_ms=1)
        first=await a.controller.run(req); self.assertEqual(first.state,"REJECTED")
        out=await task; self.assertEqual(out.result["settings"],{"production_time_ms":250})
        repeated=await a.controller.run(req); self.assertEqual(repeated.reason,"BUSY")
        self.assertEqual((await a.query(req["cmd_id"])).result["target"]["state"],"REJECTED")

    async def test_full_batch_producer_faster_with_real_a_and_b(self):
        batch=await self.batch(); view=await asyncio.wait_for(batch.wait(),5)
        self.assertEqual((view["produced"],view["inspected"],view["pass"],view["fail"]),(5,5,4,1))
        self.assertEqual(view["outcome"],"COMPLETED")
        await asyncio.sleep(1.1)
        closed=await batch.close_run(); self.assertEqual(closed["state"],"IDLE")
        self.assertIsNone(closed["fault_reason"])

    async def test_full_batch_inspector_faster(self):
        batch=await self.batch(p=120,i=10,target=4)
        view=await asyncio.wait_for(batch.wait(),5)
        self.assertEqual((view["pass"],view["fail"],view["inspected"]),(3,1,4))

    async def test_same_batch_continue_unknown_production_no_replacement(self):
        batch=await self.batch("--drop-first-request",target=4)
        with self.assertRaises(GatewayFault): await asyncio.wait_for(batch.wait(),4)
        await asyncio.sleep(1.1)
        view=await batch.continue_remaining()
        self.assertEqual(view["state"],"RUNNING")
        view=await asyncio.wait_for(batch.wait(),5)
        self.assertEqual((view["reserved"],view["produced"],view["inspected"],view["unresolved"]),(4,3,3,1))
        self.assertEqual((view["pass"],view["fail"]),(2,1))
        await asyncio.sleep(1.1)
        closed=await batch.close_run(incomplete=True)
        self.assertEqual(closed["outcome"],"INCOMPLETE")
        self.assertEqual((closed["pass"],closed["fail"]),(2,1))

    async def test_retirement_reply_loss_recovers_cached_complete_control_result(self):
        a=await self.client("--drop-retirement")
        out=await a.retire(a.ids.new("PROD"),24)
        self.assertEqual(out.state,"COMPLETED",out.reason)
        self.assertEqual(out.evidence.query_attempts,1)
        self.assertEqual(out.result["target"]["error"],"RETIRED")

    async def test_maximum_length_ids_retirement_and_query_fit_wire_limit(self):
        a=await self.client()
        a.select_run("b"*96,1)
        # Reconfigure same run with original batch is forbidden: open a new
        # explicit scope to exercise the worst legal lengths.
        a.select_run("batch-a",1)
        self.assertEqual((await a.close_run()).state,"COMPLETED")
        a.select_run("b"*96,2)
        self.assertEqual((await a.configure(ProductionSettings(1))).state,"COMPLETED")
        req=a.request("RETIRE",identifier="c"*96,target_id="j"*96,part_id=4294967295)
        out=await a.controller.run(req)
        self.assertEqual(out.state,"COMPLETED",out.reason)
        queried=await a.query(req["cmd_id"])
        self.assertEqual(queried.state,"COMPLETED",queried.reason)
        result=a.controller._result(queried.result["target"],req,0)
        self.assertEqual(result,out.result)

    async def test_run_close_fences_old_serial_requests_and_allows_new_batch(self):
        a=await self.client(); request=a.production(1)
        self.assertEqual((await a.controller.run(request,duration_ms=60,expected_settings=a.settings.fields())).state,"COMPLETED")
        self.assertEqual((await a.close_run()).state,"COMPLETED")
        a.select_run("batch-second",2)
        self.assertEqual((await a.configure(ProductionSettings(1))).state,"COMPLETED")
        old=await a.controller.run(request,duration_ms=60,expected_settings={"production_time_ms":60})
        self.assertEqual(old.state,"UNRESOLVED")
        self.assertIn("STALE_SCOPE",old.reason)
        self.assertEqual((await a.produce(2)).state,"COMPLETED")

    async def test_same_batch_continue_unknown_inspection_preserves_other_verdicts(self):
        batch=await self.batch(target=4,bflags=("--drop-first-request",))
        with self.assertRaises(GatewayFault): await asyncio.wait_for(batch.wait(),4)
        await asyncio.sleep(1.1)
        await batch.continue_remaining()
        view=await asyncio.wait_for(batch.wait(),5)
        self.assertEqual((view["produced"],view["inspected"],view["unresolved"]),(4,3,1))
        self.assertEqual((view["pass"],view["fail"]),(2,1))

    async def test_lost_closure_reply_recovered_by_lookup_without_replaying_close(self):
        batch=await self.batch(target=2,bflags=("--drop-close",))
        await asyncio.wait_for(batch.wait(),5)
        await asyncio.sleep(1.1)
        # The shared controller's own read-only recovery confirms CLOSE.
        closed=await batch.close_run()
        self.assertEqual(closed["outcome"],"COMPLETED")
        self.assertEqual(batch.closures["B"][1].evidence.query_attempts,1)

    async def test_two_complete_batches_preserve_durable_part_sequence(self):
        batch=await self.batch(target=2)
        await asyncio.wait_for(batch.wait(),5); await asyncio.sleep(1.1)
        await batch.close_run()
        # Both physical-style station peers keep their framed links open
        # across explicit run closure; wait for the new idle heartbeat.
        await asyncio.sleep(1.1)
        await batch.start_run(ProductionSettings(10),Settings(10,3,0),2,batch_id="batch-two")
        await asyncio.wait_for(batch.wait(),5)
        self.assertEqual(sorted(batch.b.parts),[3,4])

    async def test_explicit_restart_fence_allows_incomplete_closure_without_old_result(self):
        batch=await self.batch("--drop-first-request",target=3)
        with self.assertRaises(GatewayFault): await asyncio.wait_for(batch.wait(),4)
        replacement=AClient(f"socket://127.0.0.1:{self.host('--new-boot')}",policy=FAST)
        self.clients.append(replacement)
        await batch.bind_restarted_station("A",replacement)
        with self.assertRaises(GatewayFault): await batch.continue_remaining()
        await asyncio.sleep(.6)
        view=await batch.close_run(incomplete=True)
        self.assertEqual(view["outcome"],"INCOMPLETE")
        self.assertEqual(view["unresolved"],1)

    async def test_real_cli_exercises_both_stations(self):
        port=self.host(); bport=self.host(inspection=True)
        process=await asyncio.create_subprocess_exec(sys.executable,"-B","-m","gateway.production",
            f"socket://127.0.0.1:{port}","127.0.0.1","--port",str(bport),"--parts","3",
            "--production-ms","20","--inspection-ms","40","--rule-n","3","--rule-k","0",
            "--queue-capacity","2","--full-policy","block","--state-file",str(Path(self.state_dir.name)/"cli.sqlite3"),
            cwd=ROOT,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await asyncio.wait_for(process.communicate(),15)
        self.assertEqual(process.returncode,0,stderr.decode()+stdout.decode())
        import json
        result=json.loads(stdout)
        self.assertEqual((result["outcome"],result["pass"],result["fail"]),("COMPLETED",2,1))

    async def test_partial_closure_recovers_cached_busy_before_new_explicit_close(self):
        batch=await self.batch(target=2,p=20,i=1000,bflags=("--drop-close",))
        # Gateway active means submitted/persisting, not receiver acceptance.
        # Wait for receiver evidence before injecting the BUSY close request.
        deadline=asyncio.get_running_loop().time()+2
        while batch.b.client.link.heartbeat["state"]!="BUSY":
            self.assertLess(asyncio.get_running_loop().time(),deadline)
            await asyncio.sleep(.01)
        request=batch.b.client.request("CLOSE")
        from gateway.inspection.controller import Evidence, Outcome
        # One immutable original attempt whose rejection replies are dropped.
        # Do not use the controller's query recovery yet: simulate the client
        # losing the exchange before its original finite budget was consumed.
        from gateway.inspection.wire import encode
        await batch.b.client.link.send(request,encode(request))
        batch.closures["B"]=(request,Outcome("UNRESOLVED",request["cmd_id"],None,Evidence(),"lost close reply"))
        await asyncio.wait_for(batch.wait(),5)
        await asyncio.sleep(1.1)
        with self.assertRaises(GatewayFault): await batch.close_run()
        self.assertEqual(batch.closures["A"][1].state,"COMPLETED")
        self.assertEqual(batch.closures["B"][1].state,"REJECTED")
        closed=await batch.close_run()
        self.assertEqual(closed["outcome"],"COMPLETED")

if __name__=="__main__": unittest.main()
