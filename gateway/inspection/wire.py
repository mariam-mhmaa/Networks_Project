"""Version 1 JSON/framing and the shared origin-side ID allocator."""
import asyncio
import json
import re
import struct
import uuid
from collections import defaultdict

MAX_PAYLOAD = 1024
ID = re.compile(r"[A-Za-z0-9_:-]{1,96}\Z")
BOOT = re.compile(r"[0-9a-f]{32}\Z")


class ProtocolError(Exception):
    pass


class Restarted(ProtocolError):
    pass


class Ids:
    def __init__(self):
        self.session = uuid.uuid4().hex
        self.counters = defaultdict(int)

    def new(self, action):
        self.counters[action] += 1
        return f"{action}-GW-{self.session}-{self.counters[action]:06d}"


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate JSON field")
        result[key] = value
    return result


def encode(message):
    body = json.dumps(message, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    if not 1 <= len(body) <= MAX_PAYLOAD:
        raise ProtocolError("payload outside 1..1024 bytes")
    return struct.pack(">I", len(body)) + body


async def receive(reader):
    size, = struct.unpack(">I", await reader.readexactly(4))
    if not 1 <= size <= MAX_PAYLOAD:
        raise ProtocolError("invalid length prefix")
    body = await reader.readexactly(size)
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               ProtocolError(f"non-JSON number {value}")))
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("malformed UTF-8 JSON") from exc
    if not isinstance(value, dict) or type(value.get("v")) is not int or value["v"] != 1:
        raise ProtocolError("invalid message envelope/version")
    if not isinstance(value.get("type"), str) or not BOOT.fullmatch(str(value.get("boot_id", ""))):
        raise ProtocolError("invalid response type/boot identity")
    return value


def uint(value, maximum=4294967295, minimum=0):
    return type(value) is int and minimum <= value <= maximum


class Link:
    """One reader and one write lock; reconnect is requested by the controller.

    A fresh heartbeat is the connection greeting, not a successful command.
    No retries, execution scheduling, or result accounting happen here.
    """
    def __init__(self, host, port=5001, *, log=None, heartbeat_age=1.5):
        self.host, self.port = host, port
        self.log = log or (lambda event, data: None)
        self.heartbeat_age = heartbeat_age
        self.boot_id = None
        self.heartbeat = None
        self.last_heartbeat = 0.0
        self.query_no = 0
        self.reader_task = None
        self.writer = None
        self.routes = {}
        self.lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self.ready = None
        self.failure = None
        self.terminal_conflict = None
        self.late_handler = lambda message: None

    @property
    def fresh(self):
        return self.writer is not None and not self.writer.is_closing() and (
            asyncio.get_running_loop().time() - self.last_heartbeat <= self.heartbeat_age)

    def route(self, identifier, queue):
        self.routes[identifier] = queue

    def unroute(self, identifier):
        self.routes.pop(identifier, None)

    def next_query_no(self):
        self.query_no += 1
        if self.query_no > 4294967295:
            raise ProtocolError("query sequence exhausted; explicit receiver restart required")
        return self.query_no

    async def connect(self):
        async with self.lock:
            if isinstance(self.failure, Restarted):
                raise self.failure
            if self.writer and not self.writer.is_closing() and self.fresh:
                return
            await self._close_transport()
            reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.ready = asyncio.get_running_loop().create_future()
            # A failed greeting is read below, so consume its exception exactly once.
            self.reader_task = asyncio.create_task(self._reader(reader, self.writer))
            try:
                await asyncio.wait_for(asyncio.shield(self.ready), 1.0)
            except BaseException:
                await self._close_transport()
                raise

    async def _reader(self, reader, writer):
        failure = None
        try:
            while True:
                message = await receive(reader)
                now = asyncio.get_running_loop().time()
                if self.boot_id and message["boot_id"] != self.boot_id:
                    raise Restarted("ESP32 B restarted; old operations cannot be replayed")
                if message["type"] == "HEARTBEAT":
                    if not (uint(message.get("run_no")) and uint(message.get("query_high_water"))
                            and uint(message.get("config_version"))
                            and type(message.get("run_open")) is bool
                            and message.get("state") in {"IDLE", "BUSY"}
                            and isinstance(message.get("batch_id"), str)):
                        raise ProtocolError("malformed heartbeat")
                    self.boot_id = message["boot_id"]
                    self.heartbeat, self.last_heartbeat = message, now
                    self.query_no = max(self.query_no, message["query_high_water"])
                    if not self.ready.done():
                        self.ready.set_result(message)
                    self.log("heartbeat", message)
                    continue
                if not self.ready.done():
                    # History outbox may precede the fresh connection greeting.
                    continue
                self.log("receive", message)
                identifier = message.get("job_id", message.get("cmd_id"))
                queue = self.routes.get(identifier)
                if queue:
                    try:
                        queue.put_nowait(message)
                    except asyncio.QueueFull:
                        raise ProtocolError("bounded gateway event queue exhausted") from None
                else:
                    self.late_handler(message)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            failure = exc
            self.failure = exc
            if not self.ready.done():
                self.ready.set_exception(exc)
        finally:
            writer.close()
            if failure:
                for queue in set(self.routes.values()):
                    if not queue.full():
                        queue.put_nowait({"_event": "disconnected", "error": failure})

    async def send(self, message, payload):
        await self.connect()
        if message["boot_id"] != self.boot_id:
            raise Restarted("immutable request addressed to another receiver boot")
        async with self.write_lock:
            self.writer.write(payload)
            await self.writer.drain()
        self.log("send", message)

    async def _close_transport(self):
        task, self.reader_task = self.reader_task, None
        if self.writer:
            # Graceful stream close can wait for an unreachable peer's send
            # buffer. Abort is immediate; operation recovery retains identity.
            self.writer.transport.abort()
            self.writer = None
        if task and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.ready and self.ready.done() and not self.ready.cancelled():
            self.ready.exception()

    async def close(self):
        async with self.lock:
            await self._close_transport()
