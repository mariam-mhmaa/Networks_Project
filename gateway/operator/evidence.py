"""Bounded off-loop JSONL evidence writer; never owns operation decisions."""
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import sys
import threading
import time
import uuid


class EventLog:
    def __init__(self, path, *, capacity=4096):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a", encoding="utf-8", buffering=1)
        self.queue = queue.Queue(maxsize=capacity)
        self.stop = threading.Event()
        self.session = uuid.uuid4().hex
        self.error = None
        self.written = self.dropped = 0
        self.closed = False
        self.thread = threading.Thread(target=self._write, name="station-evidence", daemon=True)
        self.thread.start()
        self.emit("gateway", "capture_started", {"format":1})

    def logger(self, station):
        return lambda event, data: self.emit(station, event, data)

    def serial_logger(self):
        """Raw A transport only; application operations live in SQLite."""
        def log(event, data):
            if event in {"serial_tx", "serial_rx"}:
                self.emit("A", event, data)
        return log

    def emit(self, station, event, data):
        if self.closed or self.error:
            self.dropped += 1
            return
        record = {"utc":datetime.now(timezone.utc).isoformat(), "monotonic_ns":time.monotonic_ns(),
                  "session":self.session, "station":station, "event":event, "data":data}
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1
            self.error = "Evidence queue full; capture is incomplete"
            print(self.error, file=sys.stderr, flush=True)

    def _write(self):
        try:
            while not self.stop.is_set() or not self.queue.empty():
                try: record = self.queue.get(timeout=.1)
                except queue.Empty: continue
                self.stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
                self.written += 1
        except Exception as exc:
            self.error = "Evidence write failed: " + str(exc)
            print(self.error, file=sys.stderr, flush=True)
        finally:
            self.stream.close()

    def status(self):
        return {"path":str(self.path), "session":self.session, "written":self.written,
                "dropped":self.dropped, "error":self.error}

    def close(self):
        if self.closed: return
        self.emit("gateway", "capture_stopped", {})
        self.closed = True
        self.stop.set()
        self.thread.join(5)
        if self.thread.is_alive():
            self.error = "Evidence writer did not finish within five seconds"
            print(self.error, file=sys.stderr, flush=True)
