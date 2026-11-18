"""One serial worker owns open/read/write/close; asyncio owns all operation logic.

The bounded outgoing queue carries immutable JSON bytes. A fresh ATR attempt
sequence is added by the worker. There is no retry/deadline controller here.
"""
import asyncio
import queue
import threading
from gateway.inspection.wire import Link, ProtocolError, Restarted, decode, uint
from .framing import SlipDecoder, decode_atr, encode_atr, slip_encode

class SerialLink(Link):
    def __init__(self, port, *, log=None, heartbeat_age=5.0, opener=None):
        super().__init__(port, log=log, heartbeat_age=heartbeat_age)
        self.opener=opener
        self.thread=None
        self.stop=None
        self.outgoing=None
        self.incoming=None
        self.sequence=0
        self.last_heartbeat_no=-1
        self.overflow=False

    @property
    def fresh(self):
        return bool(self.thread and self.thread.is_alive() and self.ready and self.ready.done()
                    and not self.failure and asyncio.get_running_loop().time()-self.last_heartbeat < self.heartbeat_age)

    def _deliver(self, item):
        if self.incoming.full():
            self.overflow=True
            self.stop.set()
        else: self.incoming.put_nowait(item)

    def _worker(self, loop, outgoing, stop):
        serial=None
        try:
            if self.opener: serial=self.opener(self.host)
            else:
                import serial as pyserial
                # Set control lines before opening to avoid an intentional reset.
                serial=pyserial.serial_for_url(self.host, baudrate=115200, timeout=.02, write_timeout=.25, do_not_open=True)
                serial.dtr=False; serial.rts=False; serial.open()
            decoder=SlipDecoder()
            while not stop.is_set():
                try: payload=outgoing.get_nowait()
                except queue.Empty: payload=None
                if payload is not None:
                    self.sequence+=1
                    if self.sequence>4294967295: raise ProtocolError("ATR attempt sequence exhausted")
                    frame=slip_encode(encode_atr(0,self.sequence,payload))
                    if serial.write(frame)!=len(frame): raise OSError("partial serial frame write")
                for frame in decoder.feed(serial.read(4096)):
                    try: test_id,seq,body=decode_atr(frame)
                    except ValueError: continue
                    if test_id: continue
                    message=decode(body)
                    if (message["type"]=="HEARTBEAT") != (seq==0):
                        raise ProtocolError("invalid heartbeat/application ATR sequence")
                    message["_atr_seq"]=seq
                    loop.call_soon_threadsafe(self._deliver,message)
        except Exception as exc:
            loop.call_soon_threadsafe(self._deliver,exc)
        finally:
            if serial: serial.close()

    async def connect(self):
        async with self.lock:
            if isinstance(self.failure,Restarted): raise self.failure
            if self.fresh: return
            await self._close_transport()
            self.failure=None; self.overflow=False
            self.outgoing=queue.Queue(maxsize=4); self.incoming=asyncio.Queue(maxsize=128)
            self.stop=threading.Event(); self.ready=asyncio.get_running_loop().create_future()
            self.thread=threading.Thread(target=self._worker,args=(asyncio.get_running_loop(),self.outgoing,self.stop),daemon=True)
            self.thread.start()
            self.reader_task=asyncio.create_task(self._reader_serial())
            try: await asyncio.wait_for(asyncio.shield(self.ready),2.5)
            except BaseException:
                await self._close_transport()
                raise

    async def _reader_serial(self):
        try:
            while True:
                try: message=await asyncio.wait_for(self.incoming.get(),.1)
                except asyncio.TimeoutError:
                    if self.overflow: raise ProtocolError("serial event queue exhausted")
                    if not self.thread.is_alive(): raise OSError("serial worker stopped")
                    continue
                if isinstance(message,Exception): raise message
                if self.boot_id and message["boot_id"]!=self.boot_id:
                    raise Restarted("ESP32 A restarted; old operations cannot be replayed")
                if message["type"]=="HEARTBEAT":
                    if not (uint(message.get("heartbeat_no"),2**53-1,1) and
                            uint(message.get("run_no")) and uint(message.get("query_high_water")) and
                            uint(message.get("config_version")) and type(message.get("run_open")) is bool and
                            message.get("state") in {"IDLE","BUSY"} and message.get("station")=="A" and
                            isinstance(message.get("batch_id"),str)):
                        raise ProtocolError("invalid A heartbeat")
                    if message["heartbeat_no"]<=self.last_heartbeat_no: continue
                    self.last_heartbeat_no=message["heartbeat_no"]
                    self.boot_id=message["boot_id"]; self.heartbeat=message
                    self.last_heartbeat=asyncio.get_running_loop().time()
                    self.query_no=max(self.query_no,message["query_high_water"])
                    if not self.ready.done(): self.ready.set_result(message)
                    self.log("heartbeat",message)
                    continue
                if not self.ready.done(): continue
                self.log("receive",message)
                target=self.routes.get(message.get("job_id",message.get("cmd_id")))
                if target: target.put_nowait(message)
                else: self.late_handler(message)
        except asyncio.CancelledError: return
        except Exception as exc:
            self.failure=exc; self.stop.set()
            if not self.ready.done(): self.ready.set_exception(exc)
            for target in set(self.routes.values()):
                if not target.full(): target.put_nowait({"_event":"disconnected","error":exc})

    async def send(self,message,payload):
        await self.connect()
        if message["boot_id"]!=self.boot_id: raise Restarted("request addressed to another A boot")
        try: self.outgoing.put_nowait(bytes(payload[4:]))
        except queue.Full: raise ProtocolError("serial outgoing queue full") from None
        self.log("send",message)

    async def _close_transport(self):
        if self.stop: self.stop.set()
        if self.thread:
            await asyncio.to_thread(self.thread.join,1.0)
            if self.thread.is_alive(): raise ProtocolError("serial worker failed to close")
            self.thread=None
        if self.reader_task:
            self.reader_task.cancel(); await asyncio.gather(self.reader_task,return_exceptions=True)
            self.reader_task=None
        if self.ready and self.ready.done() and not self.ready.cancelled(): self.ready.exception()
