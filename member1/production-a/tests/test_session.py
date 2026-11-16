import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pc_test"))
from session import SessionGuard,SessionFault
from receiver import Receiver
from protocol import encode_atr,slip_encode
import json

def status(kind="HEARTBEAT",boot="a"*32,n=1):
    return dict(type=kind,boot_id=boot,state="IDLE",active_op_no=None,high_water=2,
                production_time_ms=1000,heartbeat_no=n)

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now=0
        self.guard=SessionGuard(lambda:self.now)
        self.guard.bind(status("STATUS",n=0))
        self.guard.observe(status())

    def test_exact_deadline_and_same_session_recovery_latches_fault(self):
        self.now=4.999; self.assertTrue(self.guard.check())
        self.now=5.0; self.assertFalse(self.guard.check())
        self.assertEqual(self.guard.fault,"HEARTBEAT_TIMEOUT")
        self.guard.observe(status(n=2)); self.assertTrue(self.guard.available)
        with self.assertRaises(SessionFault): self.guard.require_send()

    def test_invalid_old_or_status_frames_do_not_refresh_deadline(self):
        self.now=4
        self.guard.observe(status("STATUS",n=2),123)
        self.guard.observe(status(n=1)) # replayed heartbeat
        self.guard.observe(status(n=2),7) # wrong unsolicited sequence
        self.guard.observe(dict(status(n=2),high_water=True))
        self.now=5; self.assertFalse(self.guard.check())

    def test_restart_is_sticky_and_never_arms_new_boot(self):
        self.guard.observe(status(boot="b"*32,n=1))
        self.assertEqual(self.guard.fault,"RESTART")
        self.guard.observe(status(n=2)); self.assertFalse(self.guard.available)
        with self.assertRaises(SessionFault): self.guard.bind(status("STATUS",boot="b"*32))

    def test_receiver_separates_heartbeats_from_correlated_response(self):
        data=slip_encode(encode_atr(0,0,json.dumps(status(boot="invalid",n=2)).encode()))
        data+=slip_encode(encode_atr(0,0,json.dumps(status(n=2)).encode()))
        data+=slip_encode(encode_atr(0,999,json.dumps(status("STATUS",n=2)).encode()))
        data+=slip_encode(encode_atr(0,123,json.dumps(dict(type="ACCEPTED",boot_id="a"*32)).encode()))
        class Port:
            def read(self,count):
                nonlocal data
                chunk,data=data[:min(count,3)],data[min(count,3):]
                return chunk
        report={}; receiver=Receiver(Port(),report,self.guard)
        item=receiver.next(1)
        self.assertEqual(item["seq"],123)
        self.assertEqual(item["event"]["type"],"ACCEPTED")
        self.assertEqual(len(report["status_events"]),2)
        self.assertEqual(receiver.rejections,1)
