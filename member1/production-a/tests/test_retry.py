import heapq
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pc_test"))
from retry import RetryController,RetryPolicy
from session import SessionFault
from protocol import encode_atr
from gateway_client import ProductionRun,RetryStopped

BOOT="a"*32

def request(n=1,config=False):
    if config: return dict(type="CONFIGURE_PRODUCTION",boot_id=BOOT,op_no=n,cmd_id=f"cfg:{n}",production_time_ms=500)
    return dict(type="PRODUCE_PART",boot_id=BOOT,op_no=n,job_id=f"job:{n}",batch_id="batch",part_id=n)


class FakeClient:
    def __init__(self,handler=None,fault_at=None,fault="RESTART"):
        self.now=0.0; self.seq=100; self.queue=[]; self.serial=0; self.sent=[]
        self.report={"retry_operations":[]}; self.handler=handler; self.fault_at=fault_at
        owner=self
        class Guard:
            boot_id=BOOT; available=True
            def require_send(self):
                if owner.fault_at is not None and owner.now>=owner.fault_at:
                    self.fault=fault; self.available=False; raise SessionFault(fault)
        self.receiver=type("Receiver",(),{})(); self.receiver.guard=Guard()

    def emit(self,at,seq,req,kind,**extra):
        event={k:v for k,v in req.items() if k not in ("type","production_time_ms")}
        event.update(type=kind,**extra)
        self.serial+=1
        raw=encode_atr(0,seq,json.dumps(event).encode())
        item=dict(test_id=0,seq=seq,event=event,monotonic=at,atr_hex=raw.hex(" "))
        heapq.heappush(self.queue,(at,self.serial,item))

    def send(self,req,write_deadline=None):
        self.seq+=1; self.sent.append((self.now,self.seq,json.loads(json.dumps(req))))
        if self.handler: self.handler(self,req,self.seq)
        return self.seq

    def next(self,timeout,strict_session=True):
        end=self.now+timeout
        if self.queue and self.queue[0][0]<=end:
            at,_,item=heapq.heappop(self.queue); self.now=max(self.now,at); return item
        self.now=end
        return None


class RetryTests(unittest.TestCase):
    def engine(self,client,**kw): return RetryController(client,clock=lambda:client.now,**kw)

    def test_no_loss_no_retries(self):
        def reply(c,r,s):
            c.emit(c.now+.01,s,r,"ACCEPTED")
            c.emit(c.now+.2,s,r,"PART_PRODUCED",replayed=False)
        c=FakeClient(reply); engine=self.engine(c)
        out=engine.execute(request(),200)
        self.assertEqual(out["outcome"],"COMPLETED"); self.assertEqual(len(c.sent),1)
        self.assertEqual(engine.completion_count,1)

    def test_acceptance_loss_running_and_original_sequence(self):
        def reply(c,r,s):
            if len(c.sent)==1:
                c.emit(.01,s,r,"ACCEPTED"); c.emit(1.8,s,r,"PART_PRODUCED",replayed=False)
            else: c.emit(c.now+.01,s,r,"OPERATION_RUNNING")
        c=FakeClient(reply); engine=self.engine(c,omit=lambda i,a:i["event"]["type"]=="ACCEPTED")
        out=engine.execute(request(),1800)
        self.assertEqual(out["outcome"],"COMPLETED"); self.assertEqual(len(c.sent),2)
        self.assertEqual(out["completion"]["seq"],c.sent[0][1])
        self.assertEqual(c.sent[0][2],c.sent[1][2]); self.assertNotEqual(c.sent[0][1],c.sent[1][1])

    def test_completion_loss_replays_immediately(self):
        def reply(c,r,s):
            if len(c.sent)==1:
                c.emit(.01,s,r,"ACCEPTED"); c.emit(.2,s,r,"PART_PRODUCED",replayed=False)
            else: c.emit(c.now+.01,s,r,"PART_PRODUCED",replayed=True)
        c=FakeClient(reply)
        out=self.engine(c,omit=lambda i,a:i["event"]["type"]=="PART_PRODUCED" and not i["event"]["replayed"]).execute(request(),200)
        self.assertEqual(out["outcome"],"COMPLETED"); self.assertAlmostEqual(c.now,1.21)
        self.assertTrue(out["completion"]["event"]["replayed"])

    def test_acceptance_and_completion_loss_share_one_retry_budget(self):
        def reply(c,r,s):
            if len(c.sent)==1:
                c.emit(.01,s,r,"ACCEPTED"); c.emit(1.8,s,r,"PART_PRODUCED",replayed=False)
            elif len(c.sent)==2: c.emit(c.now+.01,s,r,"OPERATION_RUNNING")
            else: c.emit(c.now+.01,s,r,"PART_PRODUCED",replayed=True)
        c=FakeClient(reply)
        def omit(item,attempt):
            event=item["event"]
            return event["type"]=="ACCEPTED" or (event["type"]=="PART_PRODUCED" and not event["replayed"])
        result=self.engine(c,omit=omit).execute(request(),1800)
        self.assertEqual(result["outcome"],"COMPLETED"); self.assertEqual(len(c.sent),3)
        self.assertAlmostEqual(c.now,2.81)

    def test_received_is_not_acceptance_budget_and_absolute_deadline(self):
        c=FakeClient(lambda c,r,s:c.emit(c.now+.01,s,r,"RECEIVED"))
        out=self.engine(c).execute(request(),200)
        self.assertEqual(out["outcome"],"UNRESOLVED"); self.assertFalse(out["accepted"])
        self.assertEqual(len(c.sent),3); self.assertAlmostEqual(c.now,3.2)
        self.assertEqual([round(i[0],2) for i in c.sent],[0,1,2])

    def test_repeated_running_never_moves_deadline(self):
        def reply(c,r,s):
            if len(c.sent)==1: c.emit(.01,s,r,"ACCEPTED")
            else:
                for n in range(1,101): c.emit(c.now+n*.02,s,r,"OPERATION_RUNNING")
        c=FakeClient(reply); out=self.engine(c).execute(request(),100)
        self.assertEqual(out["outcome"],"UNRESOLVED"); self.assertAlmostEqual(c.now,3.1)
        self.assertEqual(len(c.sent),3)

    def test_configuration_overall_deadline(self):
        c=FakeClient(); out=self.engine(c).execute(request(config=True))
        self.assertEqual(out["outcome"],"UNRESOLVED")
        self.assertEqual(len(c.sent),3); self.assertAlmostEqual(c.now,3.0)

    def test_config_historical_replay_and_completion_count_once(self):
        stored={}; state=[None]; ignore=[False]
        def reply(c,r,s):
            replay=r["op_no"] in stored
            if not replay: stored[r["op_no"]]=r["production_time_ms"]; state[0]=r["production_time_ms"]
            c.emit(c.now+.01,s,r,"PRODUCTION_CONFIGURED",production_time_ms=stored[r["op_no"]],replayed=replay)
        def omit(item,attempt):
            if ignore[0]: ignore[0]=False; return True
            return False
        c=FakeClient(reply); e=self.engine(c,omit=omit)
        old=request(1,True)
        newer=dict(request(2,True),production_time_ms=2500)
        applied_new=[False]
        def omit_with_new_configuration(item,attempt):
            if item["event"]["op_no"]==1 and not applied_new[0]:
                applied_new[0]=True
                self.engine(c).execute(newer)
                return True
            return False
        e.omit=omit_with_new_configuration
        result=e.execute(old)
        self.assertEqual(result["outcome"],"COMPLETED"); self.assertEqual(len(result["attempts"]),2)
        self.assertEqual(state[0],2500); self.assertTrue(result["new_logical_completion"])
        self.assertEqual(e.completion_count,1)
        again=e.execute(old)
        self.assertEqual(len(again["attempts"]),0)
        self.assertFalse(again["new_logical_completion"])

    def test_stopped_operation_cannot_acquire_a_new_budget(self):
        c=FakeClient(); e=self.engine(c); req=request()
        first=e.execute(req,200); count=len(c.sent)
        second=self.engine(c,ledger=e.ledger).execute(req,200)
        self.assertEqual(second["outcome"],"UNRESOLVED")
        self.assertEqual(len(c.sent),count)
        self.assertEqual(second["absolute_deadline"],first["absolute_deadline"])

    def test_restart_and_heartbeat_fault_stop_transmissions(self):
        for fault,at in (("RESTART",.5),("HEARTBEAT_TIMEOUT",5)):
            c=FakeClient(lambda c,r,s:c.emit(.01,s,r,"ACCEPTED"),fault_at=at,fault=fault)
            out=self.engine(c).execute(request(),7000)
            self.assertEqual(out["outcome"],"FAULT"); self.assertEqual(len(c.sent),1)

    def test_terminal_rejections_stop_immediately(self):
        for reason in ("OPERATION_CONFLICT","INVALID_CONFIGURATION","STALE_RESULT_UNAVAILABLE","SESSION_MISMATCH"):
            c=FakeClient(lambda c,r,s:c.emit(.01,s,r,"REJECTED",reason=reason))
            out=self.engine(c).execute(request(),200)
            self.assertEqual(out["outcome"],"REJECTED"); self.assertEqual(len(c.sent),1)

    def test_late_duplicate_and_old_session_frames_quarantined(self):
        old=request(); c=FakeClient()
        def reply(c,r,s):
            c.emit(c.now+.02,s,r,"PART_PRODUCED",replayed=False)
        c.handler=reply; e=self.engine(c); first=e.execute(old,200)
        c.emit(c.now+.001,first["completion"]["seq"],old,"PART_PRODUCED",replayed=False)
        c.emit(c.now+.002,999,dict(old,boot_id="b"*32),"PART_PRODUCED",replayed=True)
        second=e.execute(request(2),200)
        self.assertEqual(second["outcome"],"COMPLETED"); self.assertEqual(e.completion_count,2)
        self.assertEqual(sum(t["event"]=="QUARANTINED_RESPONSE" for t in second["trace"]),2)

    def test_unresolved_gateway_operation_disarms_run(self):
        c=FakeClient(); e=self.engine(c)
        run=ProductionRun(None,c.report); run.client=c; run.controller=e
        run.configured=run.started=True; run.production_time_ms=200
        with self.assertRaises(RetryStopped): run.produce(1,"job:1","batch",1)
        self.assertFalse(run.started); self.assertFalse(run.configured)

    def test_policy_validation_and_local_identity_conflict(self):
        with self.assertRaises(ValueError): RetryPolicy(max_retries=True)
        with self.assertRaises(ValueError): RetryPolicy(saved_result_wait=float("nan"))
        c=FakeClient(); e=self.engine(c)
        e.execute(request(),200)
        sent=len(c.sent); out=e.execute(dict(request(),part_id=2),200)
        self.assertEqual(out["reason"],"LOCAL_OPERATION_CONFLICT"); self.assertEqual(len(c.sent),sent)
