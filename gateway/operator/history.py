"""Read-only batch reports projected from the existing durable application journal.

No report files and no execution restoration. The two small SQLite indexes only
allocate stable display names; original protocol identities remain authoritative.
"""
import asyncio
from contextlib import closing
from copy import deepcopy
import json
import re
import sqlite3

SESSION = re.compile(r"^(?:(.+)-(GW|OP)-([0-9a-f]{32})-(\d+)|(GW|OP)-([0-9a-f]{32}))$")


class History:
    def __init__(self, ledger):
        self.ledger = ledger
        self.lock = asyncio.Lock()
        self.cursor = 0
        self.reports = {}
        self.aliases = {}
        self.numbers = {}
        self.operations = {}
        self.current = None
        self.pending_start = None
        self.error = None
        self.live_batch = None

    def label(self, identifier):
        match = SESSION.fullmatch(identifier or "")
        if not match:
            return identifier or ""
        action, issuer, session, counter, bare_issuer, bare_session = match.groups()
        name = self.aliases.get(f"{issuer or bare_issuer}:{session or bare_session}")
        if name is None:
            return (action + "-" if action else "") + (issuer or bare_issuer) + "-session pending"
        return f"{action}-{issuer}-{name}-{int(counter)}" if action else f"{bare_issuer}-{name}"

    def batch_label(self, identifier):
        number = self.numbers.get(identifier)
        return f"Batch {number}" if number else "Batch pending"

    def _register(self, db, value):
        if isinstance(value, dict):
            for child in value.values():
                self._register(db, child)
        elif isinstance(value, list):
            for child in value:
                self._register(db, child)
        elif isinstance(value, str) and (match := SESSION.fullmatch(value)):
            _, issuer, session, _, bare_issuer, bare_session = match.groups()
            key = f"{issuer or bare_issuer}:{session or bare_session}"
            if key not in self.aliases:
                db.execute("INSERT OR IGNORE INTO display_sessions(identity) VALUES (?)", (key,))
                number = db.execute("SELECT number FROM display_sessions WHERE identity=?", (key,)).fetchone()[0]
                self.aliases[key] = f"S{number:02d}"

    def _batch(self, db, identifier):
        if identifier not in self.reports:
            if identifier not in self.numbers:
                db.execute("INSERT INTO display_batches(identity) VALUES (?)", (identifier,))
            number = self.numbers.get(identifier)
            if number is None:
                number = db.execute("SELECT number FROM display_batches WHERE identity=?", (identifier,)).fetchone()[0]
            self.numbers[identifier] = number
            self.reports[identifier] = {"schema_version": 2, "batch": {"id": identifier,
                "display_id": f"Batch {number}", "target": None, "outcome": "interrupted_or_open", "elapsed_ms": None},
                "settings": None, "counts": {}, "parts": [], "operations": [], "controls": [],
                "notes": ["Times are gateway monotonic observations, not device execution timestamps.",
                          "Null acknowledgement times mean no original acknowledgement was observed.",
                          "History is read-only and never restarts work. Use serial traces and Wireshark for transport evidence."]}
        return self.reports[identifier]

    @staticmethod
    def _scope(value):
        if not isinstance(value, dict):
            return None
        if isinstance(value.get("batch_id"), str):
            return value["batch_id"]
        if isinstance(value.get("batch"), dict) and value["batch"].get("id"):
            return value["batch"]["id"]
        for key in ("request", "result", "outcome", "data"):
            if identifier := History._scope(value.get(key)):
                return identifier
        return None

    def _operation(self, report, identifier, station=None):
        op = next((o for o in report["operations"] if o["id"] == identifier), None)
        if op is None:
            op = {"id": identifier, "station": station, "phase": "unknown", "request": None,
                  "result": None, "evidence": None, "observations": [], "duplicate_observations": 0}
            report["operations"].append(op)
        if station:
            op["station"] = station
        self.operations[identifier] = report["batch"]["id"]
        return op

    def _project(self, db, kind, body):
        identifier = body.get("identifier") or body.get("job_id") or body.get("cmd_id")
        batch = self._scope(body) or self.operations.get(identifier)
        if kind == "operator_outcome" and "batch_id" in body and body["batch_id"] is None and not batch:
            return  # Rejected/unscoped controls are in the journal, not another batch.
        if kind == "operator_received" and body.get("action") == "start":
            self.pending_start = body["request"]
            return
        if kind == "batch_open":
            self.pending_start = body.get("request", self.pending_start)
        if not batch and kind not in {"station_observation"}:
            batch = self.current
        if not batch:
            return
        report = self._batch(db, batch)
        if batch != self.current and kind in {"batch_open", "configure"}:
            self.current = batch
            if self.pending_start:
                request = self.pending_start
                report["settings"] = {k: request[k] for k in ("batch_size", "production_time_ms", "inspection_time_ms", "N", "K") if k in request}
                report["batch"]["target"] = request.get("batch_size")
                report["queue"] = {"capacity": request.get("queue_capacity"), "full_policy": request.get("full_policy")}
                self.operations[request["cmd_id"]] = batch
                self.pending_start = None
        if kind == "operator_batch_view":
            closed_outcome = report["batch"]["outcome"]
            for key in ("batch", "settings", "counts", "parts", "queue"):
                report[key] = deepcopy(body[key])
            if closed_outcome in {"completed", "incomplete"}:
                # A view captured before closure can finish writing later.
                # Confirmed scope closure is never undone by that stale view.
                report["batch"]["outcome"] = closed_outcome
            report["batch"]["display_id"] = self.batch_label(batch)
            report["saved_state"] = body["state"]
            report["saved_fault"] = body.get("fault")
            for part in report["parts"]:
                # Outcomes live once in operations; parts refer to their job IDs.
                part.pop("production_result", None)
                part.pop("inspection_result", None)
        elif kind == "batch_close":
            report["batch"].update(outcome="completed" if body.get("inspection_complete") and not body.get("unresolved") else "incomplete",
                                   target=body.get("target", report["batch"]["target"]))
        elif kind == "reserved":
            if not any(p["part_id"] == body["part_id"] for p in report["parts"]):
                report["parts"].append({"part_id": body["part_id"], "inspection_job_id": body["job_id"],
                    "production_job_id": None, "produced": False, "status": "waiting", "isolated": False})
        elif kind == "produced":
            for part in report["parts"]:
                if part["part_id"] == body["part_id"]:
                    part.update(produced=True, status="queued")
        elif kind == "operator_outcome":
            report["controls"] = [c for c in report["controls"] if c["cmd_id"] != identifier] + [body]
        elif kind == "station_observation":
            data = body["data"]
            oid = data.get("job_id", data.get("cmd_id"))
            if not oid:
                return
            op = self._operation(report, oid, body["station"])
            if body["event"] == "send":
                op["request"] = op["request"] or data
            elif body["event"] == "receive":
                fact = {"stage": data.get("type"), "state": data.get("state"), "observed_at": body["observed_at"]}
                if any(o["stage"] == fact["stage"] and o["state"] == fact["state"] for o in op["observations"]):
                    op["duplicate_observations"] += 1
                else:
                    op["observations"].append(fact)
        else:
            outcome = body.get("outcome") if isinstance(body.get("outcome"), dict) else body
            oid = outcome.get("identifier")
            if oid:
                station = "A" if kind.startswith("production") else body.get("station", "B")
                op = self._operation(report, oid, station)
                if kind == "accounted":
                    op["accounted"] = True
                # Recovery-query ACK times belong to the QUERY operation. Never
                # present those as the original execution's ACK timestamps.
                if "reconciliation" in (outcome.get("reason") or ""):
                    op["recovered_result"] = outcome.get("result")
                    op["phase"] = outcome["state"]
                    op["recovery_note"] = outcome["reason"]
                else:
                    op.update(phase=outcome.get("state", "unknown"), result=outcome.get("result"),
                              evidence=outcome.get("evidence"), reason=outcome.get("reason"))
                    for query_id, facts in (outcome.get("evidence") or {}).get("queries", {}).items():
                        query = self._operation(report, query_id, station)
                        query["evidence"] = facts
                        query["target_id"] = oid
                        query["phase"] = "query_response_observed" if facts.get("completed_observed_at") is not None else "query_unresolved"
                        query["validation_note"] = "Query stage observations; the parent operation holds the validated recovered outcome."
            elif kind in {"production_request", "inspection_request"}:
                oid = body.get("job_id")
                op = self._operation(report, oid, "A" if kind.startswith("production") else "B")
                op["request"] = body
                for part in report["parts"]:
                    if part["part_id"] == body["part_id"]:
                        part["production_job_id" if kind.startswith("production") else "inspection_job_id"] = oid

    def _refresh(self, identifiers):
        with closing(sqlite3.connect(self.ledger.path, timeout=2)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, kind TEXT, body TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS display_sessions (number INTEGER PRIMARY KEY AUTOINCREMENT, identity TEXT UNIQUE NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS display_batches (number INTEGER PRIMARY KEY AUTOINCREMENT, identity TEXT UNIQUE NOT NULL)")
            for key, number in db.execute("SELECT identity,number FROM display_sessions"):
                self.aliases[key] = f"S{number:02d}"
            for key, number in db.execute("SELECT identity,number FROM display_batches"):
                self.numbers[key] = number
            self._register(db, identifiers)
            for seq, kind, encoded in db.execute("SELECT seq,kind,body FROM events WHERE seq>? ORDER BY seq", (self.cursor,)).fetchall():
                body = json.loads(encoded)
                self._register(db, body)
                self._project(db, kind, body)
                self.cursor = seq

    async def refresh(self, identifiers=()):
        async with self.lock:
            task = asyncio.create_task(asyncio.to_thread(self._refresh, list(identifiers)))
            try:
                await asyncio.shield(task)
                self.error = None
            except asyncio.CancelledError:
                await task
                raise
            except Exception as exc:
                # Rebuild from the authoritative journal after a failed index
                # transaction; never skip partially projected rows.
                self.cursor = 0
                self.reports.clear()
                self.operations.clear()
                self.current = self.pending_start = None
                self.aliases.clear()
                self.numbers.clear()
                self.error = str(exc)
                raise

    def _report(self, identifier):
        if identifier not in self.reports:
            return None
        report = deepcopy(self.reports[identifier])
        if report["batch"]["outcome"] == "active" and identifier != self.live_batch:
            report["batch"]["outcome"] = "interrupted_or_open"
        for op in report["operations"]:
            op["display_id"] = self.label(op["id"])
        for control in report["controls"]:
            control["display_id"] = self.label(control["cmd_id"])
        # Legacy journals have outcomes but no full UI snapshot. Reconstruct
        # confirmed facts only; never invent missing times or a missing verdict.
        ops = {o["id"]: o for o in report["operations"]}
        for part in report["parts"]:
            production = ops.get(part.get("production_job_id"), {})
            inspection = ops.get(part.get("inspection_job_id"), {})
            if production.get("phase") == "COMPLETED":
                part["produced"] = True
            result = inspection.get("recovered_result") or inspection.get("result") or {}
            if inspection.get("phase") == "COMPLETED" and inspection.get("accounted") and result.get("verdict") in {"PASS", "FAIL"}:
                part["status"] = result["verdict"].lower()
            elif production.get("phase") == "UNRESOLVED" or inspection.get("phase") == "UNRESOLVED":
                part["status"] = "unresolved"
        parts = report["parts"]
        inspected = sum(p["status"] in {"pass", "fail"} for p in parts)
        target = report["batch"]["target"]
        report["counts"] = {"produced": sum(p["produced"] for p in parts), "inspected": inspected,
            "passed": sum(p["status"] == "pass" for p in parts), "failed": sum(p["status"] == "fail" for p in parts),
            "unresolved": sum(p["status"] == "unresolved" for p in parts),
            "unstarted": target - sum(bool(p["production_job_id"]) for p in parts) if target is not None else None,
            "not_inspected": target - inspected if target is not None else None}
        report["sessions"] = {key: value for key, value in self.aliases.items()
                              if any(key.split(":", 1)[1] in op["id"] for op in report["operations"] + [{"id": c["cmd_id"]} for c in report["controls"]])}
        return report

    async def report(self, identifier):
        await self.refresh()
        async with self.lock:
            return self._report(identifier)

    async def page(self, offset=0, limit=20):
        await self.refresh()
        async with self.lock:
            keys = sorted(self.reports, key=lambda key: self.numbers[key], reverse=True)
            items = []
            for key in keys[offset:offset+limit]:
                report = self._report(key)
                items.append({"batch": report["batch"], "counts": report["counts"]})
            return {"items": items, "total": len(keys), "offset": offset,
                    "next_offset": offset+limit if offset+limit < len(keys) else None}
