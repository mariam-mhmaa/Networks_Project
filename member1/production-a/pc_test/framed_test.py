"""Step 3 hardware functional tests; not formal benchmarking."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import serial

from protocol import SlipDecoder, decode_atr, crc16, slip_encode
from protocol_cases import cases
from two_way_test import drain_startup
from receiver import Receiver


def exchange(port, case, timeout, record, receiver):
    tx, expected = case["tx"], case["expected"]
    record.update(name=case["name"], intended_tx_hex=tx.hex(" "), tx_hex="",
                  expected_rx_hex=expected.hex(" "), rx_hex="", read_sizes=[],
                  write_sizes=[], passed=False)
    sent = 0
    deadline = time.monotonic() + timeout
    while sent < len(tx):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("write deadline")
        port.write_timeout = min(0.5, remaining)
        end = min(len(tx), sent + (case["split"] or len(tx)))
        count = port.write(tx[sent:end])
        if count:
            sent += count
            record["write_sizes"].append(count)
            record["tx_hex"] = tx[:sent].hex(" ")
        if case["split"]:
            time.sleep(0.002)

    rx = bytearray()
    rejected_before=receiver.rejections+receiver.decoder.rejected
    deadline = time.monotonic() + (timeout if expected else 0.35)
    quiet_deadline = None
    while True:
        limit = min(deadline, quiet_deadline) if quiet_deadline else deadline
        remaining = limit - time.monotonic()
        if remaining <= 0:
            break
        item=receiver.next(remaining,strict_session=False)
        if item:
            chunk=slip_encode(bytes.fromhex(item["atr_hex"]))
            rx.extend(chunk)
            record["read_sizes"].append(len(chunk))
            record["rx_hex"] = rx.hex(" ")
            if len(rx) > len(expected):
                break
            if expected and len(rx) == len(expected) and quiet_deadline is None:
                quiet_deadline = time.monotonic() + 0.2
                deadline = max(deadline, quiet_deadline)
    decoder = SlipDecoder()
    responses = []
    try:
        for raw in decoder.feed(rx):
            test_id, seq, payload = decode_atr(raw)
            responses.append(dict(test_id=test_id, seq=seq, payload_hex=payload.hex(" "), crc_valid=True))
    except ValueError as exc:
        record["parse_error"] = str(exc)
    record["responses"] = responses
    record["slip_rejections"] = decoder.rejected
    record["passed"] = (bytes(rx) == expected and not decoder.rejected and "parse_error" not in record
                         and receiver.rejections+receiver.decoder.rejected==rejected_before)
    return record["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--log", type=Path, default=Path("results/step3_hardware.json"))
    args = parser.parse_args()
    if args.baud <= 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("positive baud and finite positive timeout required")
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), scope="actual hardware",
                  port=args.port, baud=args.baud, settings="8N1, no flow control",
                  cases=[], not_run=[c["name"] for c in cases()], passed=False, port_closed=False)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    port = None
    try:
        if crc16(b"123456789") != 0x29B1:
            raise RuntimeError("CRC reference failed")
        with serial.Serial(port=None, baudrate=args.baud, bytesize=serial.EIGHTBITS,
                           parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                           timeout=0.05, write_timeout=0.5,
                           xonxoff=False, rtscts=False, dsrdtr=False) as port:
            port.dtr = port.rts = False
            port.port = args.port
            port.open()
            startup, quiet = drain_startup(port)
            report["startup_rx_hex"] = startup.hex(" ")
            if not quiet:
                raise RuntimeError("startup did not become quiet in 5 seconds")
            all_cases = cases()
            receiver=Receiver(port,report)
            for case in all_cases:
                record = {}
                report["cases"].append(record)
                passed = exchange(port, case, args.timeout, record,receiver)
                print(f"{case['name']}: {'PASS' if passed else 'FAIL'}")
                if not passed:
                    break
            report["not_run"] = [case["name"] for case in all_cases[len(report["cases"]):]]
            report["passed"] = not report["not_run"] and all(c["passed"] for c in report["cases"])
    except (serial.SerialException, OSError, RuntimeError, KeyboardInterrupt) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print("FAIL:", report["error"])
    finally:
        report["not_run"] = [c["name"] for c in cases()[len(report["cases"]):]]
        report["port_closed"] = port is None or not port.is_open
        args.log.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}; port_closed={report['port_closed']}; log={args.log}")
    return 0 if report["passed"] and report["port_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
