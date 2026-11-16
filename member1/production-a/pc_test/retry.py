"""Bounded one-operation retry controller. No firmware/interface changes."""
from dataclasses import dataclass,asdict
import json
import math
import time
from session import SessionFault
from evidence import record_part_evidence,uncertain_part_owner


@dataclass(frozen=True)
class RetryPolicy:
    acceptance_timeout: float = 1.0
    completion_slack: float = 1.0
    max_retries: int = 2
    saved_result_wait: float = 1.0
    production_overall_slack: float = 3.0
    configuration_overall: float = 3.0

    def __post_init__(self):
        for value in (self.acceptance_timeout,self.completion_slack,self.saved_result_wait,
                      self.production_overall_slack,self.configuration_overall):
            if not math.isfinite(value) or value<=0: raise ValueError("positive finite retry times required")
        if type(self.max_retries) is not int or self.max_retries<0: raise ValueError("invalid retry budget")
        if self.production_overall_slack<self.completion_slack: raise ValueError("overall precedes completion deadline")


class RetryLedger:
    def __init__(self):
        self.requests={}
        self.sequences={}
        self.completed=set()
        self.results={}
        self.part_evidence={}
        self.resolution_audit=[]
        self.inflight=set()


class RetryController:
    def __init__(self,client,policy=None,clock=time.monotonic,omit=None,ledger=None):
        self.client=client
        self.policy=policy or RetryPolicy()
        self.clock=clock
        self.omit=omit # Deterministic test hook, after heartbeat routing.
        self.ledger=ledger or RetryLedger()
        self.requests=self.ledger.requests
        self.sequences=self.ledger.sequences
        self.completed=self.ledger.completed
        policies=self.client.report.setdefault("retry_policies",[])
        if asdict(self.policy) not in policies: policies.append(asdict(self.policy))

    @property
    def completion_count(self): return len(self.completed)

    def execute(self,request,production_time_ms=None):
        p=self.policy
        # Freeze a private JSON copy once. Never allocate/repair an op number.
        request=json.loads(json.dumps(request,allow_nan=False))
        request.setdefault("boot_id",self.client.receiver.guard.boot_id)
        kind=request.get("type")
        if kind not in ("CONFIGURE_PRODUCTION","PRODUCE_PART"): raise ValueError("unsupported operation")
        if type(request.get("op_no")) is not int or not 1<=request["op_no"]<=0xFFFFFFFF:
            raise ValueError("explicit uint32 op_no required")
        if kind=="PRODUCE_PART" and (type(production_time_ms) is not int or not 1<=production_time_ms<=60000):
            raise ValueError("known applied production duration required")
        key=(request["boot_id"],request["op_no"])
        frozen=json.dumps(request,sort_keys=True,separators=(",",":"),allow_nan=False)
        t0=self.clock()
        duration=production_time_ms/1000 if kind=="PRODUCE_PART" else 0
        overall=t0+(duration+p.production_overall_slack if kind=="PRODUCE_PART" else p.configuration_overall)
        initial_completion=t0+duration+p.completion_slack if kind=="PRODUCE_PART" else t0+p.acceptance_timeout
        prior=self.ledger.results.get(key)
        if prior:
            t0=prior["original_time"]
            overall=prior["absolute_deadline"]
            initial_completion=prior["initial_completion_deadline"]
        log=dict(request=request,original_time=t0,acceptance_deadline=prior["acceptance_deadline"] if prior else t0+p.acceptance_timeout,
                 initial_completion_deadline=initial_completion,absolute_deadline=overall,
                 attempts=[],trace=[],accepted=prior["accepted"] if prior else False,outcome=None)
        self.client.report.setdefault("retry_operations",[]).append(log)
        def trace(event,**details):
            log["trace"].append(dict(time=self.clock(),event=event,**details))
        def finish(outcome,reason=None,item=None):
            log.update(outcome=outcome,reason=reason,finished_at=self.clock(),completion=item)
            if outcome=="COMPLETED":
                log["accepted"]=True # Completion confirms historical acceptance even if ACCEPTED was lost.
                log["new_logical_completion"]=key not in self.completed
                self.completed.add(key)
            trace("FINAL",outcome=outcome,reason=reason)
            self.ledger.inflight.discard(key)
            if key not in self.ledger.results:
                self.ledger.results[key]=log
                audit=dict(type="RETRY_STOPPED",boot_id=key[0],op_no=key[1],time=self.clock(),outcome=outcome)
                self.ledger.resolution_audit.append(audit)
                self.client.report.setdefault("resolution_audit",[]).append(dict(audit))
            if outcome=="COMPLETED" and kind=="PRODUCE_PART" and item:
                record_part_evidence(self.ledger,item,self.client.receiver.guard,self.client.report,self.clock)
            return log
        if key in self.requests and self.requests[key]!=frozen:
            return finish("REJECTED","LOCAL_OPERATION_CONFLICT")
        if prior:
            try:
                self.client.receiver.guard.require_send()
            except SessionFault as exc:
                return finish("FAULT",str(exc))
            if request["boot_id"]!=self.client.receiver.guard.boot_id:
                return finish("FAULT","SESSION_MISMATCH_LOCAL")
            log["local_result_only"]=True
            trace("NO_TRANSMISSION_PREVIOUS_RESULT",previous_outcome=prior["outcome"])
            return finish(prior["outcome"],"PREVIOUS_OPERATION_RESULT",prior.get("completion"))
        owner=uncertain_part_owner(self.ledger,request,key)
        if owner:
            return finish("REJECTED","UNRESOLVED_PART_IDENTITY_REUSE")
        self.requests[key]=frozen
        allowed=self.sequences.setdefault(key,set())
        phase="WAIT_ACCEPTANCE"; wake=min(t0+p.acceptance_timeout,overall)
        def transmit():
            self.client.receiver.guard.require_send()
            now=self.clock()
            if now>=overall or len(log["attempts"])>=p.max_retries+1: return False
            attempt=dict(attempt=len(log["attempts"])+1,seq=None,time=now,write_complete=False)
            log["attempts"].append(attempt)
            trace("TRANSMIT_BEGIN",attempt=attempt["attempt"])
            previous_seq=self.client.seq
            try:
                seq=self.client.send(request,write_deadline=overall)
            finally:
                attempt["seq"]=self.client.seq if self.client.seq!=previous_seq else None
                if attempt["seq"] is not None: allowed.add(attempt["seq"])
            allowed.add(seq)
            attempt["write_complete"]=True
            trace("TRANSMIT",attempt=len(log["attempts"]),seq=seq)
            return True
        try:
            if request["boot_id"]!=self.client.receiver.guard.boot_id:
                return finish("FAULT","SESSION_MISMATCH_LOCAL")
            self.ledger.inflight.add(key)
            transmit()
            trace("WAIT",phase=phase,until=wake)
            while True:
                self.client.receiver.guard.require_send()
                now=self.clock()
                if now>=overall: return finish("UNRESOLVED","ABSOLUTE_DEADLINE")
                if now>=wake:
                    if len(log["attempts"])<p.max_retries+1:
                        # Inspect already-decoded late replies before resubmitting.
                        item=self.client.next(0,strict_session=False)
                        if item is None:
                            if not transmit(): return finish("UNRESOLVED","ABSOLUTE_DEADLINE")
                            phase="SAVED_RESULT_WINDOW"; wake=min(self.clock()+p.saved_result_wait,overall)
                            trace("WAIT",phase=phase,until=wake)
                            continue
                    else:
                        phase="OBSERVE_ONLY_BUDGET_EXHAUSTED"; wake=overall
                        trace("WAIT",phase=phase,until=wake)
                        item=self.client.next(min(0.05,overall-now),strict_session=False)
                else:
                    item=self.client.next(min(0.05,wake-now,overall-now),strict_session=False)
                if item is None: continue
                event=item.get("event") or {}
                if item.get("test_id")==0 and item.get("seq") in allowed and event.get("boot_id")!=request["boot_id"]:
                    self.client.receiver.guard.fault="RESTART"
                    self.client.receiver.guard.available=False
                    return finish("FAULT","RESTART",item)
                matching=(item.get("test_id")==0 and item.get("seq") in allowed and
                          event.get("boot_id")==request["boot_id"] and
                          type(event.get("op_no")) is int and event["op_no"]==request["op_no"])
                if not matching:
                    resolution=None
                    if event.get("type")=="PART_PRODUCED":
                        resolution=record_part_evidence(self.ledger,item,self.client.receiver.guard,self.client.report,self.clock)
                    trace("QUARANTINED_RESPONSE",response=item,resolution=resolution)
                    continue
                identity_keys=("cmd_id",) if kind=="CONFIGURE_PRODUCTION" else ("job_id","batch_id","part_id")
                for field in identity_keys:
                    if event.get("type")=="REJECTED" and field=="part_id" and field not in event: continue
                    if type(event.get(field)) is not type(request.get(field)) or event.get(field)!=request.get(field):
                        return finish("FAULT","RESPONSE_IDENTITY_CONFLICT",item)
                ignored=bool(self.omit and self.omit(item,len(log["attempts"])))
                trace("IGNORED_RESPONSE" if ignored else "RESPONSE",response=item,phase=phase,
                      attempt=len(log["attempts"]),seq=item.get("seq"))
                if ignored: continue
                response_type=event.get("type")
                terminal="PRODUCTION_CONFIGURED" if kind=="CONFIGURE_PRODUCTION" else "PART_PRODUCED"
                if response_type==terminal:
                    if kind=="CONFIGURE_PRODUCTION" and (type(event.get("production_time_ms")) is not int or
                            event["production_time_ms"]!=request.get("production_time_ms")):
                        return finish("FAULT","CONFIGURATION_RESULT_MISMATCH",item)
                    if self.clock()>overall: return finish("UNRESOLVED","ABSOLUTE_DEADLINE")
                    return finish("COMPLETED",item=item)
                if response_type=="REJECTED": return finish("REJECTED",event.get("reason"),item)
                if response_type in ("ACCEPTED","OPERATION_RUNNING"):
                    log["accepted"]=True
                    if self.clock()<initial_completion and phase!="OBSERVE_ONLY_BUDGET_EXHAUSTED":
                        phase="WAIT_COMPLETION"; wake=min(initial_completion,overall)
                        trace("WAIT",phase=phase,until=wake)
                elif response_type!="RECEIVED":
                    return finish("FAULT","UNEXPECTED_RESPONSE_TYPE",item)
        except SessionFault as exc:
            return finish("FAULT",str(exc))
        except (OSError,RuntimeError,ValueError,AssertionError) as exc:
            return finish("UNRESOLVED",f"{type(exc).__name__}: {exc}")


def write_retry_csv(report,path):
    import csv
    from pathlib import Path
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fields=["boot_id","op_no","request_type","cmd_id","job_id","event","elapsed_s","attempt",
            "seq","acceptance_deadline","initial_completion_deadline","absolute_deadline","outcome","details"]
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        for op in report.get("retry_operations",[]):
            req=op["request"]
            for row in op["trace"]:
                writer.writerow(dict(boot_id=req["boot_id"],op_no=req["op_no"],request_type=req["type"],
                    cmd_id=req.get("cmd_id",""),job_id=req.get("job_id",""),event=row["event"],
                    elapsed_s=row["time"]-op["original_time"],attempt=row.get("attempt",""),seq=row.get("seq",""),
                    acceptance_deadline=op["acceptance_deadline"],initial_completion_deadline=op["initial_completion_deadline"],
                    absolute_deadline=op["absolute_deadline"],outcome=op["outcome"],details=json.dumps(row)))
