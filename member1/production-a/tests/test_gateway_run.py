import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pc_test"))
from gateway_client import ProductionRun
from session import SessionFault,SessionGuard
from test_session import status


class RunTests(unittest.TestCase):
    def test_local_old_configuration_cannot_arm_stale_setting(self):
        run=ProductionRun(None,{})
        class Controller:
            def execute(self,request):
                return dict(outcome="COMPLETED",local_result_only=True,
                            completion=dict(event=dict(replayed=False,production_time_ms=500)))
        class Client:
            def send(self,request,bind_session=False): return 10
            def next(self,timeout): return dict(seq=10,event=dict(type="STATUS",production_time_ms=1500))
        run.controller=Controller(); run.client=Client()
        class Dispatch:
            def read_status(self,timeout): return dict(event=dict(production_time_ms=1500))
        run.dispatch=Dispatch()
        run.configure(1,"cfg:1",500)
        self.assertFalse(run.configured); self.assertEqual(run.production_time_ms,1500)
        with self.assertRaises(SessionFault): run.start()

    def test_explicit_configuration_and_start_required(self):
        run=ProductionRun(None,{})
        with self.assertRaises(SessionFault): run.start()
        with self.assertRaises(SessionFault): run.produce(1,"job:1","batch",1)

    def test_observation_of_recovery_never_rearms_work(self):
        now=[0]
        guard=SessionGuard(lambda:now[0]); guard.bind(status("STATUS",n=0)); guard.observe(status())
        class Receiver:
            def pump(self,timeout): guard.check()
        receiver=Receiver(); receiver.guard=guard
        class Client: pass
        client=Client(); client.receiver=receiver
        run=ProductionRun(None,{}); run.client=client; run.configured=run.started=True
        now[0]=5; self.assertEqual(run.observe()["fault"],"HEARTBEAT_TIMEOUT")
        self.assertFalse(run.configured); self.assertFalse(run.started)
        guard.observe(status(n=2)); self.assertTrue(run.observe()["available"])
        self.assertFalse(run.configured); self.assertFalse(run.started)
