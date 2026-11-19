"""Temporary raw XOR test. No SLIP, ATR, CRC or production messages."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

import serial


def read_exact(port, count, timeout, read_sizes):
    """Accumulate short reads up to count, under one overall deadline."""
    received = bytearray()
    deadline = time.monotonic() + timeout
    while len(received) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        port.timeout = min(0.1, remaining)
        # Intentionally small reads exercise accumulation on actual hardware.
        chunk = port.read(min(7, count - len(received)))
        if chunk:
            received.extend(chunk)
            read_sizes.append(len(chunk))
    return bytes(received)


def drain_startup(port, timeout=5.0):
    """Discard only pre-test output: >=1 s settling and >=0.5 s silence."""
    start = last_byte = time.monotonic()
    discarded = bytearray()
    port.timeout = 0.1
    while time.monotonic() - start < timeout:
        chunk = port.read(256)
        now = time.monotonic()
        if chunk:
            discarded.extend(chunk)
            last_byte = now
        if now - start >= 1.0 and now - last_byte >= 0.5:
            return bytes(discarded), True
    return bytes(discarded), False


def check_case(port, name, payload, timeout, record):
    expected = bytes(value ^ 0xA5 for value in payload)
    record.update(name=name, intended_tx_hex=payload.hex(" "), tx_hex="",
                  expected_rx_hex=expected.hex(" "), rx_hex="", extra_rx_hex="",
                  read_sizes=[], passed=False)
    sent = bytearray()
    deadline = time.monotonic() + timeout
    while len(sent) < len(payload):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            record["error"] = "write deadline expired"
            return False
        port.write_timeout = min(0.5, remaining)
        # Split writes deliberately; no assumed UART message boundaries.
        count = port.write(payload[len(sent):len(sent) + 3])
        if count:
            sent.extend(payload[len(sent):len(sent) + count])
            record["tx_hex"] = sent.hex(" ")
        time.sleep(0.002)
    received = read_exact(port, len(expected), timeout, record["read_sizes"])
    record["rx_hex"] = received.hex(" ")
    # Never discard traffic during a case. Extra debug/heartbeat bytes fail it.
    port.timeout = 0.25
    extra = port.read(256)
    record["extra_rx_hex"] = extra.hex(" ")
    record["passed"] = received == expected and not extra
    if not record["passed"]:
        record["error"] = "incomplete, incorrect or extra response bytes"
    return record["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="e.g. COM3")
    parser.add_argument("--baud", type=int, default=115200,
                        help="must match firmware's fixed 115200 for this step")
    parser.add_argument("--timeout", type=float, default=3.0,
                        help="overall deadline per write/read phase in seconds")
    parser.add_argument("--log", type=Path, default=Path("results/step2_serial.json"))
    args = parser.parse_args()
    if args.baud <= 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("baud and timeout must be positive finite values")
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), port=args.port,
                  baud=args.baud, settings="8N1, no flow control", transform="byte XOR 0xA5",
                  startup_rx_hex="", cases=[], passed=False, port_closed=False)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    port = None
    try:
        # No monitor is launched. Context manager also closes on timeout/error.
        with serial.Serial(port=None, baudrate=args.baud, bytesize=serial.EIGHTBITS,
                           parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                           timeout=0.1, write_timeout=0.5,
                           xonxoff=False, rtscts=False, dsrdtr=False) as port:
            port.dtr = False
            port.rts = False
            port.port = args.port
            port.open()
            startup, quiet = drain_startup(port)
            report["startup_rx_hex"] = startup.hex(" ")
            if not quiet:
                raise RuntimeError("No quiet test mode within 5 s; wrong firmware or continuing logs")
            cases = [("ordinary_text", b"MCT431 serial test\r\n"),
                     ("special_binary", bytes([0x00, 0xC0, 0xDB, 0xFF, 0x41, 0x00, 0xFF])),
                     ("all_byte_values", bytes(range(256)))]
            for name, payload in cases:
                record = {}
                report["cases"].append(record)
                passed = check_case(port, name, payload, args.timeout, record)
                print(f"{name}: {'PASS' if passed else 'FAIL'} ({len(payload)} bytes)")
                if not passed:
                    break
            report["passed"] = len(report["cases"]) == len(cases) and all(
                case["passed"] for case in report["cases"])
    except (serial.SerialException, OSError, RuntimeError, KeyboardInterrupt) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAIL: {report['error']}")
    finally:
        report["port_closed"] = port is None or not port.is_open
        args.log.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}; port_closed={report['port_closed']}; log={args.log}")
    return 0 if report["passed"] and report["port_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
