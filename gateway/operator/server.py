"""Same-origin FastAPI UI/HTTP/WS gateway. One process owns the station core."""
from contextlib import asynccontextmanager
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from .service import AdmissionError

ASSETS = Path(__file__).resolve().parents[2] / "operator_ui"
PUBLIC_ASSETS = {"index.html", "app.js", "protocol.js", "transport.js", "cartoon.css", "toys.css", "toys.js", "motion.css", "motion.js", "integration.css"}


def pairs(items):
    obj = {}
    for key, value in items:
        if key in obj: raise ValueError("Duplicate JSON field")
        obj[key] = value
    return obj


def create_app(service):
    @asynccontextmanager
    async def lifespan(app):
        await service.start()
        try: yield
        finally: await service.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.state.operator = service

    def same_origin(origin, host):
        if not origin: return True  # Nonbrowser test/client with an explicit command identity.
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc == host

    @app.get("/api/status")
    async def status():
        return JSONResponse(service.snapshot(), headers={"Cache-Control": "no-store"})

    @app.get("/api/commands/{identifier}")
    async def lookup(identifier: str):
        value = service.lookup(identifier)
        return JSONResponse(value or {"gateway_id": service.gateway_id, "error": "Unknown command"},
                            status_code=200 if value else 404, headers={"Cache-Control": "no-store"})

    @app.get("/api/history")
    async def history(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
        return JSONResponse(await service.history.page(offset, limit), headers={"Cache-Control": "no-store"})

    @app.get("/api/history/{identifier}")
    async def report(identifier: str, download: bool = False):
        value = await service.history.report(identifier)
        headers = {"Cache-Control": "no-store"}
        if value and download:
            number = service.history.numbers[identifier]
            headers["Content-Disposition"] = f'attachment; filename="batch-{number}.json"'
            return Response(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n",
                            media_type="application/json", headers=headers)
        return JSONResponse(value or {"error": "Unknown batch"}, status_code=200 if value else 404, headers=headers)

    @app.post("/api/{action}")
    async def command(action: str, request: Request):
        if not same_origin(request.headers.get("origin"), request.headers.get("host")):
            return JSONResponse({"error": "Use the same-origin operator screen"}, status_code=403)
        try:
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                raise AdmissionError("Expected application/json", 415)
            data = bytearray()
            async for piece in request.stream():
                data.extend(piece)
                if len(data) > 4096: raise AdmissionError("Command exceeds 4096 bytes", 413)
            body = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-JSON number")))
            code, ack = await service.submit(action, body)
            return JSONResponse(ack, status_code=code, headers={"Cache-Control": "no-store"})
        except AdmissionError as exc:
            return JSONResponse({"gateway_id": service.gateway_id, "error": str(exc)}, status_code=exc.status)
        except (ValueError, UnicodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.websocket("/ws/status")
    async def websocket(socket: WebSocket):
        if not same_origin(socket.headers.get("origin"), socket.headers.get("host")):
            await socket.close(code=1008); return
        await socket.accept()
        async def receive_alive():
            while True:
                data = await socket.receive_text()
                if len(data.encode("utf-8")) > 1024: raise ValueError("Liveness message too large")
                value = json.loads(data, object_pairs_hook=pairs)
                if not isinstance(value, dict) or set(value) != {"type", "operator_id", "gateway_id", "status_seq"} or value["type"] != "alive":
                    raise ValueError("WebSocket receives only liveness acknowledgements; controls use HTTP")
                service.alive(value["operator_id"], value["gateway_id"], value["status_seq"])
        receiver = asyncio.create_task(receive_alive())
        try:
            while not receiver.done():
                await asyncio.wait_for(socket.send_json(service.snapshot()), 2)
                await asyncio.sleep(.2)
            await receiver
        except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError, ValueError, AdmissionError):
            pass
        finally:
            receiver.cancel(); await asyncio.gather(receiver, return_exceptions=True)

    @app.get("/")
    async def index():
        return FileResponse(ASSETS / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/{asset}")
    async def asset(asset: str):
        if asset not in PUBLIC_ASSETS: return JSONResponse({"error": "Not found"}, status_code=404)
        return FileResponse(ASSETS / asset, headers={"Cache-Control": "no-store"})

    return app
