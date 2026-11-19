"""Integrated A -> bounded queue -> B core. Operator HTTP/UI stays separate.

One producer, one inspector, one controller per operation. Known parts on B
may finish while A is held. Continue never invents replacement target work.
"""
import asyncio
from dataclasses import asdict
from gateway.inspection.coordinator import InspectionGateway, GatewayFault
from gateway.inspection.controller import Outcome

class BatchGateway:
    def __init__(self, production, inspection, *, queue_capacity, full_policy, ledger_path):
        self.a=production
        self.b=InspectionGateway(inspection,queue_capacity=queue_capacity,full_policy=full_policy,ledger_path=ledger_path)
        self.state="IDLE"; self.fault_reason=None
        self.requests={}; self.settings={}; self.outcomes={}; self.unresolved={}; self.isolated=set()
        self.production_ids={}; self.producer=None; self.health=None; self.active=None
        self.closures={}; self.restart_fences=set()
        self.dispatch_lock=asyncio.Lock()
        self.pending_part=None; self.ending=False; self.production_started={}; self.configuration_hold=False
        self.changed=asyncio.Condition(); self.control=asyncio.Lock(); self.stopping=False

    async def _hold(self, reason):
        self.state="FAULT"; self.fault_reason=reason
        async with self.changed: self.changed.notify_all()

    async def start_run(self, production_settings, inspection_settings, target, *, batch_id=None):
        async with self.control:
            if self.state!="IDLE": raise GatewayFault("close existing batch first")
            heartbeat=await self.a.connect()
            if heartbeat["run_open"] or heartbeat["state"]!="IDLE":
                raise GatewayFault("A requires explicit prior-run closure")
            # Configure B first, reserving a run context; either failure leaves
            # a visible Fault and needs explicit closure, never partial dispatch.
            self.state="FAULT"; self.fault_reason="batch configuration incomplete"
            await self.b.start_run(inspection_settings,target,batch_id=batch_id)
            # B has established the new batch. Clear old production accounting
            # before awaiting A, including when A configuration later fails.
            self.requests={}; self.settings={}; self.outcomes={}; self.unresolved={}; self.isolated=set(); self.production_ids={}
            self.closures={}; self.restart_fences=set()
            self.pending_part=None; self.ending=False; self.production_started={}; self.configuration_hold=False
            self.a.select_run(self.b.batch_id,heartbeat["run_no"]+1)
            outcome=await self.a.configure(production_settings)
            await self.b.ledger.record("production_configure",asdict(outcome))
            if outcome.state!="COMPLETED": raise GatewayFault("A configuration did not complete")
            self.stopping=False; self.state="RUNNING"; self.fault_reason=None
            self.producer=asyncio.create_task(self._produce())
            self.health=asyncio.create_task(self._health())
            return self.snapshot()

    def snapshot(self):
        view=self.b.snapshot()
        unresolved_parts={self.requests[j]["part_id"] for j in self.unresolved}
        unresolved_parts.update(self.b.requests[j]["part_id"] for j in self.b.unresolved)
        view.update(state=self.state if self.state!="RUNNING" else self.b.state,
            fault_reason=self.fault_reason or self.b.fault_reason,
            produced=sum(o.state=="COMPLETED" for o in self.outcomes.values()),
            unresolved=len(unresolved_parts), production_unresolved_job_ids=list(self.unresolved),
            production_active_part_id=self.active.part_id if self.active else None)
        view["outcome"]="COMPLETED" if view["inspection_complete"] and not unresolved_parts else ("INCOMPLETE" if self.state=="IDLE" and self.b.target else "OPEN")
        return view

    async def _health(self):
        while not self.stopping:
            await asyncio.sleep(.1)
            if not self.a.link.fresh or self.a.link.terminal_conflict:
                await self._hold("A disconnected/stale or conflicting evidence")
            if self.b.state=="FAULT": await self._hold(self.b.fault_reason)

    async def _produce(self):
        try:
            while not self.stopping and (self.pending_part or len(self.b.parts)<self.b.target):
                async with self.changed:
                    await self.changed.wait_for(lambda:self.stopping or (self.state=="RUNNING" and not self.ending))
                if self.stopping: return
                if self.pending_part is None:
                    self.pending_part=await self.b.reserve_part()
                part=self.pending_part
                # Pause/Stop serialize only the brief preparation/submission
                # point, never a station's entire accepted execution time.
                async with self.dispatch_lock:
                    if self.state!="RUNNING" or self.ending: continue
                    identifier=self.a.ids.new("PROD")
                    request=self.a.production(part.part_id,identifier)
                    frozen=self.a.settings.fields()
                    await self.b.ledger.record("production_request",request)
                    if self.state!="RUNNING" or self.b.state!="RUNNING" or not self.a.link.fresh:
                        await self.b.ledger.record("production_not_submitted",request)
                        await self._hold("production held before submission")
                        continue
                    self.production_ids[part.part_id]=identifier
                    self.requests[identifier]=request; self.settings[identifier]=frozen
                    self.active=part; self.pending_part=None
                    self.production_started[identifier]=asyncio.get_running_loop().time()
                    operation=asyncio.create_task(self.a.controller.run(request,
                        duration_ms=frozen["production_time_ms"],expected_settings=frozen))
                outcome=await operation
                await self.b.ledger.record("production_outcome",asdict(outcome))
                self.outcomes[identifier]=outcome
                if outcome.state=="COMPLETED" and not self.a.link.terminal_conflict:
                    await self.b.produced(part)
                else:
                    self.unresolved[identifier]=outcome
                    await self._hold(outcome.reason or "production needs explicit reconciliation")
                self.active=None
        except asyncio.CancelledError:
            if self.active:
                identifier=self.production_ids[self.active.part_id]
                self.unresolved[identifier]=self.outcomes.get(identifier)
                await self.b.ledger.record("production_shutdown_unresolved",self.requests[identifier])
                self.active=None
            raise
        except Exception as exc:
            if self.active:
                identifier=self.production_ids.get(self.active.part_id)
                if identifier: self.unresolved[identifier]=self.outcomes.get(identifier)
                self.active=None
            await self._hold(str(exc))

    async def pause(self, reason="Operator paused dispatch"):
        async with self.control:
            if self.state not in {"RUNNING","PAUSED"}: raise GatewayFault("only a running batch can be paused")
            async with self.dispatch_lock:
                self.state="PAUSED"; self.fault_reason=None
                async with self.b.condition:
                    if self.b.state=="FAULT":
                        await self._hold(self.b.fault_reason)
                        raise GatewayFault(self.fault_reason)
                    self.b.state="PAUSED"; self.b.condition.notify_all()
            await self.b.ledger.record("pause",{"batch_id":self.b.batch_id,"reason":reason})
            async with self.changed: self.changed.notify_all()
            return self.snapshot()

    async def resume(self):
        async with self.control:
            if self.state!="PAUSED" or self.ending or self.configuration_hold: raise GatewayFault("batch is not resumable")
            if (not self.a.link.fresh or not self.b.client.link.fresh or
                    self.a.link.terminal_conflict or self.b.client.link.terminal_conflict or
                    set(self.unresolved)-self.isolated or set(self.b.unresolved)-self.b.isolated):
                raise GatewayFault("fresh original stations and resolved/fenced work required")
            for client in (self.a,self.b.client):
                h=client.link.heartbeat
                if not h or not h["run_open"] or h["run_no"]!=client.run_no or h["batch_id"]!=self.b.batch_id:
                    raise GatewayFault("station run context changed")
            if self.b.state=="FAULT": raise GatewayFault(self.b.fault_reason)
            self.state="RUNNING"; self.fault_reason=None
            async with self.b.condition:
                self.b.state="RUNNING"; self.b.condition.notify_all()
            async with self.changed: self.changed.notify_all()
            return self.snapshot()

    async def apply_settings(self, production, inspection):
        async with self.control:
            if (self.state!="PAUSED" or self.active or self.b.active or self.ending or
                    not self._ready(self.a) or not self._ready(self.b.client)):
                raise GatewayFault("pause and wait for both stations to become fresh and idle")
            self.configuration_hold=True
            a=await self.a.configure(production)
            await self.b.ledger.record("production_reconfigure",asdict(a))
            if a.state!="COMPLETED":
                await self._hold("A settings were not confirmed"); raise GatewayFault(self.fault_reason)
            async with self.b.operation_lock:
                b=await self.b.client.configure(inspection)
            await self.b.ledger.record("inspection_reconfigure",asdict(b))
            if b.state!="COMPLETED":
                await self._hold("B settings were not confirmed; review partial configuration")
                raise GatewayFault(self.fault_reason)
            self.configuration_hold=False
            return self.snapshot()

    async def stop_batch(self):
        # Stop is finite, gates both dispatchers and leaves current controllers
        # running. It never cancels an ESP job or drains the waiting queue.
        async with self.control:
            if self.state=="IDLE": raise GatewayFault("no open batch")
            async with self.dispatch_lock:
                self.ending=True
                if self.state!="FAULT": self.state="PAUSED"
                async with self.b.condition:
                    if self.b.state!="FAULT": self.b.state="PAUSED"
                    self.b.condition.notify_all()
            end=asyncio.get_running_loop().time()+max(
                self.a.settings.production_time_ms if self.a.settings else 0,
                self.b.client.settings.inspection_time_ms if self.b.client.settings else 0)/1000+35
        while self.active or self.b.active:
            if asyncio.get_running_loop().time()>=end:
                await self._hold("Stop waiting limit exhausted; accepted work remains unresolved")
                raise GatewayFault(self.fault_reason)
            await asyncio.sleep(.02)
        # Read-only late-result recovery may amend only this original batch.
        await self.b._fault("ending batch: recovering retained outcomes")
        for identifier in list(self.unresolved):
            if identifier not in self.isolated: await self.reconcile_production(identifier)
        for identifier in list(self.b.unresolved):
            if identifier not in self.b.isolated: await self.b.reconcile(identifier)
        while not all(station in self.restart_fences or self._ready(client) or
                      (station in self.closures and self.closures[station][1].state=="COMPLETED")
                      for station,client in (("A",self.a),("B",self.b.client))):
            if (isinstance(self.a.link.failure,Exception) or isinstance(self.b.client.link.failure,Exception) or
                    asyncio.get_running_loop().time()>=end):
                await self._hold("Stop needs station recovery/confirmed idle closure")
                raise GatewayFault(self.fault_reason)
            await asyncio.sleep(.05)
        return await self.close_run(incomplete=True)

    def _ready(self, client):
        h=client.link.heartbeat
        return (client.link.fresh and not client.link.terminal_conflict and h and h["state"]=="IDLE" and
                h["run_open"] and h["batch_id"]==self.b.batch_id and h["run_no"]==client.run_no)

    async def reconfigure_production(self, settings):
        async with self.control:
            if self.state!="RUNNING" or self.active:
                raise GatewayFault("production configuration is BUSY or batch held")
            # Briefly hold production dispatch while the command is pending.
            self.state="FAULT"; self.fault_reason="production configuration in progress"
            outcome=await self.a.configure(settings)
            await self.b.ledger.record("production_reconfigure",asdict(outcome))
            if outcome.state=="COMPLETED" and self.a.link.fresh and not self.a.link.terminal_conflict:
                self.state="RUNNING"; self.fault_reason=None
                async with self.changed: self.changed.notify_all()
            return outcome

    async def reconcile_production(self, identifier):
        if identifier not in self.unresolved: raise GatewayFault("no matching unresolved production")
        outcome=await self.a.query(identifier)
        await self.b.ledger.record("production_lookup",asdict(outcome))
        if outcome.state!="COMPLETED": raise GatewayFault("production lookup did not complete")
        target=outcome.result.get("target"); original=self.unresolved[identifier]
        if not target:
            if original and original.evidence.delivery_established_by:
                raise GatewayFault("A lost a queryable record; close incomplete instead")
            return outcome
        req=self.requests[identifier]
        if not self.a.controller._identity({**target,"boot_id":req["boot_id"]},req):
            raise GatewayFault("lookup identity conflict")
        if target["state"]=="COMPLETED":
            frozen=self.settings[identifier]
            result=self.a.controller._result(target,req,frozen["production_time_ms"],frozen)
            recovered=Outcome("COMPLETED",identifier,result,outcome.evidence,"explicit production reconciliation")
            self.outcomes[identifier]=recovered
            part=self.b.parts[req["part_id"]]
            if identifier in self.isolated:
                # An unknown tombstone must never later acquire an executed outcome.
                raise GatewayFault("completion contradicts acknowledged production retirement")
            await self.b.produced(part)
            self.unresolved.pop(identifier)
            return recovered
        if target["state"]=="REJECTED" and original and original.evidence.acceptance_established_by:
            raise GatewayFault("rejection contradicts production acceptance")
        return outcome

    async def continue_remaining(self):
        async with self.control:
            if self.configuration_hold:
                raise GatewayFault("settings were not jointly confirmed; end this batch before new work")
            if self.state!="FAULT" or self.closures or self.restart_fences or self.active or self.b.active:
                raise GatewayFault("wait for current operation controllers to finish")
            if not self._ready(self.a) or not self._ready(self.b.client):
                raise GatewayFault("fresh same-boot/current-run idle evidence required")
            await self.b._fault("explicit guarded continuation in progress")
            for identifier in list(self.unresolved):
                if identifier in self.isolated: continue
                lookup=await self.reconcile_production(identifier)
                if identifier not in self.unresolved: continue
                target=lookup.result.get("target")
                if target and target["state"] not in {"COMPLETED","REJECTED"}:
                    raise GatewayFault("A still executing; no implicit cancellation")
                req=self.requests[identifier]
                retirement=await self.a.retire(identifier,req["part_id"])
                await self.b.ledger.record("production_retirement",asdict(retirement))
                if retirement.state!="COMPLETED": raise GatewayFault("A retirement unconfirmed")
                target=retirement.result["target"]
                if target["action"]!="PRODUCE": raise GatewayFault("wrong production retirement action")
                if target["state"]=="COMPLETED":
                    # Query again recovers the real frozen outcome, without execution.
                    await self.reconcile_production(identifier)
                else:
                    original=self.unresolved[identifier]
                    if original and original.evidence.acceptance_established_by:
                        raise GatewayFault("retirement contradicts accepted production")
                    await self.b.release_unproduced(self.b.parts[req["part_id"]])
                    self.isolated.add(identifier)
            for identifier in list(self.b.unresolved): await self.b.isolate(identifier)
            if self.b.state=="FAULT": await self.b.resume_after_reconciliation()
            if not self._ready(self.a): raise GatewayFault("A readiness changed during recovery")
            self.state="RUNNING"; self.fault_reason=None
            if not self.producer or self.producer.done(): self.producer=asyncio.create_task(self._produce())
            async with self.changed: self.changed.notify_all()
            return self.snapshot()

    async def wait(self):
        while True:
            view=self.snapshot()
            if view["state"]=="FAULT": raise GatewayFault(view["fault_reason"])
            if self.producer and self.producer.done() and all(p.future.done() for p in self.b.parts.values()):
                return view
            await asyncio.sleep(.02)

    async def bind_restarted_station(self, station, replacement):
        """Explicit incomplete-batch recovery; never replay old work on a new boot.

        The caller provides a new client only after an actual restart. Old
        results stay unresolved. The fresh idle boot itself invalidates old
        requests, and this batch must be closed before new work starts.
        """
        async with self.control:
            if station not in {"A","B"} or self.state!="FAULT" or self.active or self.b.active:
                raise GatewayFault("quiescent Fault and station A/B required")
            old=self.a if station=="A" else self.b.client
            h=await replacement.connect()
            if (not old.link.boot_id or replacement.link.boot_id==old.link.boot_id or
                    not replacement.link.fresh or h["state"]!="IDLE" or h["run_open"]):
                raise GatewayFault("replacement must prove a different fresh idle boot with no open run")
            await self.b._fault("restarted station: close incomplete before new batch")
            await self.b.ledger.record("restart_fence",{"station":station,"old_boot":old.link.boot_id,"new_boot":replacement.link.boot_id})
            await old.close()
            if station=="A": self.a=replacement
            else: self.b.client=replacement
            self.restart_fences.add(station)
            self.fault_reason="restart fenced old scope; close incomplete before starting a new batch"

    async def _close_station(self, station, client):
        if station in self.restart_fences: return None
        previous=self.closures.get(station)
        if previous and previous[1].state=="COMPLETED": return previous[1]
        h=client.link.heartbeat
        if (not client.link.fresh or client.link.terminal_conflict or not h or h["state"]!="IDLE" or
                h["batch_id"]!=self.b.batch_id or h["run_no"]!=client.run_no):
            raise GatewayFault(f"{station} fresh idle same-boot scope required")
        if previous and previous[1].state=="UNRESOLVED":
            # Explicit recovery is a new read-only query, never a fresh budget
            # for the old mutation. A later heartbeat cannot fabricate closure.
            request,_=previous
            query=await client.query(request["cmd_id"])
            await self.b.ledger.record("closure_lookup",asdict(query))
            target=query.result.get("target") if query.state=="COMPLETED" else None
            if target and target.get("state")=="REJECTED":
                if (not client.controller._identity({**target,"boot_id":request["boot_id"]},request) or
                        previous[1].evidence.acceptance_established_by):
                    raise GatewayFault("closure rejection contradicts context/acceptance")
                rejected=Outcome("REJECTED",request["cmd_id"],target,query.evidence,target.get("error"))
                self.closures[station]=(request,rejected)
                await self.b.ledger.record("closure_rejected",asdict(rejected))
                raise GatewayFault("cached closure rejection recovered; another explicit idle closure may proceed")
            if not target or target.get("state")!="COMPLETED":
                raise GatewayFault("closure unresolved; retain old context and retry explicit lookup")
            result=client.controller._result(target,request,0)
            outcome=Outcome("COMPLETED",request["cmd_id"],result,query.evidence,"explicit closure reconciliation")
        else:
            if not h["run_open"]: raise GatewayFault("closed scope without matching closure evidence")
            # A cached BUSY rejection is immutable. A later explicit idle
            # closure action gets a new identity rather than rewriting it.
            request=client.request("CLOSE")
            outcome=await client.controller.run(request)
        self.closures[station]=(request,outcome)
        await self.b.ledger.record("station_close",{"station":station,"outcome":asdict(outcome)})
        if outcome.state!="COMPLETED": raise GatewayFault(f"{station} closure not confirmed")
        return outcome

    async def close_run(self, *, incomplete=False):
        async with self.control:
            if self.active or self.b.active: raise GatewayFault("accepted work must finish before closure")
            if not incomplete and (self.restart_fences or not self.snapshot()["inspection_complete"]):
                raise GatewayFault("batch incomplete; explicit incomplete closure required")
            await self._hold("batch closure in progress")
            await self.b._fault("batch closure in progress")
            # Hold both dispatchers and serialize against an inspector that
            # has left its queue but has not yet submitted its request.
            async with self.b.operation_lock:
                if self.b.active: raise GatewayFault("inspection is still in flight")
                await self._close_station("A",self.a)
                await self._close_station("B",self.b.client)
            await self.b.ledger.record("batch_close",self.snapshot())
            self.state="IDLE"; self.fault_reason=None; self.b.state="IDLE"; self.b.fault_reason=None
            await self.shutdown(close_links=False)
            return self.snapshot()

    async def shutdown(self, *, close_links=True):
        if self.state=="RUNNING": await self._hold("gateway stopped with an open batch")
        self.stopping=True
        async with self.changed: self.changed.notify_all()
        for task in (self.producer,self.health):
            if task: task.cancel()
        await asyncio.gather(*(t for t in (self.producer,self.health) if t),return_exceptions=True)
        if close_links: await self.a.close()
        await self.b.shutdown(close_link=close_links)
