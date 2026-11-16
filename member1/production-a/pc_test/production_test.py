"""Step 4 production hardware checks; resets volatile station state on start."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import serial

from protocol import SlipDecoder, decode_atr, encode_atr, slip_encode
from two_way_test import drain_startup
from receiver import Receiver
from session import SessionFault

PLAN = ["unconfigured_rejection", "configuration_1000", "invalid_requests",
        "part_1000_and_busy", "configuration_2500", "part_2500"]


class Client:
    _seq_counter=0x20000000 # Process-wide allocation; no reuse on same-process reconnect.
    def __init__(self, port, report, assign_operations=True):
        self.port, self.report = port, report
        self.decoder = SlipDecoder()
        self.pending = []
        self.seq = Client._seq_counter
        self.op_no = 0
        self.assign_operations = assign_operations
        self.receiver=Receiver(port,report)

    def discover(self):
        seq=self.send(dict(type="GET_STATUS"),bind_session=False)
        item=self.receiver.next(3,strict_session=False)
        assert item and item["seq"]==seq and item["event"].get("type")=="STATUS", "discovery response missing"
        self.receiver.guard.bind(item["event"])
        deadline=time.monotonic()+2
        while not self.receiver.guard.available and time.monotonic()<deadline:
            self.receiver.pump(0.02)
        self.receiver.guard.require_send()
        return item["event"]

    def send(self, obj=None, raw=None, corrupt=False, bind_session=True, write_deadline=None):
        if obj is not None:
            obj = dict(obj)
            if bind_session:
                self.receiver.guard.require_send()
                obj.setdefault("boot_id",self.receiver.guard.boot_id)
            if self.assign_operations and "op_no" not in obj and obj.get("type")!="GET_STATUS":
                self.op_no += 1
                obj["op_no"] = self.op_no
                for key in ("cmd_id", "job_id"):
                    if isinstance(obj.get(key), str) and obj[key]:
                        obj[key] += ":" + str(self.op_no)
        if Client._seq_counter>=0xFFFFFFFF: raise ValueError("ATR sequence space exhausted; no wrap/reuse")
        Client._seq_counter+=1
        self.seq=Client._seq_counter
        if obj is not None and obj.get("type")=="GET_STATUS":
            self.receiver.expected_status.add(self.seq)
        payload = raw if raw is not None else json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        record = encode_atr(0, self.seq, payload)
        if corrupt:
            record = record[:-1] + bytes([record[-1] ^ 1])
        wire = slip_encode(record)
        entry = dict(seq=self.seq, payload_hex=payload.hex(" "), intended_tx_hex=wire.hex(" "), tx_hex="")
        self.report["tx"].append(entry)
        sent = 0
        deadline = time.monotonic() + 2
        if write_deadline is not None: deadline=min(deadline,write_deadline)
        while sent < len(wire):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("write timeout")
            self.port.write_timeout = min(0.5, remaining)
            sent += self.port.write(wire[sent:])
            entry["tx_hex"] = wire[:sent].hex(" ")
        return self.seq

    def next(self, timeout, strict_session=True):
        item=self.receiver.next(timeout,strict_session=strict_session)
        if item is not None:
            if item["test_id"]!=0: raise AssertionError("unexpected XOR response")
            item={k:v for k,v in item.items() if k!="payload"}
            self.report["events"].append(item)
        return item

    def expect(self, seq, types, ids, reason=None, timeout=2):
        events = []
        for kind in types:
            item = self.next(timeout)
            assert item is not None, f"missing {kind}, seq={seq}"
            assert (item["test_id"], item["seq"]) == (0, seq), item
            event = item["event"]
            assert event.get("type") == kind, (kind, item)
            for key, value in ids.items():
                if key in ("cmd_id", "job_id") and isinstance(value, str):
                    # Legacy Step 4 checks use labels; compare full sent IDs.
                    tx = next(t for t in reversed(self.report["tx"]) if t["seq"] == seq)
                    value = json.loads(bytes.fromhex(tx["payload_hex"]).decode())[key]
                assert type(event.get(key)) is type(value) and event[key] == value, item
            if kind == "REJECTED" and reason:
                assert event.get("reason") == reason, item
            events.append(item)
        return events

    def reject_config(self, value, index):
        ids = dict(cmd_id=f"invalid-{index}")
        seq = self.send(dict(type="CONFIGURE_PRODUCTION", **ids, production_time_ms=value))
        self.expect(seq, ["RECEIVED", "REJECTED"], ids, "INVALID_CONFIGURATION")

    def configure(self, ms):
        ids = dict(cmd_id=f"cfg-{ms}")
        seq = self.send(dict(type="CONFIGURE_PRODUCTION", **ids, production_time_ms=ms))
        events = self.expect(seq, ["RECEIVED", "ACCEPTED", "PRODUCTION_CONFIGURED"], ids)
        assert type(events[-1]["event"].get("production_time_ms")) is int
        assert events[-1]["event"]["production_time_ms"] == ms

    def job(self, ms, part):
        ids = dict(job_id=f"job-{part}", batch_id="step4-batch", part_id=part)
        seq = self.send(dict(type="PRODUCE_PART", **ids))
        accepted = self.expect(seq, ["RECEIVED", "ACCEPTED"], ids)[-1]
        if part == 1:
            other = dict(job_id="busy-other", batch_id="other-batch", part_id=99)
            busy_seq = self.send(dict(type="PRODUCE_PART", **other))
            self.expect(busy_seq, ["RECEIVED", "REJECTED"], other, "BUSY")
            config_ids = dict(cmd_id="busy-config")
            config_seq = self.send(dict(type="CONFIGURE_PRODUCTION", **config_ids, production_time_ms=2500))
            self.expect(config_seq, ["RECEIVED", "REJECTED"], config_ids, "BUSY")
            # Prove the original XOR path responds while the timer is active.
            payload = bytes.fromhex("00 c0 db ff")
            wire = slip_encode(encode_atr(7, 0xABCDEF01, payload))
            self.port.write(wire)
            expected = slip_encode(encode_atr(7, 0xABCDEF01, bytes(b ^ 0xA5 for b in payload)))
            response=self.receiver.next(0.4)
            received=slip_encode(bytes.fromhex(response["atr_hex"])) if response else b""
            self.report["xor_while_busy"] = dict(tx_hex=wire.hex(" "), rx_hex=received.hex(" "), passed=bytes(received)==expected)
            assert bytes(received) == expected, "XOR not responsive while busy"
        completed = self.expect(seq, ["PART_PRODUCED"], ids, timeout=ms/1000+1)[0]
        elapsed_ms = (completed["monotonic"]-accepted["monotonic"])*1000
        timing = dict(configured_ms=ms, elapsed_ms=elapsed_ms, lower_ms=ms-100,
                      upper_ms=ms+500, passed=ms-100 <= elapsed_ms <= ms+500)
        self.report["timings"].append(timing)
        assert timing["passed"], timing
        assert self.next(0.15) is None, "unexpected extra event/production"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--log", type=Path, default=Path("results/step4_production.json"))
    args = parser.parse_args()
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), port=args.port,
                  settings="115200 8N1, no flow control", reset_on_start=True,
                  tx=[], rx_chunks_hex=[], events=[], timings=[], checks=[], passed=False, not_run=PLAN.copy())
    port = None
    try:
        with serial.Serial(port=None, baudrate=115200, timeout=0.01, write_timeout=0.5,
                           xonxoff=False, rtscts=False, dsrdtr=False) as port:
            port.dtr = port.rts = False
            port.port = args.port
            port.open()
            # CP210x RTS controls EN on this verified board. Reset RAM state.
            port.rts = True
            time.sleep(0.1)
            port.rts = False
            startup, quiet = drain_startup(port)
            report["startup_rx_hex"] = startup.hex(" ")
            assert quiet, "startup not quiet"
            client = Client(port, report)
            client.discover()

            def unconfigured():
                ids = dict(job_id="before-config", batch_id="step4-batch", part_id=1)
                seq = client.send(dict(type="PRODUCE_PART", **ids))
                client.expect(seq, ["RECEIVED", "REJECTED"], ids, "NOT_CONFIGURED")

            def invalid():
                for i, value in enumerate([True, False, 0, -1, 60001, 1.5, "1000", None, 1000.0]):
                    client.reject_config(value, i)
                for i, value in enumerate([True, 0, -1, 2147483648, 1.5, "1", None]):
                    ids = dict(job_id=f"invalid-part-{i}", batch_id="step4-batch")
                    seq = client.send(dict(type="PRODUCE_PART", **ids, part_id=value))
                    client.expect(seq,["RECEIVED","REJECTED"],ids,"INVALID_JOB")
                for obj in [dict(type="CONFIGURE_PRODUCTION",cmd_id="missing"),
                            dict(type="CONFIGURE_PRODUCTION",cmd_id="extra",production_time_ms=1,extra=1),
                            dict(type="UNKNOWN",cmd_id="unknown")]:
                    seq=client.send(obj)
                    client.expect(seq,["RECEIVED","REJECTED"],dict(cmd_id=obj["cmd_id"]))
                # No usable application identity, or invalid JSON: bounded silence.
                for raw in [b'{"type":', b'[]', b'{"type":"PRODUCE_PART","job_id":true}',
                            b'{"cmd_id":"a","cmd_id":"b"}', b'{"cmd_id":"bad\xff"}',
                            json.dumps(dict(type="CONFIGURE_PRODUCTION",cmd_id="x"*49,production_time_ms=1)).encode(),
                            json.dumps(dict(type="PRODUCE_PART",job_id="",batch_id="b",part_id=1)).encode()]:
                    client.send(raw=raw)
                    assert client.next(0.2) is None, "invalid request produced an event"
                client.send(dict(type="PRODUCE_PART",job_id="bad-crc",batch_id="b",part_id=1),corrupt=True)
                assert client.next(0.2) is None, "trusted IDs from corrupt ATR"

            actions = [unconfigured, lambda:client.configure(1000), invalid,
                       lambda:client.job(1000,1), lambda:client.configure(2500), lambda:client.job(2500,2)]
            for name, action in zip(PLAN, actions):
                check = dict(name=name, passed=False)
                report["checks"].append(check)
                action()
                check["passed"] = True
                print(name+": PASS")
            report["passed"] = True
    except (serial.SerialException, OSError, RuntimeError, AssertionError, ValueError, KeyboardInterrupt) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print("FAIL:",report["error"])
    finally:
        report["not_run"] = PLAN[len(report["checks"]):]
        report["port_closed"] = port is None or not port.is_open
        args.log.parent.mkdir(parents=True,exist_ok=True)
        args.log.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}; port_closed={report['port_closed']}; log={args.log}")
    return 0 if report["passed"] and report["port_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
