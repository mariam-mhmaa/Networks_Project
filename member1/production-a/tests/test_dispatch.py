import copy
import heapq
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pc_test"))
from dispatch import StationDispatch,StatusTimeout
from gateway_client import ProductionRun,ContinuationBlocked,OperationUnresolved
from session import SessionGuard,SessionFault
from retry import RetryController
from protocol import encode_atr
from production_test import Client

BOOT="a"*32
def job(n=1,part=None):
    return dict(type="PRODUCE_PART",boot_id=BOOT,op_no=n,job_id=f"job:{n}",batch_id="batch",part_id=n if part is None else part)
def status(state="IDLE",ms=500,boot=BOOT):
    return dict(type="STATUS",boot_id=boot,state=state,active_op_no=1 if state=="PRODUCING" else None,
                high_water=0 if state=="UNCONFIGURED" else 1,production_time_ms=ms,heartbeat_no=2)
def frame(seq,event,at):
    raw=encode_atr(0,seq,json.dumps(event).encode())
    return dict(test_id=0,seq=seq,event=event,monotonic=at,atr_hex=raw.hex(" "))

class TestClient:
    def __init__(self):
        self.now=0.; self.seq=100; self.sent=[]; self.queue=[]; self.serial=0
        self.report=dict(tx=[],events=[]); self.snapshot=status(); self.on_status=None
        self.receiver=type("Receiver",(),{})()
        self.receiver.pending=[]; self.receiver.expected_status=set()
        self.receiver.guard=SessionGuard(lambda:self.now)
        self.receiver.guard.bind(dict(self.snapshot,heartbeat_no=0))
        self.receiver.guard.observe(dict(self.snapshot,type="HEARTBEAT",heartbeat_no=2))
        self.snapshot["heartbeat_no"]=2
        self.complete_new_work=False

    def put(self,at,item):
        self.serial+=1; heapq.heappush(self.queue,(at,self.serial,item))

    def send(self,request,bind_session=True,write_deadline=None):
        self.seq+=1; self.sent.append(copy.deepcopy(request))
        if request["type"]=="GET_STATUS":
            self.receiver.expected_status.add(self.seq)
            if self.on_status: self.on_status(self,self.seq)
            else: self.put(self.now+.01,frame(self.seq,copy.deepcopy(self.snapshot),self.now+.01))
        elif self.complete_new_work:
            identity={k:v for k,v in request.items() if k!="type"}
            self.put(self.now+.01,frame(self.seq,dict(identity,type="ACCEPTED"),self.now+.01))
            self.put(self.now+.1,frame(self.seq,dict(identity,type="PART_PRODUCED",replayed=False),self.now+.1))
        return self.seq

    def next(self,timeout,strict_session=True):
        if self.receiver.pending: return self.receiver.pending.pop(0)
        end=self.now+timeout
        while self.queue and self.queue[0][0]<=end:
            at,_,item=heapq.heappop(self.queue); self.now=max(self.now,at)
            event=item["event"]
            if event.get("type") in ("HEARTBEAT","STATUS"):
                self.receiver.guard.observe(event,item["seq"])
                self.report.setdefault("status_events",[]).append(item)
                if event["type"]=="HEARTBEAT": continue
            return item
        self.now=end; self.receiver.guard.check()
        return None

class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.c=TestClient()
        self.e=RetryController(self.c,clock=lambda:self.c.now)
        self.original=self.e.execute(job(),200)
        self.assertEqual(self.original["outcome"],"UNRESOLVED")
        self.saved=copy.deepcopy(self.original)
        self.d=StationDispatch(self.c,self.e.ledger,clock=lambda:self.c.now)
        self.seq=self.original["attempts"][0]["seq"]

    def completion(self,seq=None,**change):
        event=dict(job(),type="PART_PRODUCED",replayed=False); event.update(change)
        return frame(self.seq if seq is None else seq,event,self.c.now+.005)

    def run_api(self):
        run=ProductionRun(None,self.c.report); run.client=self.c; run.controller=self.e
        run.ledger=self.e.ledger; run.dispatch=self.d; run.production_time_ms=500
        return run

    def test_correlated_status_interleaves_heartbeat_and_late_completion(self):
        def responses(c,seq):
            c.put(c.now+.001,frame(seq+99,status(),c.now+.001))
            c.put(c.now+.002,frame(0,dict(status(),type="HEARTBEAT",heartbeat_no=3),c.now+.002))
            c.put(c.now+.005,self.completion())
            c.put(c.now+.01,frame(seq,dict(status(),heartbeat_no=3),c.now+.01))
        self.c.on_status=responses
        snapshot=self.d.read_status(.2)
        self.assertEqual(snapshot["query_seq"],self.c.seq)
        self.assertEqual(self.d.confirmed_part_count,1)
        self.assertEqual(self.e.ledger.results[(BOOT,1)],self.saved)
        self.assertFalse(self.d.operation_evidence(1)["automatic_retry_allowed"])
        self.assertEqual(self.e.ledger.resolution_audit[-1]["type"],"PART_RESOLVED_LATE")
        before=len(self.c.sent); again=self.e.execute(job(),200)
        self.assertEqual(again["outcome"],"UNRESOLVED"); self.assertEqual(len(self.c.sent),before)

    def test_duplicates_and_mismatched_results(self):
        first=self.completion()
        self.assertTrue(self.d.reconcile(first)["new_confirmation"])
        self.assertFalse(self.d.reconcile(first)["new_confirmation"])
        replay=self.completion(seq=self.original["attempts"][1]["seq"],replayed=True)
        self.assertFalse(self.d.reconcile(replay)["new_confirmation"])
        for bad in (self.completion(job_id="wrong:1"),self.completion(seq=999),
                    self.completion(boot_id="b"*32),self.completion(part_id=True),self.completion(op_no=2)):
            self.assertFalse(self.d.reconcile(bad)["valid"])
        broken=copy.deepcopy(first); raw=bytes.fromhex(broken["atr_hex"])
        broken["atr_hex"]=(raw[:-1]+bytes([raw[-1]^1])).hex(" ")
        self.assertFalse(self.d.reconcile(broken)["valid"])
        self.assertEqual(self.d.confirmed_part_count,1)

    def test_status_and_heartbeat_never_confirm_a_part(self):
        self.d.reconcile(frame(0,dict(status(),type="HEARTBEAT",heartbeat_no=3),self.c.now))
        self.d.read_status(.2)
        self.assertEqual(self.d.confirmed_part_count,0)

    def test_queued_old_status_is_not_fresh(self):
        self.c.receiver.pending.append(frame(self.c.seq+1,status(),self.c.now-1))
        self.c.snapshot=status("PRODUCING")
        assessment=self.d.assess_continuation(job(2),.2,500)
        self.assertFalse(assessment["eligible"])
        self.assertIn("STATION_NOT_IDLE",assessment["reasons"])

    def test_stale_matching_timestamp_and_old_counter_timeout(self):
        for stale in ("timestamp","counter"):
            def responses(c,seq):
                event=status(); at=c.now+.01
                if stale=="counter": event["heartbeat_no"]=0
                c.put(at,frame(seq,event,c.now-1 if stale=="timestamp" else at))
            self.c.on_status=responses
            with self.assertRaises(StatusTimeout): self.d.read_status(.1)
        self.assertEqual(self.e.ledger.results[(BOOT,1)],self.saved)
        self.assertTrue(all(r["type"]=="GET_STATUS" for r in self.c.sent[3:]))

    def test_positive_assessment_does_not_rearm_or_submit(self):
        run=self.run_api(); before=len(self.c.sent)
        assessment=run.assess_continuation(job(2),.2)
        self.assertTrue(assessment["eligible"])
        self.assertFalse(run.started); self.assertFalse(run.configured)
        self.assertEqual(self.c.sent[before:],[dict(type="GET_STATUS")])
        self.assertEqual(len(self.original["attempts"]),3)

    def test_busy_unconfigured_and_configuration_change_block(self):
        for snapshot in (status("PRODUCING"),status("UNCONFIGURED",0),status(ms=1500)):
            self.c.snapshot=snapshot
            self.assertFalse(self.d.assess_continuation(job(2),.2,500)["eligible"])

    def test_late_evidence_never_clears_lost_contact_fault(self):
        guard=self.c.receiver.guard; guard.fault="HEARTBEAT_TIMEOUT"; guard.available=False
        self.assertTrue(self.d.reconcile(self.completion())["valid"])
        guard.observe(dict(status(),type="HEARTBEAT",heartbeat_no=3))
        self.assertTrue(guard.available); self.assertEqual(guard.fault,"HEARTBEAT_TIMEOUT")
        self.assertFalse(self.d.assess_continuation(job(2),.2,500)["eligible"])

    def test_restart_and_other_boot_evidence_block(self):
        guard=self.c.receiver.guard; guard.observe(dict(status(boot="b"*32),type="HEARTBEAT",heartbeat_no=1))
        self.assertFalse(self.d.reconcile(self.completion())["valid"])
        self.c.snapshot=status(boot="b"*32)
        guard.last_heartbeat_no=99 # New boot may legitimately restart its counter at 1.
        observed=self.d.read_status(.2)
        self.assertEqual(observed["event"]["boot_id"],"b"*32)
        self.assertFalse(self.d.assess_continuation(job(2),.2,500)["eligible"])
        self.assertEqual(guard.fault,"RESTART")

    def test_unresolved_part_cannot_be_recreated_under_new_ids(self):
        candidate=job(2,part=1)
        self.assertFalse(self.d.assess_continuation(candidate,.2,500)["eligible"])
        before=len(self.c.sent); result=self.e.execute(candidate,500)
        self.assertEqual(result["reason"],"UNRESOLVED_PART_IDENTITY_REUSE")
        self.assertEqual(len(self.c.sent),before)

    def test_explicit_action_rechecks_status_and_then_runs_only_different_part(self):
        run=self.run_api(); self.assertTrue(run.assess_continuation(job(2),.2)["eligible"])
        self.c.snapshot=status("PRODUCING")
        with self.assertRaises(ContinuationBlocked): run.produce_different(2,"job:2","batch",2,.2)
        self.c.snapshot=status(); self.c.complete_new_work=True
        result=run.produce_different(2,"job:2","batch",2,.2)
        self.assertEqual(result["outcome"],"COMPLETED")
        self.assertFalse(run.started); self.assertFalse(run.configured)
        self.assertEqual(self.e.ledger.results[(BOOT,1)],self.saved)
        again=self.d.assess_continuation(job(3,part=2),.2,500)
        self.assertIn("PART_ALREADY_KNOWN",again["reasons"])

    def test_operation_exception_is_not_station_unavailability(self):
        exc=OperationUnresolved(self.original)
        self.assertNotIsInstance(exc,SessionFault)
        self.assertTrue(self.c.receiver.guard.available)
        self.assertEqual(exc.category,"OPERATION_UNRESOLVED")

    def test_new_client_does_not_reuse_status_sequence(self):
        class Port:
            def write(self,data): return len(data)
        first=Client(Port(),{"tx":[]}); a=first.send(dict(type="GET_STATUS"),bind_session=False)
        second=Client(Port(),{"tx":[]}); b=second.send(dict(type="GET_STATUS"),bind_session=False)
        self.assertGreater(b,a)

    def test_status_io_failure_cleans_correlation_and_does_not_touch_budget(self):
        def broken(c,seq): raise OSError("injected read-only send failure")
        self.c.on_status=broken
        with self.assertRaises(OSError): self.d.read_status(.1)
        self.assertEqual(self.c.receiver.expected_status,set())
        self.assertEqual(self.e.ledger.results[(BOOT,1)],self.saved)
        self.assertEqual(len(self.original["attempts"]),3)
