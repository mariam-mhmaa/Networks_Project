"""A uses the same operation owner as B, with USB serial and production results."""
from dataclasses import dataclass
from gateway.inspection.client import BClient
from gateway.inspection.wire import ID, uint, ProtocolError
from .controller import ProductionController
from .serial_link import SerialLink

@dataclass(frozen=True)
class ProductionSettings:
    production_time_ms: int
    def __post_init__(self):
        if not uint(self.production_time_ms, 600000, 1):
            raise ValueError("production_time_ms outside 1..600000")
    def fields(self): return {"production_time_ms": self.production_time_ms}

class AClient(BClient):
    def __init__(self, port, *, ids=None, policy=None, log=None, heartbeat_age=5.0, opener=None):
        super().__init__("unused", ids=ids, policy=policy, log=log)
        self.link=SerialLink(port, log=log, heartbeat_age=heartbeat_age, opener=opener)
        self.controller=ProductionController(self.link, self.ids, policy)

    async def connect(self):
        await self.link.connect()
        return dict(self.link.heartbeat)

    def request(self, action, *, identifier=None, **fields):
        if action != "PRODUCE":
            return super().request(action, identifier=identifier, **fields)
        if not self.link.boot_id or not self.batch_id or self.run_no is None:
            raise ProtocolError("connect/select a run before production")
        identifier=identifier or self.ids.new("PROD")
        if not ID.fullmatch(identifier): raise ValueError("invalid production ID")
        return {"v":1,"type":action,"job_id":identifier,"boot_id":self.link.boot_id,
                "batch_id":self.batch_id,"run_no":self.run_no,**fields}

    def production(self, part_id, identifier=None):
        if self.settings is None or self.config_version is None:
            raise ProtocolError("A configuration has not completed")
        if not uint(part_id, minimum=1): raise ValueError("part_id must be positive uint32")
        return self.request("PRODUCE", identifier=identifier, part_id=part_id, config_version=self.config_version)

    async def produce(self, part_id, *, identifier=None):
        return await self.controller.run(self.production(part_id, identifier),
            duration_ms=self.settings.production_time_ms, expected_settings=self.settings.fields())
