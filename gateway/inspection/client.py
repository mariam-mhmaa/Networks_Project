"""Public gateway-side B adapter; no verdict calculation and no hidden retries."""
import asyncio
from dataclasses import dataclass
from .controller import Controller
from .wire import ID, Ids, Link, ProtocolError, uint


@dataclass(frozen=True)
class Settings:
    inspection_time_ms: int
    N: int
    K: int

    def __post_init__(self):
        if not (uint(self.inspection_time_ms, 600000, 1) and uint(self.N, 2147483647, 1)
                and type(self.K) is int and -2147483648 <= self.K <= 2147483647):
            raise ValueError("settings outside documented ranges")

    def fields(self):
        return {"inspection_time_ms": self.inspection_time_ms, "N": self.N, "K": self.K}


class BClient:
    def __init__(self, host, port=5001, *, ids=None, policy=None, log=None):
        self.ids = ids or Ids()
        self.link = Link(host, port, log=log)
        self.controller = Controller(self.link, self.ids, policy)
        self.batch_id = None
        self.run_no = None
        self.settings = None
        self.config_version = None

    async def connect(self):
        # B retains one controller until it observes the previous connection's
        # FIN. Bound discovery retries here, before submitting any operation;
        # the transport adapter itself never starts a retry loop.
        for attempt in range(3):
            try:
                await asyncio.wait_for(self.link.connect(), 1.0)
                return dict(self.link.heartbeat)
            except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
                if attempt == 2:
                    raise
                await asyncio.sleep(.03)

    def request(self, action, *, identifier=None, **fields):
        if not self.link.boot_id or not self.batch_id or self.run_no is None:
            raise ProtocolError("connect and select an explicit run context first")
        prefix = {"CONFIGURE": "CFG", "INSPECT": "INSP", "QUERY": "QUERY", "CLOSE": "CLOSE", "RETIRE": "RETIRE"}[action]
        key = "job_id" if action == "INSPECT" else "cmd_id"
        identifier = identifier or self.ids.new(prefix)
        if not ID.fullmatch(identifier):
            raise ValueError("invalid operation ID")
        return {"v": 1, "type": action, key: identifier, "boot_id": self.link.boot_id,
                "batch_id": self.batch_id, "run_no": self.run_no, **fields}

    def select_run(self, batch_id, run_no):
        if not ID.fullmatch(batch_id) or not uint(run_no, minimum=1):
            raise ValueError("invalid batch/run identity")
        if (batch_id, run_no) != (self.batch_id, self.run_no):
            self.controller.finished.clear()
            self.link.terminal_conflict = None
        self.batch_id, self.run_no = batch_id, run_no

    async def configure(self, settings):
        request = self.request("CONFIGURE", **settings.fields())
        outcome = await self.controller.run(request)
        if outcome.state == "COMPLETED":
            self.settings = settings
            self.config_version = outcome.result["config_version"]
        return outcome

    def inspection(self, part_id, identifier=None):
        if self.settings is None or self.config_version is None:
            raise ProtocolError("B configuration has not completed")
        if not uint(part_id, minimum=1):
            raise ValueError("part_id must be a positive uint32")
        return self.request("INSPECT", identifier=identifier, part_id=part_id,
                            config_version=self.config_version)

    async def inspect(self, part_id, *, identifier=None):
        request = self.inspection(part_id, identifier)
        return await self.controller.run(request, duration_ms=self.settings.inspection_time_ms,
                                         expected_settings=self.settings.fields())

    async def query(self, target_id):
        if not ID.fullmatch(target_id):
            raise ValueError("invalid target ID")
        request = self.request("QUERY", target_id=target_id, query_no=self.link.next_query_no())
        return await self.controller.run(request)

    async def retire(self, target_id, part_id):
        if not ID.fullmatch(target_id) or not uint(part_id, minimum=1):
            raise ValueError("invalid retirement identity")
        return await self.controller.run(self.request("RETIRE", target_id=target_id, part_id=part_id))

    async def close_run(self):
        return await self.controller.run(self.request("CLOSE"))

    async def close(self):
        await self.link.close()
