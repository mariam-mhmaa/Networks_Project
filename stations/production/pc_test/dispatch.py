"""Single-reader read-only status dispatch and passive completion reconciliation."""
import copy
import math
import time
from evidence import record_part_evidence,uncertain_part_owner,known_part_owner
from session import valid_status


class StatusTimeout(TimeoutError):
    pass


class StationDispatch:
    def __init__(self,client,ledger,clock=time.monotonic):
        self.client,self.ledger,self.clock=client,ledger,clock
        self.report=client.report

    @property
    def confirmed_part_count(self): return len(self.ledger.part_evidence)

    def reconcile(self,item):
        event=item.get("event") or {}
        clean={k:v for k,v in item.items() if k!="payload"}
        if event.get("type")=="PART_PRODUCED":
            return record_part_evidence(self.ledger,clean,self.client.receiver.guard,self.report,self.clock)
        self.report.setdefault("dispatch_observations",[]).append(copy.deepcopy(clean))
        return dict(valid=False,new_confirmation=False,reason="NOT_PART_COMPLETION")

    def poll(self,timeout=.02):
        if self.ledger.inflight: raise RuntimeError("use one synchronous reader; operation is in flight")
        if not math.isfinite(timeout) or timeout<0: raise ValueError("finite nonnegative timeout required")
        before=self.confirmed_part_count
        # Drain decoded evidence first; continue observing even with a latched fault.
        while self.client.receiver.pending:
            self.reconcile(self.client.receiver.pending.pop(0))
        item=self.client.next(timeout,strict_session=False)
        if item: self.reconcile(item)
        while self.client.receiver.pending:
            self.reconcile(self.client.receiver.pending.pop(0))
        return dict(new_confirmations=self.confirmed_part_count-before,confirmed_part_count=self.confirmed_part_count)

    def read_status(self,timeout=1.0):
        if self.ledger.inflight: raise RuntimeError("status helper cannot compete with an active operation reader")
        if not math.isfinite(timeout) or timeout<=0: raise ValueError("finite positive status timeout required")
        # Old queued statuses can never qualify as this query's fresh snapshot.
        while self.client.receiver.pending:
            self.reconcile(self.client.receiver.pending.pop(0))
        requested=self.clock(); deadline=requested+timeout
        guard=self.client.receiver.guard
        baseline=guard.last_heartbeat_no
        seq=None
        try:
            seq=self.client.send(dict(type="GET_STATUS"),bind_session=False,write_deadline=deadline)
            while self.clock()<deadline:
                item=self.client.next(min(.05,deadline-self.clock()),strict_session=False)
                if item is None: continue
                event=item.get("event") or {}
                fresh=(item.get("test_id")==0 and item.get("seq")==seq and event.get("type")=="STATUS"
                       and valid_status(event) and requested<=item.get("monotonic",-1)<=deadline
                       and (event["boot_id"]!=guard.boot_id or
                            event["heartbeat_no"]>=max(baseline,guard.last_heartbeat_no)))
                if fresh:
                    snapshot=dict(query_seq=seq,requested_at=requested,received_at=item["monotonic"],
                                  event=copy.deepcopy(event))
                    self.report.setdefault("status_queries",[]).append(snapshot)
                    return snapshot
                self.reconcile(item)
            raise StatusTimeout("fresh correlated STATUS not received before deadline")
        finally:
            self.client.receiver.expected_status.discard(seq if seq is not None else self.client.seq)

    def assess_continuation(self,request,timeout=1.0,expected_production_time_ms=None):
        guard=self.client.receiver.guard
        candidate=copy.deepcopy(request)
        candidate.setdefault("boot_id",guard.boot_id)
        reasons=[]; snapshot=None
        # Request validation is read-only; never register or repair an operation.
        n=candidate.get("op_no"); ident=candidate.get("job_id")
        import re
        valid=(set(candidate)=={"type","boot_id","op_no","job_id","batch_id","part_id"}
               and candidate["type"]=="PRODUCE_PART" and type(n) is int and 1<=n<=0xFFFFFFFF
               and isinstance(ident,str) and 1<=len(ident)<=48 and re.fullmatch(r"[A-Za-z0-9_.:-]+",ident)
               and ident.rsplit(":",1)[-1]==str(n) and ":" in ident and ident.rsplit(":",1)[0]
               and isinstance(candidate.get("batch_id"),str) and 1<=len(candidate["batch_id"])<=48
               and re.fullmatch(r"[A-Za-z0-9_.:-]+",candidate["batch_id"])
               and type(candidate.get("part_id")) is int and 1<=candidate["part_id"]<=2147483647)
        key=(candidate.get("boot_id"),n)
        if not valid: reasons.append("INVALID_DIFFERENT_WORK_REQUEST")
        elif key in self.ledger.requests: reasons.append("OPERATION_ALREADY_KNOWN")
        elif uncertain_part_owner(self.ledger,candidate,key): reasons.append("UNRESOLVED_PART_IDENTITY_REUSE")
        elif known_part_owner(self.ledger,candidate,key): reasons.append("PART_ALREADY_KNOWN")
        if not reasons:
            try: snapshot=self.read_status(timeout)
            except (OSError,ValueError,RuntimeError) as exc: reasons.append("STATUS_UNCONFIRMED: "+str(exc))
        guard.check()
        if guard.fault: reasons.append("BLOCKING_STATION_FAULT: "+guard.fault)
        if not guard.available: reasons.append("STATION_UNAVAILABLE")
        if candidate.get("boot_id")!=guard.boot_id: reasons.append("WRONG_INTENDED_SESSION")
        if snapshot:
            event=snapshot["event"]
            if event["boot_id"]!=guard.boot_id or guard.observed_boot_id!=guard.boot_id: reasons.append("SESSION_CHANGED")
            if event["state"]!="IDLE" or event["active_op_no"] is not None: reasons.append("STATION_NOT_IDLE")
            if event["production_time_ms"]<=0: reasons.append("STATION_UNCONFIGURED")
            if expected_production_time_ms is not None and event["production_time_ms"]!=expected_production_time_ms:
                reasons.append("CONFIGURATION_CHANGED")
            if valid and n<=event["high_water"]: reasons.append("STALE_NEW_OPERATION_NUMBER")
        assessment=dict(eligible=not reasons,reasons=reasons,request=candidate,status=snapshot,
                        assessed_at=self.clock(),available=guard.available,station_fault=guard.fault)
        self.report.setdefault("continuation_assessments",[]).append(copy.deepcopy(assessment))
        return assessment

    def operation_evidence(self,op_no,boot_id=None):
        key=(boot_id or self.client.receiver.guard.boot_id,op_no)
        result=self.ledger.results.get(key)
        return dict(retry_outcome=result["outcome"] if result else None,
                    retry_reason=result.get("reason") if result else None,
                    automatic_retry_allowed=False if result else None,
                    confirmed_produced=key in self.ledger.part_evidence,
                    evidence=copy.deepcopy(self.ledger.part_evidence.get(key)))
