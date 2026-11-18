"""Capture drain/append and visible failure; no hardware access."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from gateway.operator.evidence import EventLog


class EvidenceTests(unittest.TestCase):
    def test_append_sessions_drain_records_without_replacing_prior_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"events.local.jsonl"
            for number in range(2):
                capture=EventLog(path)
                capture.emit("A","serial_rx",{"hex":"c000c0","number":number})
                capture.close()
                self.assertIsNone(capture.error)
                self.assertEqual(capture.dropped,0)
            records=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(records),6)
            self.assertEqual(len({r["session"] for r in records}),2)

    def test_writer_failure_is_visible_in_status(self):
        with tempfile.TemporaryDirectory() as directory:
            capture=EventLog(Path(directory)/"events.local.jsonl")
            try:
                capture.emit("A","invalid_evidence",{"number":float("nan")})
                end=time.monotonic()+2
                while not capture.error and time.monotonic()<end:time.sleep(.01)
                self.assertIn("Evidence write failed",capture.status()["error"])
            finally: capture.close()
