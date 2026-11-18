"""One owner for operator commands, deduplication, liveness and display facts."""
import asyncio
from dataclasses import asdict
import json
import math
import uuid
from gateway.inspection.client import Settings
from gateway.inspection.coordinator import GatewayFault
from gateway.inspection.wire import ID, uint
from gateway.production.client import ProductionSettings

ACTIONS = {"start", "pause", "resume", "stop", "configure", "reconcile", "continue", "recover_a", "recover_b", "close_orphans"}


class AdmissionError(Exception):
    def __init__(self, message, status=409):
        self.status = status
        super().__init__(message)


def validate_settings(body):
    if not uint(body.get("batch_size"), 64, 1):
        raise ValueError("Batch size must be 1–64 whole parts")
    a = ProductionSettings(body.get("production_time_ms"))
    b = Settings(body.get("inspection_time_ms"), body.get("N"), body.get("K"))
    return a, b


class OperatorService:
    def __init__(self, core, *, simulation=False, factories=None, lease_s=5.0, history_limit=10000):
        if not math.isfinite(lease_s) or lease_s <= 0:
            raise ValueError("lease_s must be finite and positive")
        self.core, self.simulation = core, simulation
        self.factories = factories or {}
        self.gateway_id = "GW-" + uuid.uuid4().hex
        self.sequence = 0
        self.records = {}
        self.history_limit = history_limit
        self.active = None
        self.monitor = None
        self.auto_close = None
        self.owner = None
        self.last_alive = 0.0
        self.last_ack = -1
        self.lease_s = lease_s
        self.tasks = set()
        self.applied = None
        self.started_at = None
        self.ended_ms = None
        self.pause_reason = None
        self.progress = {}
        self._closing = False
        self._connect_after = 0.0
        self.closing_orphans = False
        self.orphan_closures = {}
        self.last_checkpoint = 0.0
        for station, client in (("A", core.a), ("B", core.b.client)):
            self._observe(station, client)

    def _observe(self, station, client):
        original = client.link.log
        def log(kind, message):
            original(kind, message)
            identifier = message.get("job_id", message.get("cmd_id")) if isinstance(message, dict) else None
            if kind == "receive" and identifier:
                key = (station, identifier)
                entry = self.progress.setdefault(key, {})
                stage = message.get("type")
                now = asyncio.get_running_loop().time()
                if stage in {"ACCEPTED", "COMPLETED"} or (stage == "STATUS" and message.get("state") == "IN_PROGRESS"):
                    entry.setdefault("accepted_at", now)
                if stage in {"COMPLETED", "REJECTED"}:
                    entry.setdefault("terminal_at", now)
                entry["stage"] = stage
        client.link.log = log

    @property
    def owner_live(self):
        return bool(self.owner and asyncio.get_running_loop().time() - self.last_alive < self.lease_s)

    def alive(self, operator, boot, sequence):
        if (not isinstance(operator, str) or not ID.fullmatch(operator) or boot != self.gateway_id or
                not uint(sequence, 2**53-1) or sequence > self.sequence):
            raise AdmissionError("Invalid operator liveness acknowledgement")
        if self.owner_live and self.owner != operator:
            return False
        if self.owner != operator:
            self.owner, self.last_ack = operator, -1
        if sequence > self.last_ack:
            self.last_ack = sequence
            self.last_alive = asyncio.get_running_loop().time()
        return True

    def _scope(self, body):
        return body.get("batch_id") == self.core.b.batch_id and self.core.b.batch_id is not None

    def _validate(self, action, body):
        common = {"schema_version", "gateway_id", "operator_id", "cmd_id"}
        fields = {"batch_size", "production_time_ms", "inspection_time_ms", "N", "K"}
        allowed = common | (fields | {"queue_capacity", "full_policy"} if action == "start" else
                            {"batch_id"} | (fields if action == "configure" else set()))
        if set(body) != allowed:
            raise ValueError("Unexpected or missing command fields")
        if type(body["schema_version"]) is not int or body["schema_version"] != 1:
            raise ValueError("Unsupported command schema")
        if action == "start":
            validate_settings(body)
            if not uint(body["queue_capacity"], 64, 1) or not isinstance(body["full_policy"], str) or body["full_policy"] not in {"block", "fault"}:
                raise ValueError("Choose queue capacity 1–64 and block/Fault policy")
            if self.core.state != "IDLE" or self.orphaned:
                raise AdmissionError("Close/recover the old batch before Start")
            if not all(client.link.fresh for client in (self.core.a, self.core.b.client)):
                raise AdmissionError("Both stations must be freshly connected")
        elif action == "close_orphans":
            if not self.can_close_orphans:
                raise AdmissionError("Old scopes require fresh idle evidence from both stations")
        else:
            if not self._scope(body):
                raise AdmissionError("Command targets a different or ended batch")
            state = self.core.state
            if action == "pause" and state != "RUNNING":
                raise AdmissionError("Pause requires Running")
            if action == "resume" and (state != "PAUSED" or not self.can_resume):
                raise AdmissionError("Resume requires fresh current-run status from both stations")
            if action == "configure":
                validate_settings(body)
                if state != "PAUSED" or body["batch_size"] != self.core.b.target:
                    raise AdmissionError("Settings require Pause and the original batch target")
                if self.core.active or self.core.b.active:
                    raise AdmissionError("Wait for current jobs to finish before changing settings")
            if action in {"reconcile", "continue", "recover_a", "recover_b"} and state != "FAULT":
                raise AdmissionError("Recovery action requires Fault")
            if action == "continue" and self.core.configuration_hold:
                raise AdmissionError("Settings were not jointly confirmed; end this batch before new work")
            if action == "stop" and state == "IDLE":
                raise AdmissionError("No open batch to Stop")

    @property
    def can_resume(self):
        if self.core.state != "PAUSED" or self.core.ending: return False
        for client in (self.core.a, self.core.b.client):
            h=client.link.heartbeat
            if (not client.link.fresh or client.link.terminal_conflict or not h or not h["run_open"] or
                    h["run_no"]!=client.run_no or h["batch_id"]!=self.core.b.batch_id): return False
        return not self.core.configuration_hold and not (set(self.core.unresolved)-self.core.isolated or set(self.core.b.unresolved)-self.core.b.isolated)

    @property
    def orphaned(self):
        if self.core.b.batch_id is not None:
            return False
        return any(c.link.heartbeat and c.link.heartbeat.get("run_open") for c in (self.core.a, self.core.b.client))

    @property
    def can_close_orphans(self):
        return self.orphaned and all(c.link.fresh and c.link.heartbeat and
            c.link.heartbeat["state"] == "IDLE" and not c.link.terminal_conflict
            for c in (self.core.a, self.core.b.client))

    async def submit(self, action, body):
        if action not in ACTIONS or not isinstance(body, dict):
            raise AdmissionError("Unknown command", 404)
        identifier = body.get("cmd_id")
        if not isinstance(identifier, str) or not ID.fullmatch(identifier):
            raise AdmissionError("Missing/invalid command identity", 400)
        fingerprint = json.dumps({"action": action, "body": body}, sort_keys=True, separators=(",", ":"), allow_nan=False)
        previous = self.records.get(identifier)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise AdmissionError("ID_CONFLICT: original command contents are immutable")
            return previous["ack_status"], dict(previous["ack"])
        if body.get("gateway_id") != self.gateway_id:
            raise AdmissionError("GATEWAY_RESTARTED: old work cannot be replayed")
        if not self.owner_live or body.get("operator_id") != self.owner:
            raise AdmissionError("Synchronize the controlling operator screen first")
        if len(self.records) >= self.history_limit:
            raise AdmissionError("Command history is full; no retained identity will be evicted", 503)
        now = asyncio.get_running_loop().time()
        record = {"cmd_id": identifier, "command": action, "phase": "received", "result": "Gateway registered the original request",
                  "received_at": now, "accepted_at": None, "completed_at": None, "fingerprint": fingerprint,
                  "body": dict(body), "ack_status": 202}
        self.records[identifier] = record  # Registration precedes reported receipt.
        reason = None
        try:
            self._validate(action, body)
            if self.active or (self.auto_close and not self.auto_close.done()):
                raise AdmissionError("Another operator control is still pending")
        except (ValueError, AdmissionError) as exc:
            reason = str(exc)
            record["ack_status"] = exc.status if isinstance(exc, AdmissionError) else 422
        record["ack"] = {"schema_version": 1, "gateway_id": self.gateway_id, "cmd_id": identifier,
                         "command": action, "accepted": reason is None,
                         "phase": "rejected" if reason else "accepted",
                         "message": reason or "Registered and accepted; completion will be reported separately"}
        record["phase"] = record["ack"]["phase"]
        record["result"] = record["ack"]["message"]
        if reason is None:
            record["accepted_at"] = now
            duration = max(body.get("production_time_ms", 0), body.get("inspection_time_ms", 0),
                           self.core.a.settings.production_time_ms if self.core.a.settings else 0,
                           self.core.b.client.settings.inspection_time_ms if self.core.b.client.settings else 0) / 1000
            window = duration + 90 if action == "stop" else 65 if action in {"continue", "close_orphans"} else 35
            record["absolute_at"] = now + window
            record["ack"]["completion_window_ms"] = int(window * 1000)
            self.active = identifier
            task = asyncio.create_task(self._execute(record))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        else:
            record["completed_at"] = now
        return record["ack_status"], dict(record["ack"])

    async def _execute(self, record):
        core, action, body = self.core, record["command"], record["body"]
        try:
            await core.b.ledger.record("operator_received", {"gateway_id": self.gateway_id, "request": body, "action": action})
            async with asyncio.timeout_at(record["absolute_at"]):
                if action == "start":
                    a, b = validate_settings(body)
                    core.b.capacity, core.b.full_policy = body["queue_capacity"], body["full_policy"]
                    self.started_at = asyncio.get_running_loop().time()
                    self.ended_ms = None
                    await core.start_run(a, b, body["batch_size"])
                    self.applied = {key: body[key] for key in ("batch_size", "production_time_ms", "inspection_time_ms", "N", "K")}
                    self.pause_reason = None
                    text = "Both station configurations confirmed; this batch is Running"
                elif action == "pause":
                    await core.pause(); self.pause_reason = "Operator paused dispatch"
                    text = "Paused: current jobs may finish; remaining work stays in this same batch"
                elif action == "resume":
                    await core.resume(); self.pause_reason = None
                    text = "Resumed the same batch with its original parts and results"
                elif action == "stop":
                    await core.stop_batch(); self._freeze_elapsed()
                    text = "Batch ended with all confirmed results retained: " + core.snapshot()["outcome"]
                elif action == "configure":
                    a, b = validate_settings(body)
                    await core.apply_settings(a, b)
                    self.applied = {key: body[key] for key in ("batch_size", "production_time_ms", "inspection_time_ms", "N", "K")}
                    text = "Both settings confirmed for future jobs; batch remains Paused"
                elif action == "reconcile":
                    for identifier in list(core.unresolved):
                        if identifier not in core.isolated: await core.reconcile_production(identifier)
                    for identifier in list(core.b.unresolved):
                        if identifier not in core.b.isolated: await core.b.reconcile(identifier)
                    text = "Read-only result lookup finished; dispatch remains held until explicit recovery"
                elif action == "continue":
                    await core.continue_remaining(); self.pause_reason = None
                    text = "Guarded continuation established; remaining original-target parts may proceed"
                elif action in {"recover_a", "recover_b"}:
                    station = action[-1].upper()
                    replacement = self.factories[station]()
                    try:
                        await core.bind_restarted_station(station, replacement)
                    except BaseException:
                        await replacement.close(); raise
                    self._observe(station, replacement)
                    text = "New boot fenced old requests; end the old batch before starting another"
                else:
                    await self._close_orphans()
                    text = "Unowned idle station scopes closed; missing historical outcomes remain unknown"
            record["phase"], record["result"] = "completed", text
        except asyncio.CancelledError:
            record["phase"], record["result"] = "unresolved", "Gateway stopped while this command was pending"
            raise
        except Exception as exc:
            record["phase"], record["result"] = "unresolved", str(exc)
            if core.b.batch_id:
                await core._hold("Operator " + action + " requires recovery: " + str(exc))
        finally:
            record["completed_at"] = asyncio.get_running_loop().time()
            self.active = None
            await core.b.ledger.record("operator_outcome", self.public(record))

    async def _close_orphans(self):
        self.closing_orphans = True
        try:
            for station, client in (("A", self.core.a), ("B", self.core.b.client)):
                h = client.link.heartbeat
                if not h or not client.link.fresh or h["state"] != "IDLE":
                    raise GatewayFault("Wait for fresh idle evidence from both stations")
                if not h["run_open"]:
                    continue
                client.select_run(h["batch_id"], h["run_no"])
                previous = self.orphan_closures.get(station)
                if previous:
                    result = await client.query(previous["cmd_id"])
                    target = result.result.get("target") if result.state == "COMPLETED" else None
                    if not target or target.get("state") != "COMPLETED":
                        raise GatewayFault("Prior orphan closure is still unresolved")
                    client.controller._result(target, previous, 0)
                else:
                    request = client.request("CLOSE")
                    self.orphan_closures[station] = request
                    result = await client.controller.run(request)
                    if result.state != "COMPLETED": raise GatewayFault("Station closure unresolved")
            self.core.state, self.core.fault_reason = "IDLE", None
        finally:
            self.closing_orphans = False

    def public(self, record):
        return {**{key: record.get(key) for key in ("cmd_id", "command", "phase", "result", "received_at", "accepted_at", "completed_at", "absolute_at")},
                "completion_window_ms": record["ack"].get("completion_window_ms")}

    def lookup(self, identifier):
        record = self.records.get(identifier)
        return {"gateway_id": self.gateway_id, **self.public(record)} if record else None

    def _freeze_elapsed(self):
        if self.started_at is not None and self.ended_ms is None:
            self.ended_ms = int((asyncio.get_running_loop().time() - self.started_at)*1000)

    def snapshot(self):
        self.sequence += 1
        core, b = self.core, self.core.b
        raw = core.snapshot()
        state = raw["state"].title()
        fault = raw["fault_reason"] if state == "Fault" else None
        if self.orphaned:
            state, fault = "Fault", "Gateway has no active batch record, but a station retains an old run; close its idle scope explicitly"
        parts = []
        for part in b.parts.values():
            production_id = core.production_ids.get(part.part_id)
            status = "waiting"
            if part.job_id in b.results: status = b.results[part.job_id].result["verdict"].lower()
            elif production_id in core.unresolved or part.job_id in b.unresolved: status = "unresolved"
            elif core.active is part: status = "producing"
            elif b.active is part and part.dispatched: status = "inspecting"
            elif part.produced: status = "queued" if not part.dispatched else "uninspected"
            if state == "Idle" and status not in {"pass", "fail", "unresolved"}: status = "uninspected" if part.produced else "not_started"
            parts.append({"part_id": part.part_id, "status": status, "produced": part.produced,
                          "production_job_id": production_id, "inspection_job_id": part.job_id,
                          "isolated": production_id in core.isolated or part.job_id in b.isolated,
                          "production_result": asdict(core.outcomes[production_id]) if production_id in core.outcomes else None,
                          "inspection_result": asdict(b.results[part.job_id]) if part.job_id in b.results else None})
        stations = {}
        for name, station, client, active in (("production", "A", core.a, core.active), ("inspection", "B", b.client, b.active)):
            identifier = core.production_ids.get(active.part_id) if active and station == "A" else active.job_id if active else None
            progress = self.progress.get((station, identifier), {})
            accepted = progress.get("accepted_at")
            duration = (core.settings.get(identifier, {}).get("production_time_ms") if station == "A" else
                        b.frozen_settings.get(identifier, {}).get("inspection_time_ms")) if active else None
            remaining = max(0, int(duration - (asyncio.get_running_loop().time()-accepted)*1000)) if duration is not None and accepted is not None else None
            stations[name] = {"connected": client.link.fresh, "busy": bool(active and identifier),
                "part_id": active.part_id if active and identifier else None, "remaining_ms": remaining,
                "phase": "active" if accepted is not None else "awaiting_acceptance" if active else "idle",
                "boot_id": client.link.boot_id, "restarted": client.link.failure.__class__.__name__ == "Restarted"}
        outcome = "none" if b.batch_id is None else "completed" if state == "Idle" and raw["inspection_complete"] else "incomplete" if state == "Idle" else "active"
        queued = [p["part_id"] for p in parts if p["status"] == "queued"]
        elapsed = self.ended_ms if self.ended_ms is not None else int((asyncio.get_running_loop().time()-self.started_at)*1000) if self.started_at is not None else 0
        return {"schema_version": 1, "type": "status", "simulation": self.simulation,
            "gateway_id": self.gateway_id, "status_seq": self.sequence, "state": state, "fault": fault,
            "settings": self.applied, "batch": {"id": b.batch_id, "target": b.target, "outcome": outcome, "elapsed_ms": elapsed},
            "counts": {"produced": raw["produced"], "inspected": len(b.results), "passed": b.accepted,
                       "failed": b.rejected, "unresolved": raw["unresolved"], "unstarted": b.target-len(core.production_ids),
                       "not_inspected": b.target-len(b.results)},
            "queue": {"size": len(queued), "capacity": b.capacity, "part_ids": queued, "full_policy": b.full_policy,
                      "reserved": b._slots_used}, "stations": stations, "parts": parts,
            "command_results": [self.public(r) for r in list(self.records.values())[-100:]],
            "operator": {"controller_id": self.owner if self.owner_live else None, "lease_ms": int(self.lease_s*1000)},
            "pause_reason": self.pause_reason, "control_pending": self.records[self.active]["command"] if self.active else "completing_batch" if self.auto_close and not self.auto_close.done() else None,
            "configuration_hold": core.configuration_hold, "orphaned": self.orphaned, "can_close_orphans": self.can_close_orphans, "can_edit": core.state == "PAUSED" and not core.active and not b.active and all(core._ready(c) for c in (core.a,b.client)),
            "can_resume": self.can_resume,
            "ready": all(client.link.fresh and client.link.heartbeat and
                         (core.state!="IDLE" or not client.link.heartbeat["run_open"])
                         for client in (core.a,b.client))}

    async def _tick(self):
        while not self._closing:
            await asyncio.sleep(.1)
            now = asyncio.get_running_loop().time()
            if not self.active and not (self.auto_close and not self.auto_close.done()):
                if not self.owner_live and self.core.state == "RUNNING":
                    identifier = "AUTOPAUSE-GW-" + uuid.uuid4().hex
                    self.pause_reason = "Operator screen disconnected/stale; synchronize and press Resume"
                    try:
                        await self.core.pause(self.pause_reason)
                        await self.core.b.ledger.record("automatic_pause", {"cmd_id": identifier, "reason": self.pause_reason})
                    except GatewayFault:
                        pass
                raw = self.core.snapshot()
                producer = self.core.producer
                if (self.core.state in {"RUNNING","PAUSED"} and len(self.core.b.parts)==self.core.b.target and producer and producer.done() and
                    all(p.future.done() for p in self.core.b.parts.values()) and not self.core.active and not self.core.b.active and
                    all(self.core._ready(c) for c in (self.core.a, self.core.b.client))):
                    self.auto_close = asyncio.create_task(self._finish_batch())
                if now >= self._connect_after and not self.core.active and not self.core.b.active:
                    self._connect_after = now+2
                    for client in (self.core.a, self.core.b.client):
                        if not client.link.fresh:
                            try: await asyncio.wait_for(client.connect(), 3)
                            except Exception: pass

    async def _finish_batch(self):
        try:
            # All original target positions are settled, including guarded
            # isolated cases. Close truthfully as completed or incomplete.
            await self.core.close_run(incomplete=not self.core.snapshot()["inspection_complete"])
            self._freeze_elapsed()
        except Exception as exc:
            await self.core._hold("Batch closure requires recovery: " + str(exc))

    async def start(self):
        self.monitor = asyncio.create_task(self._tick())

    async def shutdown(self):
        self._closing = True
        jobs = [self.monitor, self.auto_close, *self.tasks]
        for task in jobs:
            if task: task.cancel()
        await asyncio.gather(*(t for t in jobs if t), return_exceptions=True)
        await self.core.shutdown()
