"""Inspection-side gateway core and the production adapter's reservation API.

One asyncio owner accounts for parts; the link reader never changes totals.
Production A and operator HTTP/UI are integrated separately.
"""
import asyncio
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import uuid
from .client import BClient
from .controller import Evidence, Outcome
from .wire import ProtocolError


class GatewayFault(Exception):
    pass


class Ledger:
    """Atomic durable numeric-part allocation and evidence.

    Each call opens its own SQLite connection in a worker thread. No thread
    reads sockets or owns gateway operation/retry/accounting decisions.
    """
    def __init__(self, path):
        self.path = str(Path(path).resolve())

    def _call(self, action, *args):
        with closing(sqlite3.connect(self.path, timeout=2)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS counter (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, kind TEXT, body TEXT)")
            if action == "allocate":
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT value FROM counter WHERE key='part'").fetchone()
                value = (row[0] if row else 0) + 1
                if value > 4294967295:
                    raise GatewayFault("numeric part identifiers exhausted")
                db.execute("INSERT OR REPLACE INTO counter VALUES ('part', ?)", (value,))
                return value
            db.execute("INSERT INTO events(kind,body) VALUES (?,?)",
                       (action, json.dumps(args[0], sort_keys=True, separators=(",", ":"))))

    async def allocate(self):
        return await self._io("allocate")

    async def record(self, kind, body):
        await self._io(kind, body)

    async def _io(self, action, *args):
        operation = asyncio.create_task(asyncio.to_thread(self._call, action, *args))
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError:
            # Cancellation must not leave an open SQLite writer behind.
            await operation
            raise


@dataclass
class Part:
    batch_id: str
    part_id: int
    job_id: str
    future: asyncio.Future
    produced: bool = False
    dispatched: bool = False


class InspectionGateway:
    def __init__(self, client: BClient, *, queue_capacity, full_policy, ledger_path):
        if type(queue_capacity) is not int or not 1 <= queue_capacity <= 64:
            raise ValueError("queue_capacity must be explicitly set in 1..64")
        if full_policy not in {"block", "fault"}:
            raise ValueError("select full_policy='block' or 'fault' explicitly")
        self.client = client
        self.capacity, self.full_policy = queue_capacity, full_policy
        self.ledger = Ledger(ledger_path)
        self.state = "IDLE"
        self.fault_reason = None
        self.batch_id = None
        self.target = 0
        self.parts = {}
        self.queue = asyncio.Queue(maxsize=queue_capacity)
        self.condition = asyncio.Condition()
        self.operation_lock = asyncio.Lock()
        self.worker = self.health = None
        self.active = None
        self.results = {}
        self.unresolved = {}
        self.requests = {}
        self.frozen_settings = {}
        self.accepted = self.rejected = 0  # Product verdict counts only.
        self._slots_used = 0
        self._stopping = False

    async def start_run(self, settings, target, *, batch_id=None):
        if self.state != "IDLE":
            raise GatewayFault("close the existing run before starting another")
        if self.client.link.terminal_conflict:
            raise GatewayFault("prior conflicting terminal evidence requires explicit review")
        if type(target) is not int or not 1 <= target <= 64:
            raise ValueError("one B run supports 1..64 inspection jobs")
        heartbeat = await self.client.connect()
        if heartbeat["run_open"] or heartbeat["state"] != "IDLE":
            raise GatewayFault("B has an existing run; explicit reconciliation/closure is required")
        batch_id = batch_id or f"BATCH-GW-{uuid.uuid4().hex}"
        self.client.select_run(batch_id, heartbeat["run_no"] + 1)
        outcome = await self.client.configure(settings)
        await self.ledger.record("configure", asdict(outcome))
        if outcome.state != "COMPLETED":
            await self._fault("B configuration did not complete")
            raise GatewayFault(self.fault_reason)
        self.parts, self.results, self.unresolved, self.requests, self.frozen_settings = {}, {}, {}, {}, {}
        self.accepted = self.rejected = self._slots_used = 0
        self.queue = asyncio.Queue(maxsize=self.capacity)
        self._stopping = False
        self.fault_reason = None
        self.batch_id, self.target = batch_id, target
        self.state = "RUNNING"
        self.worker = asyncio.create_task(self._worker())
        self.health = asyncio.create_task(self._health())
        return outcome

    def snapshot(self):
        return {
            "state": self.state, "fault_reason": self.fault_reason,
            "batch_id": self.batch_id, "target": self.target,
            "reserved": len(self.parts), "queued": self.queue.qsize(),
            "active_part_id": self.active.part_id if self.active else None,
            "pass": self.accepted, "fail": self.rejected,
            "unresolved_job_ids": list(self.unresolved),
            "inspection_complete": len(self.results) == self.target and self.target > 0,
        }

    async def reserve_part(self):
        """Call BEFORE issuing a production job on A.

        The returned numeric ID is the part_id that production, queueing,
        inspection, and results must preserve. A reserved slot guarantees the
        production completion has somewhere to wait for inspection.
        """
        async with self.condition:
            while self._slots_used >= self.capacity:
                if self.state != "RUNNING":
                    raise GatewayFault(self.fault_reason or "dispatch unavailable")
                if self.full_policy == "fault":
                    self.state, self.fault_reason = "FAULT", "inspection queue reservation capacity exhausted"
                    self.condition.notify_all()
                    raise GatewayFault(self.fault_reason)
                await self.condition.wait()
            if self.state != "RUNNING" or len(self.parts) >= self.target:
                raise GatewayFault("run unavailable or target already reserved")
            if not self.client.link.fresh or self.client.link.terminal_conflict:
                self.state, self.fault_reason = "FAULT", "B is stale or has conflicting terminal evidence"
                self.condition.notify_all()
                raise GatewayFault(self.fault_reason)
            self._slots_used += 1
            try:
                part_id = await self.ledger.allocate()
                if self.state != "RUNNING" or not self.client.link.fresh or self.client.link.terminal_conflict:
                    raise GatewayFault(self.fault_reason or "dispatch unavailable")
                part = Part(self.batch_id, part_id, self.client.ids.new("INSP"),
                            asyncio.get_running_loop().create_future())
                self.parts[part_id] = part
                await self.ledger.record("reserved", {"batch_id": self.batch_id,
                                                     "part_id": part_id, "job_id": part.job_id})
                return part
            except BaseException:
                self._slots_used -= 1
                self.condition.notify_all()
                raise

    async def produced(self, part):
        """Production completion hook; never fabricates production evidence."""
        async with self.condition:
            if self.parts.get(part.part_id) is not part or part.batch_id != self.batch_id:
                raise GatewayFault("unknown/wrong-batch production completion")
            if part.produced:
                return False
            if self.state not in {"RUNNING", "FAULT"}:
                raise GatewayFault("run is closed; production evidence belongs to its original history")
            part.produced = True
            self.queue.put_nowait(part)  # Capacity was reserved before production.
            self.condition.notify_all()
            await self.ledger.record("produced", {"batch_id": part.batch_id,
                                                 "part_id": part.part_id, "job_id": part.job_id})
            return True

    async def _fault(self, reason):
        async with self.condition:
            if self.state != "FAULT":
                self.state, self.fault_reason = "FAULT", reason
            self.condition.notify_all()

    async def _health(self):
        while not self._stopping:
            await asyncio.sleep(0.1)
            if self.client.link.terminal_conflict:
                identifier, reason = self.client.link.terminal_conflict
                if identifier in self.results:
                    self.unresolved[identifier] = self.results[identifier]
                await self._fault(reason)
            if not self.client.link.fresh:
                await self._fault("B disconnected or heartbeat became stale")

    async def _worker(self):
        try:
            while not self._stopping:
                async with self.condition:
                    await self.condition.wait_for(
                        lambda: self._stopping or (self.state == "RUNNING" and not self.queue.empty()))
                    if self._stopping:
                        return
                    part = self.queue.get_nowait()
                    self.active = part
                async with self.operation_lock:
                    request = self.requests.get(part.job_id)
                    if request is None:
                        request = self.client.inspection(part.part_id, part.job_id)
                        self.requests[part.job_id] = request
                        self.frozen_settings[part.job_id] = self.client.settings.fields()
                    await self.ledger.record("inspection_request", request)
                    # File I/O/configuration waits can yield to a Fault. Recheck
                    # before the single submission point and retain the slot
                    # while this part has not actually been dispatched.
                    async with self.condition:
                        if not self.client.link.fresh or self.client.link.terminal_conflict:
                            self.state = "FAULT"
                            self.fault_reason = "B is stale or has conflicting terminal evidence"
                        if self.state != "RUNNING":
                            self.queue.put_nowait(part)
                            self.queue.task_done()
                            self.active = None
                            self.condition.notify_all()
                            continue
                        part.dispatched = True
                        self._slots_used -= 1
                        self.condition.notify_all()
                    outcome = await self.client.controller.run(
                        request, duration_ms=self.frozen_settings[part.job_id]["inspection_time_ms"],
                        expected_settings=self.frozen_settings[part.job_id])
                await self.ledger.record("inspection_outcome", asdict(outcome))
                self.active = None
                if self.client.link.terminal_conflict:
                    await self._fault("conflicting terminal response")
                if outcome.state != "COMPLETED" or self.state == "FAULT":
                    self.unresolved[part.job_id] = outcome
                    await self._fault(outcome.reason or "inspection needs explicit reconciliation")
                    if not part.future.done():
                        part.future.set_result(outcome)
                else:
                    await self._account(part, outcome)
                self.queue.task_done()
        except asyncio.CancelledError:
            if self.active:
                part = self.active
                self.unresolved[part.job_id] = None
                self.state, self.fault_reason = "FAULT", "gateway stopped while inspection was pending"
                await self.ledger.record("shutdown_unresolved", {"job_id": part.job_id,
                                                                 "batch_id": part.batch_id})
                if not part.future.done():
                    part.future.set_result(Outcome("UNRESOLVED", part.job_id, None,
                                                   Evidence(), self.fault_reason))
                self.active = None
            raise
        except Exception as exc:
            if self.active:
                part = self.active
                self.unresolved[part.job_id] = None
                if not part.future.done():
                    part.future.set_result(Outcome("UNRESOLVED", part.job_id, None,
                                                   Evidence(), str(exc)))
                self.active = None
            await self._fault(f"inspection worker failed: {exc}")

    async def _account(self, part, outcome):
        if part.job_id in self.results:
            if self.results[part.job_id].result != outcome.result:
                await self._fault("conflicting terminal inspection evidence")
                raise GatewayFault(self.fault_reason)
            return
        # Controller already validated the original ID, part, run, boot,
        # configuration, explicit verdict and elapsed duration.
        await self.ledger.record("accounted", asdict(outcome))
        self.results[part.job_id] = outcome
        if outcome.result["verdict"] == "PASS":
            self.accepted += 1
        else:
            self.rejected += 1
        if not part.future.done():
            part.future.set_result(outcome)
        async with self.condition:
            self.condition.notify_all()

    async def reconfigure(self, settings):
        if self.state != "RUNNING" or self.active or self.operation_lock.locked():
            raise GatewayFault("configuration is BUSY or run is unavailable")
        async with self.operation_lock:
            outcome = await self.client.configure(settings)
        await self.ledger.record("reconfigure", asdict(outcome))
        if outcome.state != "COMPLETED":
            await self._fault("runtime configuration did not complete")
        return outcome

    async def reconcile(self, job_id):
        """Explicit read-only recovery; this never resumes dispatch."""
        if self.state != "FAULT" or job_id not in self.unresolved:
            raise GatewayFault("no matching unresolved inspection")
        async with self.operation_lock:
            outcome = await self.client.query(job_id)
        await self.ledger.record("reconciliation_query", asdict(outcome))
        target = outcome.result.get("target") if outcome.state == "COMPLETED" else None
        if not target:
            return outcome
        request = self.requests[job_id]
        translated = {**target, "boot_id": request["boot_id"]}
        if not self.client.controller._identity(translated, request):
            raise GatewayFault("reconciliation target context does not match")
        if target.get("state") == "REJECTED":
            original = self.unresolved[job_id]
            if job_id in self.results or (original and original.evidence.acceptance_established_by):
                raise GatewayFault("rejection contradicts prior accepted/completed evidence")
            self.unresolved.pop(job_id)
            return outcome
        if target.get("state") != "COMPLETED":
            return outcome
        frozen = self.frozen_settings[job_id]
        result = self.client.controller._result(
            target, request, frozen["inspection_time_ms"], frozen)
        recovered = Outcome("COMPLETED", job_id, result, outcome.evidence,
                            "explicit historical reconciliation; dispatch remains stopped")
        await self._account(self.parts[request["part_id"]], recovered)
        self.unresolved.pop(job_id)
        if self.client.link.terminal_conflict and self.client.link.terminal_conflict[0] == job_id:
            self.client.link.terminal_conflict = None
        return recovered

    async def resume_after_reconciliation(self):
        """Explicit operator recovery hook; no automatic resume on reconnect."""
        if (self._stopping or self.state != "FAULT" or self.unresolved or self.active
                or self.client.link.terminal_conflict
                or not self.client.link.fresh or self.client.link.heartbeat["state"] != "IDLE"
                or not self.client.link.heartbeat["run_open"]
                or self.client.link.heartbeat["batch_id"] != self.batch_id
                or self.client.link.heartbeat["run_no"] != self.client.run_no):
            raise GatewayFault("fresh same-boot idle/run evidence and resolved work are required")
        async with self.condition:
            self.state, self.fault_reason = "RUNNING", None
            self.condition.notify_all()

    async def wait_inspection(self):
        async with self.condition:
            await self.condition.wait_for(
                lambda: self.state == "FAULT" or len(self.results) == self.target)
        if self.state == "FAULT":
            raise GatewayFault(self.fault_reason)
        return self.snapshot()

    async def close_run(self):
        if self.client.link.terminal_conflict:
            await self._fault("conflicting terminal response")
            raise GatewayFault("reconcile conflicting terminal evidence before normal closure")
        if (len(self.results) != self.target or self.unresolved or self.active
                or not self.queue.empty() or self._slots_used):
            raise GatewayFault("run is incomplete; reconcile and finish it before normal closure")
        async with self.operation_lock:
            outcome = await self.client.close_run()
        await self.ledger.record("close", asdict(outcome))
        if outcome.state != "COMPLETED":
            await self._fault("run closure did not complete")
            return outcome
        self.state = "IDLE"
        self.fault_reason = None
        await self.shutdown()
        return outcome

    async def close_incomplete(self):
        """Explicit operator action after read-only reconciliation.

        No uncertain verdict is invented. An acknowledged idle CLOSE fences
        all old requests before another batch can be started.
        """
        heartbeat = self.client.link.heartbeat
        if (self.state != "FAULT" or self.active or not self.client.link.fresh or
                not heartbeat or heartbeat["state"] != "IDLE" or
                heartbeat["run_no"] != self.client.run_no or
                heartbeat["batch_id"] != self.batch_id):
            raise GatewayFault("fresh same-boot idle evidence is required to close an incomplete run")
        # Every unresolved operation must first get an explicit read-only query.
        for identifier in list(self.unresolved):
            await self.reconcile(identifier)
        async with self.operation_lock:
            outcome = await self.client.close_run()
        await self.ledger.record("incomplete_close", {"outcome": asdict(outcome),
                                                    "batch": self.snapshot()})
        if outcome.state != "COMPLETED":
            return outcome
        for part in self.parts.values():
            if not part.future.done():
                part.future.set_result(Outcome("NOT_DISPATCHED", part.job_id, None,
                                               Evidence(), "run explicitly closed incomplete"))
        self.state = "IDLE"
        self.fault_reason = None
        await self.shutdown()
        return outcome

    async def shutdown(self):
        if self.state == "RUNNING":
            self.state, self.fault_reason = "FAULT", "gateway stopped with an open run"
        self._stopping = True
        async with self.condition:
            self.condition.notify_all()
        for task in (self.worker, self.health):
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in (self.worker, self.health) if t), return_exceptions=True)
        for part in self.parts.values():
            if not part.dispatched and not part.future.done():
                part.future.set_result(Outcome("NOT_DISPATCHED", part.job_id, None,
                                               Evidence(), "gateway stopped before submission"))
        await self.client.close()
