"""Explicit one-operation gateway API with bounded, session-safe retries."""
from production_test import Client
from session import SessionFault
from retry import RetryController,RetryPolicy,RetryLedger
from dispatch import StationDispatch


class RetryStopped(RuntimeError):
    def __init__(self,result):
        self.result=result
        self.category="OPERATION_UNRESOLVED" if result["outcome"]=="UNRESOLVED" else "STATION_FAULT" if result["outcome"]=="FAULT" else "OPERATION_REJECTED"
        super().__init__(f"{result['outcome']}: {result['reason']}; missing confirmation does not prove no work occurred")


class OperationUnresolved(RetryStopped):
    pass


class StationOperationFault(RetryStopped,SessionFault):
    pass


def stop_exception(result):
    if result["outcome"]=="UNRESOLVED": return OperationUnresolved(result)
    if result["outcome"]=="FAULT": return StationOperationFault(result)
    return RetryStopped(result)


class ContinuationBlocked(RuntimeError):
    def __init__(self,assessment):
        self.assessment=assessment
        super().__init__("different work not eligible: "+", ".join(assessment["reasons"]))


class ProductionRun:
    def __init__(self,port,report,policy=None):
        self.port,self.report=port,report
        self.client=None
        self.configured=False
        self.started=False
        self.policy=policy or RetryPolicy()
        self.controller=None
        self.production_time_ms=None
        self.ledger=RetryLedger()
        self.dispatch=None

    def connect_or_recover(self):
        # Caller explicitly requests recovery. Discovery sends no work.
        self.configured=self.started=False
        self.client=Client(self.port,self.report,assign_operations=False)
        status=self.client.discover()
        self.controller=RetryController(self.client,self.policy,ledger=self.ledger)
        self.dispatch=StationDispatch(self.client,self.ledger)
        return status

    def configure(self,op_no,cmd_id,production_time_ms):
        self.configured=self.started=False
        result=self.controller.execute(dict(type="CONFIGURE_PRODUCTION",op_no=op_no,cmd_id=cmd_id,
                                           production_time_ms=production_time_ms))
        if result["outcome"]!="COMPLETED": raise stop_exception(result)
        current=production_time_ms
        if result.get("local_result_only") or result["completion"]["event"].get("replayed"):
            current=self.read_status(1)["event"]["production_time_ms"]
        self.production_time_ms=current
        self.configured=current==production_time_ms
        return result

    def start(self):
        if not self.configured: raise SessionFault("configuration required before explicit start")
        self.client.receiver.guard.require_send()
        self.started=True

    def produce(self,op_no,job_id,batch_id,part_id):
        if not self.started: raise SessionFault("explicit start required")
        identity=dict(op_no=op_no,job_id=job_id,batch_id=batch_id,part_id=part_id)
        try:
            result=self.controller.execute(dict(type="PRODUCE_PART",**identity),self.production_time_ms)
            if result["outcome"]!="COMPLETED": raise stop_exception(result)
            return result
        except (RetryStopped,SessionFault,OSError,AssertionError,ValueError):
            self.configured=self.started=False
            raise

    def observe(self,timeout=0.02):
        # Continues reading even with a latched fault, without continuing work.
        if self.dispatch is None: self.client.receiver.pump(timeout)
        else: self.dispatch.poll(timeout)
        guard=self.client.receiver.guard
        guard.check()
        if guard.fault: self.configured=self.started=False
        return dict(available=guard.available,fault=guard.fault,
                    boot_id=guard.boot_id,observed_boot_id=guard.observed_boot_id,
                    confirmed_part_count=len(self.ledger.part_evidence))

    def read_status(self,timeout=1.0):
        if self.dispatch is None: self.dispatch=StationDispatch(self.client,self.ledger)
        return self.dispatch.read_status(timeout)

    def assess_continuation(self,request,timeout=1.0):
        if self.dispatch is None: self.dispatch=StationDispatch(self.client,self.ledger)
        return self.dispatch.assess_continuation(request,timeout,self.production_time_ms)

    def produce_different(self,op_no,job_id,batch_id,part_id,timeout=1.0):
        # Explicit one-part action; never rearms the normal run or reuses an old assessment.
        self.configured=self.started=False
        request=dict(type="PRODUCE_PART",op_no=op_no,job_id=job_id,batch_id=batch_id,part_id=part_id)
        assessment=self.assess_continuation(request,timeout)
        if not assessment["eligible"]: raise ContinuationBlocked(assessment)
        self.client.receiver.guard.require_send()
        result=self.controller.execute(assessment["request"],assessment["status"]["event"]["production_time_ms"])
        if result["outcome"]!="COMPLETED": raise stop_exception(result)
        return result

    def operation_evidence(self,op_no,boot_id=None):
        if self.dispatch is None: self.dispatch=StationDispatch(self.client,self.ledger)
        return self.dispatch.operation_evidence(op_no,boot_id)
