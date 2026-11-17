"""Member 3 test gateway. Simulated stations only; never use its verdicts as ESP32 evidence.

Run: python mock_gateway.py --port 8080
Open: http://127.0.0.1:8080
"""
import argparse
import asyncio
import contextlib
import copy
import json
import logging
import time
import uuid
from collections import OrderedDict, deque
from pathlib import Path

from aiohttp import web, WSMsgType

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("toy-test-gateway")
MAX_COMMANDS = 10000  # Reject new IDs when full; never evict accepted IDs within a boot.


def is_int(value, low, high):
    return type(value) is int and low <= value <= high


def validate_settings(body):
    bounds = {"batch_size": (1, 1000), "production_time_ms": (1, 3600000),
              "inspection_time_ms": (1, 3600000), "N": (1, 1000000), "K": (-1000000, 1000000)}
    for key, (low, high) in bounds.items():
        if not is_int(body.get(key), low, high):
            raise ValueError(f"{key} must be an integer from {low} to {high}")
    return {key: body[key] for key in bounds}


def valid_id(value):
    return isinstance(value, str) and 1 <= len(value) <= 128 and all(c.isascii() and (c.isalnum() or c in "_.:-") for c in value)


class Factory:
    def __init__(self, capacity=5):
        self.capacity = capacity
        self.reset()

    def reset(self):
        self.gateway_id = "mock-" + str(uuid.uuid4())
        self.seq = 0
        self.state, self.fault = "Idle", None
        self.settings = None
        self.batch_id, self.outcome = None, "none"
        self.parts, self.queue = [], deque()
        self.production, self.inspection = None, None
        self.produced = self.passed = self.failed = 0
        self.elapsed_ms = 0
        self.connected_a = self.connected_b = True
        self.records = OrderedDict()
        self.reject_next = False
        self.silent = False

    def result(self, cmd_id):
        record = self.records[cmd_id]
        return {"gateway_id": self.gateway_id, "cmd_id": cmd_id, "command": record["command"],
                "phase": record["phase"], "result": record["result"]}

    def ack(self, command, cmd_id, accepted, message):
        return {"schema_version": 1, "gateway_id": self.gateway_id, "command": command,
                "cmd_id": cmd_id, "accepted": accepted, "phase": "accepted" if accepted else "rejected", "message": message}

    def command(self, name, body):
        cmd_id = body.get("cmd_id")
        if not valid_id(cmd_id):
            raise ValueError("cmd_id must use 1–128 ASCII letters, digits, or _ . : -")
        # Boot precondition is checked before deduplication. Old work is never reissued after a restart.
        if body.get("gateway_id") != self.gateway_id:
            return self.ack(name, cmd_id, False, "Gateway boot changed; synchronize before issuing new work."), 409
        fingerprint = json.dumps({"command": name, "body": body}, sort_keys=True)
        if cmd_id in self.records:
            old = self.records[cmd_id]
            if old["fingerprint"] != fingerprint:
                return self.ack(name, cmd_id, False, "ID_CONFLICT: same cmd_id with different request."), 409
            LOG.info("duplicate cmd_id=%s: returned cached response", cmd_id)
            return copy.deepcopy(old["ack"]), old["http_status"]
        if len(self.records) >= MAX_COMMANDS:
            return self.ack(name, cmd_id, False, "Command capacity reached; no new work accepted."), 503
        error = None
        try:
            if body.get("schema_version") != 1:
                raise ValueError("schema_version must be 1")
            allowed = {"schema_version", "gateway_id", "cmd_id"}
            if name == "start":
                allowed |= {"batch_size", "production_time_ms", "inspection_time_ms", "N", "K"}
                settings = validate_settings(body)
                if self.state != "Idle" or not self.connected_a or not self.connected_b:
                    raise ValueError("Start requires Idle and both stations connected.")
            else:
                allowed.add("batch_id")
                if body.get("batch_id") != self.batch_id or self.outcome != "active":
                    raise ValueError("Command must target the current active batch.")
                if name == "pause" and self.state != "Running":
                    raise ValueError("Pause requires Running.")
                if name == "resume" and self.state != "Paused":
                    raise ValueError("Resume requires Paused.")
            if set(body) != allowed:
                raise ValueError("Unexpected or missing command fields.")
            if self.reject_next:
                self.reject_next = False
                raise ValueError("Controlled test rejection; no work started.")
        except ValueError as exc:
            error = str(exc)
        ack = self.ack(name, cmd_id, error is None, error or "Command validated and accepted.")
        record = {"command": name, "fingerprint": fingerprint, "ack": ack, "http_status": 422 if error else 202,
                  "phase": "rejected" if error else "accepted", "result": error or "Accepted"}
        self.records[cmd_id] = record
        LOG.info("acceptance cmd_id=%s command=%s accepted=%s", cmd_id, name, not error)
        if error:
            return ack, 422
        if name == "start":
            self.settings = settings
            self.batch_id = "batch-" + str(uuid.uuid4())
            self.parts = [{"part_id": i + 1, "status": "waiting"} for i in range(settings["batch_size"])]
            self.queue.clear()
            self.production = self.inspection = None
            self.produced = self.passed = self.failed = 0
            self.elapsed_ms = 0
            self.outcome, self.state, self.fault = "active", "Running", None
            result = "Batch started; simulated station configuration applied."
        elif name == "pause":
            self.state = "Paused"
            result = "Paused. Accepted work may finish; no new work starts."
        elif name == "resume":
            self.state = "Running"
            result = "Resumed the same batch."
        else:
            for job in [self.production, self.inspection]:
                if job:
                    self.parts[job["part_id"] - 1]["status"] = "stopped"
            self.production = self.inspection = None
            self.state, self.outcome, self.fault = "Idle", "aborted", None
            result = "Batch aborted. Partial counts retained."
        record["phase"], record["result"] = "completed", result
        LOG.info("completion cmd_id=%s command=%s result=%s", cmd_id, name, result)
        return ack, 202

    def advance(self, dt_ms):
        if self.state not in ("Running", "Paused"):
            return
        self.elapsed_ms += dt_ms
        if self.production:
            self.production["remaining_ms"] -= dt_ms
            if self.production["remaining_ms"] <= 0:
                part_id = self.production["part_id"]
                self.parts[part_id - 1]["status"] = "queued"
                self.queue.append(part_id)
                self.produced += 1
                self.production = None
        if self.inspection:
            self.inspection["remaining_ms"] -= dt_ms
            if self.inspection["remaining_ms"] <= 0:
                part_id = self.inspection["part_id"]
                # TEST ONLY. In the real project ESP32 B must calculate this verdict.
                failed = (part_id + self.settings["K"]) % self.settings["N"] == 0
                self.parts[part_id - 1]["status"] = "fail" if failed else "pass"
                self.failed += int(failed)
                self.passed += int(not failed)
                self.inspection = None
        if self.state == "Running":
            if self.inspection is None and self.queue:
                part_id = self.queue.popleft()
                self.parts[part_id - 1]["status"] = "inspecting"
                self.inspection = {"part_id": part_id, "remaining_ms": self.settings["inspection_time_ms"]}
            # Reserve one queue slot for the single in-flight production job.
            if self.production is None and len(self.queue) < self.capacity:
                waiting = next((p for p in self.parts if p["status"] == "waiting"), None)
                if waiting:
                    waiting["status"] = "producing"
                    self.production = {"part_id": waiting["part_id"], "remaining_ms": self.settings["production_time_ms"]}
        if self.passed + self.failed == len(self.parts):
            self.state, self.outcome = "Idle", "completed"

    def snapshot(self):
        self.seq += 1
        def station(connected, job):
            return {"connected": connected, "busy": job is not None,
                    "part_id": job["part_id"] if job else None,
                    "remaining_ms": max(0, round(job["remaining_ms"])) if job else None}
        return {"schema_version": 1, "type": "status", "simulation": True, "gateway_id": self.gateway_id,
                "status_seq": self.seq, "state": self.state, "fault": self.fault,
                "settings": copy.deepcopy(self.settings),
                "batch": {"id": self.batch_id, "target": len(self.parts), "outcome": self.outcome, "elapsed_ms": round(self.elapsed_ms)},
                "counts": {"produced": self.produced, "inspected": self.passed + self.failed, "passed": self.passed, "failed": self.failed},
                "queue": {"size": len(self.queue), "capacity": self.capacity, "part_ids": list(self.queue)},
                "stations": {"production": station(self.connected_a, self.production), "inspection": station(self.connected_b, self.inspection)},
                "parts": copy.deepcopy(self.parts), "command_results": [self.result(id) for id in list(self.records)[-100:]]}


async def broadcast(app):
    if app["factory"].silent:
        return
    data = json.dumps(app["factory"].snapshot())
    clients = list(app["clients"])
    if clients:
        await asyncio.gather(*(ws.send_str(data) for ws in clients if not ws.closed), return_exceptions=True)


@web.middleware
async def cors(request, handler):
    allowed = request.app["allowed_origin"]
    origin = request.headers.get("Origin")
    same = f"{request.scheme}://{request.host}"
    if origin and origin not in (same, allowed):
        return web.json_response({"error": "Origin not allowed. Use same-origin UI hosting or --allow-origin."}, status=403)
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)
    if origin == allowed and not isinstance(response, web.WebSocketResponse):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


async def get_status(request):
    return web.json_response(request.app["factory"].snapshot(), headers={"Cache-Control": "no-store"})


async def post_command(request):
    factory = request.app["factory"]
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        LOG.info("delivery cmd_id=%s command=%s", body.get("cmd_id"), request.match_info["name"])
        ack, code = factory.command(request.match_info["name"], body)
    except (ValueError, json.JSONDecodeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    await broadcast(request.app)
    return web.json_response(ack, status=code, headers={"Cache-Control": "no-store"})


async def get_command(request):
    factory = request.app["factory"]
    cmd_id = request.match_info["cmd_id"]
    if cmd_id not in factory.records:
        return web.json_response({"error": "Unknown command in this gateway boot", "gateway_id": factory.gateway_id}, status=404)
    return web.json_response(factory.result(cmd_id), headers={"Cache-Control": "no-store"})


async def websocket(request):
    ws = web.WebSocketResponse(heartbeat=2, max_msg_size=1024)
    await ws.prepare(request)
    request.app["clients"].add(ws)
    try:
        if not request.app["factory"].silent:
            await ws.send_json(request.app["factory"].snapshot())
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await ws.close(code=1008, message=b"Status socket is receive-only; commands use HTTP")
    finally:
        request.app["clients"].discard(ws)
    return ws


async def scenario(request):
    # Accessible only when explicitly enabled for local testing.
    factory = request.app["factory"]
    try:
        action = (await request.json())["action"]
    except (ValueError, KeyError, TypeError):
        return web.json_response({"error": "Expected action"}, status=400)
    if action in ("disconnect_a", "disconnect_b"):
        if action == "disconnect_a": factory.connected_a = False
        else: factory.connected_b = False
        factory.state, factory.fault = "Fault", f"Station {action[-1].upper()} disconnected (test). Stop the active batch before recovery."
    elif action == "restore_devices":
        factory.connected_a = factory.connected_b = True
        if factory.outcome != "active": factory.state, factory.fault = "Idle", None
    elif action == "silence": factory.silent = True
    elif action == "resume_updates": factory.silent = False
    elif action == "reject_next": factory.reject_next = True
    elif action == "restart":
        factory.reset()
        for ws in list(request.app["clients"]): await ws.close(code=1012, message=b"Controlled restart")
    else:
        return web.json_response({"error": "Unknown test scenario"}, status=400)
    await broadcast(request.app)
    return web.json_response({"ok": True, "action": action})


async def serve_asset(request):
    name = request.match_info.get("name", "index.html")
    # Serve only UI assets, never logs, Python code, dependencies or project files.
    assets = {"index.html", "cartoon.css", "toys.css", "motion.css", "integration.css", "toys.js", "motion.js", "app.js", "protocol.js", "transport.js"}
    if name not in assets:
        raise web.HTTPNotFound()
    return web.FileResponse(ROOT / name, headers={"Cache-Control": "no-store"})


async def lifecycle(app):
    async def run():
        last, previous_broadcast = time.monotonic(), 0
        while True:
            now = time.monotonic()
            app["factory"].advance((now - last) * 1000)
            last = now
            if now - previous_broadcast >= 0.2:
                await broadcast(app)
                previous_broadcast = now
            await asyncio.sleep(0.02)
    task = asyncio.create_task(run())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError): await task
    for ws in list(app["clients"]): await ws.close(code=1001)


def create_app(allow_origin=None, test_controls=False):
    app = web.Application(middlewares=[cors], client_max_size=8192)
    app["factory"], app["clients"], app["allowed_origin"] = Factory(), set(), allow_origin
    app.router.add_get("/api/status", get_status)
    app.router.add_get("/api/commands/{cmd_id}", get_command)
    app.router.add_get("/ws/status", websocket)
    for name in ("start", "pause", "resume", "stop"):
        app.router.add_post("/api/{name:" + name + "}", post_command)
    if test_controls: app.router.add_post("/test/scenario", scenario)
    app.router.add_route("OPTIONS", "/{tail:.*}", lambda request: web.Response(status=204))
    app.router.add_get("/", serve_asset)
    app.router.add_get("/{name}", serve_asset)
    app.cleanup_ctx.append(lifecycle)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--allow-origin", help="Exact additional UI origin, e.g. http://127.0.0.1:8765")
    parser.add_argument("--test-controls", action="store_true")
    parser.add_argument("--log", help="Optional log output path")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", filename=args.log)
    print("TEST GATEWAY: stations and verdicts are simulated. Open http://" + args.host + ":" + str(args.port))
    web.run_app(create_app(args.allow_origin, args.test_controls), host=args.host, port=args.port)
