"""Ensure invalid-input probes are not repaired by the regression client."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pc_test"))
from production_test import Client
from protocol import SlipDecoder, decode_atr


class Port:
    def __init__(self): self.wire=bytearray()
    def write(self,data): self.wire.extend(data); return len(data)


class HistoryClientTests(unittest.TestCase):
    def client(self,port,**options):
        client=Client(port,{"tx":[]},**options)
        event=dict(type="HEARTBEAT",boot_id="a"*32,state="IDLE",active_op_no=None,high_water=0,production_time_ms=500,heartbeat_no=1)
        client.receiver.guard.bind(event); client.receiver.guard.observe(event)
        return client
    def payloads(self,port):
        return [json.loads(decode_atr(frame)[2]) for frame in SlipDecoder().feed(port.wire)]

    def test_explicit_mode_keeps_missing_number(self):
        port=Port(); client=self.client(port,assign_operations=False)
        request=dict(type="CONFIGURE_PRODUCTION",cmd_id="cfg:1",production_time_ms=500)
        client.send(request)
        self.assertEqual(self.payloads(port),[dict(request,boot_id="a"*32)])
        self.assertNotIn("op_no",request)

    def test_legacy_regression_adds_number_and_suffix(self):
        port=Port(); client=self.client(port)
        client.send(dict(type="CONFIGURE_PRODUCTION",cmd_id="cfg",production_time_ms=500))
        self.assertEqual(self.payloads(port)[0]["op_no"],1)
        self.assertEqual(self.payloads(port)[0]["cmd_id"],"cfg:1")

    def test_explicit_duplicate_identity_preserved(self):
        port=Port(); client=self.client(port,assign_operations=False)
        request=dict(type="PRODUCE_PART",op_no=7,job_id="job:7",batch_id="batch",part_id=1)
        first=client.send(request); second=client.send(request)
        self.assertNotEqual(first,second)
        self.assertEqual(self.payloads(port),[dict(request,boot_id="a"*32)]*2)
