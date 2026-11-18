"""Serial worker lifecycle and stale/restart evidence; no physical port opened."""
import asyncio
import json
from pathlib import Path
import queue
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from gateway.production.serial_link import SerialLink
from gateway.production.framing import encode_atr,slip_encode
from gateway.inspection.wire import Restarted

def heartbeat(number=1,boot="a"*32):
    message={"v":1,"type":"HEARTBEAT","boot_id":boot,"run_no":0,"batch_id":"", "run_open":False,
             "state":"IDLE","config_version":0,"query_high_water":0,"heartbeat_no":number,"station":"A"}
    return slip_encode(encode_atr(0,0,json.dumps(message).encode()))

class Port:
    def __init__(self): self.incoming=queue.Queue(); self.closed=False; self.incoming.put(heartbeat())
    def read(self,size):
        try: return self.incoming.get(timeout=.02)
        except queue.Empty: return b""
    def write(self,data): return len(data)
    def close(self): self.closed=True

class SerialLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_heartbeat_does_not_refresh_liveness(self):
        port=Port(); link=SerialLink("injected",opener=lambda name:port,heartbeat_age=.12)
        try:
            await link.connect(); first=link.last_heartbeat
            port.incoming.put(heartbeat()); await asyncio.sleep(.05)
            self.assertEqual(link.last_heartbeat,first)
            await asyncio.sleep(.1); self.assertFalse(link.fresh)
            port.incoming.put(heartbeat(2)); await asyncio.sleep(.04)
            self.assertTrue(link.fresh)
        finally: await link.close()
        self.assertTrue(port.closed)

    async def test_new_boot_latches_restart_without_automatic_binding(self):
        port=Port(); link=SerialLink("injected",opener=lambda name:port)
        try:
            await link.connect(); port.incoming.put(heartbeat(2,"b"*32)); await asyncio.sleep(.05)
            self.assertIsInstance(link.failure,Restarted)
            self.assertEqual(link.boot_id,"a"*32)
            with self.assertRaises(Restarted): await link.connect()
        finally: await link.close()

    async def test_worker_io_failure_reports_disconnect_and_closes_port(self):
        port=Port()
        def fail(size): raise OSError("injected removal")
        link=SerialLink("injected",opener=lambda name:port)
        try:
            await link.connect(); events=asyncio.Queue(maxsize=2); link.route("original",events)
            port.read=fail
            event=await asyncio.wait_for(events.get(),1)
            self.assertEqual(event["_event"],"disconnected")
            self.assertFalse(link.fresh)
        finally: await link.close()
        self.assertTrue(port.closed)
