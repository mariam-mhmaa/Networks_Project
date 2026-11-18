"""Session/heartbeat policy. No serial writes, retries or work continuation."""
import re
import time


class SessionFault(RuntimeError):
    pass


def valid_status(event):
    if not isinstance(event,dict) or not isinstance(event.get("boot_id"),str): return False
    if not re.fullmatch(r"[0-9a-f]{32}",event["boot_id"]): return False
    if event.get("state") not in ("UNCONFIGURED","IDLE","PRODUCING"): return False
    for key,limit in (("high_water",0xFFFFFFFF),("production_time_ms",60000),("heartbeat_no",0xFFFFFFFF)):
        if type(event.get(key)) is not int or not 0<=event[key]<=limit: return False
    active=event.get("active_op_no")
    return ((event["state"]=="PRODUCING" and type(active) is int and 1<=active<=event["high_water"])
            or (event["state"]!="PRODUCING" and active is None))


class SessionGuard:
    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self.boot_id=None
        self.last_heartbeat=None
        self.bound_at=None
        self.available=False
        self.fault=None
        self.observed_boot_id=None
        self.last_heartbeat_no=-1

    def bind(self,event):
        if not valid_status(event): raise ValueError("invalid discovery status")
        if self.boot_id is not None: raise SessionFault("explicit new guard required to recover")
        self.boot_id=event["boot_id"]; self.observed_boot_id=self.boot_id
        self.bound_at=self.clock()
        self.last_heartbeat_no=event["heartbeat_no"] if event.get("type")=="STATUS" else -1

    def observe(self,event,seq=0):
        if not valid_status(event): return False
        if event.get("type") not in ("HEARTBEAT","STATUS"): return False
        if event["type"]=="HEARTBEAT" and seq!=0: return False
        self.observed_boot_id=event["boot_id"]
        if self.boot_id is not None and event["boot_id"]!=self.boot_id:
            self.fault="RESTART"; self.available=False; return False
        if self.fault=="RESTART": return False
        if event["type"]=="HEARTBEAT" and self.boot_id is not None:
            if event["heartbeat_no"]<=self.last_heartbeat_no: return False
            self.check()
            self.last_heartbeat=self.clock(); self.available=True
            self.last_heartbeat_no=event["heartbeat_no"]
            return True
        return False

    def check(self):
        since=self.last_heartbeat if self.last_heartbeat is not None else self.bound_at
        if since is not None and self.clock()-since>=5.0:
            self.available=False
            if self.fault is None: self.fault="HEARTBEAT_TIMEOUT"
        return self.available

    def require_send(self):
        self.check()
        if self.boot_id is None or not self.available or self.fault:
            raise SessionFault(f"station unavailable or explicit recovery required: {self.fault}")
