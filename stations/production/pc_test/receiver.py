"""One incremental SLIP/ATR receiver; unsolicited traffic has a separate route."""
import json
import time
from protocol import SlipDecoder, decode_atr
from session import SessionGuard, SessionFault, valid_status


class Receiver:
    def __init__(self,port,report,guard=None):
        self.port,self.report=port,report
        self.guard=guard or SessionGuard()
        self.decoder=SlipDecoder()
        self.pending=[]
        self.rejections=0
        self.expected_status=set()

    def pump(self,timeout):
        self.guard.check()
        self.port.timeout=min(0.02,max(0,timeout))
        chunk=self.port.read(17)
        if not chunk: return
        self.report.setdefault("rx_chunks_hex",[]).append(chunk.hex(" "))
        for raw in self.decoder.feed(chunk):
            try:
                tid,seq,payload=decode_atr(raw)
                event=None
                if tid==0:
                    event=json.loads(payload.decode("utf-8"))
                    if not isinstance(event,dict): raise ValueError("response must be JSON object")
            except (ValueError,UnicodeError):
                self.rejections+=1
                self.report["rx_rejections"]=self.rejections
                continue # Reset noise cannot establish a session; recover at END.
            item=dict(test_id=tid,seq=seq,event=event,payload=payload,
                      monotonic=time.monotonic(),atr_hex=raw.hex(" "))
            if tid==0 and event.get("type") in ("HEARTBEAT","STATUS"):
                if not valid_status(event) or (event["type"]=="HEARTBEAT" and seq!=0):
                    self.rejections+=1
                    self.report["rx_rejections"]=self.rejections
                    continue # Invalid observations cannot refresh liveness or halt recovery observation.
                self.guard.observe(event,seq)
                self.report.setdefault("status_events",[]).append({k:v for k,v in item.items() if k!="payload"})
                if event["type"]=="HEARTBEAT":
                    continue
                if seq not in self.expected_status: continue
                self.expected_status.discard(seq)
            self.pending.append(item)
        self.report["slip_rejections"]=self.decoder.rejected

    def next(self,timeout,strict_session=True):
        deadline=time.monotonic()+timeout
        while True:
            self.guard.check()
            if strict_session and self.guard.fault: raise SessionFault(self.guard.fault)
            if self.pending:
                item=self.pending.pop(0)
                if strict_session and item["test_id"]==0 and self.guard.boot_id:
                    if item["event"].get("boot_id")!=self.guard.boot_id:
                        self.guard.fault="RESTART"; self.guard.available=False
                        raise SessionFault("RESTART")
                return item
            remaining=deadline-time.monotonic()
            if remaining<=0: return None
            self.pump(remaining)
