"""Bounded, receive-only setup check; not the production gateway protocol."""
import argparse
from pathlib import Path
import sys
import time

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="explicit board port, e.g. COM3")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--log", type=Path, default=Path("results/setup_serial.log"))
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    ready = False
    heartbeat_count = 0
    pending = bytearray()
    try:
        # Set control lines before opening to avoid deliberately resetting A.
        with serial.Serial(port=None, baudrate=115200, timeout=0.2) as port:
            port.dtr = False
            port.rts = False
            port.port = args.port
            port.open()
            with args.log.open("w", encoding="utf-8") as log:
                deadline = time.monotonic() + args.seconds
                while time.monotonic() < deadline:
                    pending.extend(port.read(256))
                    while b"\n" in pending:
                        raw, _, remainder = pending.partition(b"\n")
                        pending = bytearray(remainder)
                        line = raw.decode("utf-8", errors="replace").rstrip("\r")
                        print(line)
                        log.write(line + "\n")
                        ready |= line.startswith("MCT431_A_SETUP READY ")
                        heartbeat_count += line.startswith("MCT431_A_SETUP ALIVE count=")
                if pending:
                    log.write(pending.decode("utf-8", errors="replace"))
    except (serial.SerialException, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    # READY occurs only at boot; a late reader can still verify the running app.
    passed = heartbeat_count >= 2
    print(f"{'PASS' if passed else 'FAIL'}: ready_seen={ready}, "
          f"heartbeats={heartbeat_count}; serial port closed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
