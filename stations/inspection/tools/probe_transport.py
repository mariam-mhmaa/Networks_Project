"""PC-to-B framed echo diagnostic; requires the explicit firmware test option.

No inspection commands, verdicts, retries, or operation-controller behavior.
Uses only the Python standard library. Network errors fail the probe.
"""
import argparse
import json
import socket
import struct
import time


def exact(sock, length):
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError("B closed before returning the full diagnostic frame")
        data.extend(chunk)
    return bytes(data)


def receive(sock):
    length, = struct.unpack(">I", exact(sock, 4))
    if not 1 <= length <= 1024:
        raise ValueError(f"Invalid diagnostic response length: {length}")
    return exact(sock, length)


def probe(host, port, timeout):
    # Match a single two-frame burst to the bounded firmware TX queue.
    payloads = [
        json.dumps({"diagnostic": "transport_echo", "sequence": 1},
                   separators=(",", ":")).encode("utf-8"),
        json.dumps({"diagnostic": "transport_echo", "text": "Español ✓", "sequence": 2},
                   ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    ]
    wire = b"".join(struct.pack(">I", len(p)) + p for p in payloads)
    started = time.monotonic()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        # Deliberately split the first prefix and payload across writes.
        for chunk in (wire[:1], wire[1:3], wire[3:9], wire[9:]):
            sock.sendall(chunk)
        for payload in payloads:
            if receive(sock) != payload:
                raise ValueError("Diagnostic echo changed the payload bytes")
    return {
        "test": "framed_tcp_echo", "result": "PASS", "host": host, "port": port,
        "frames": len(payloads), "elapsed_ms": round((time.monotonic() - started) * 1000),
        "scope": "Transport only; application and inspection behavior NOT TESTED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="B's current IPv4 address from its serial log")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.timeout <= 0:
        parser.error("port must be 1..65535 and timeout must be positive")
    try:
        print(json.dumps(probe(args.host, args.port, args.timeout), indent=2))
    except (OSError, EOFError, ValueError) as exc:
        parser.exit(1, f"FAIL: {exc}\nCheck B's address, shared network, and diagnostic option.\n")


if __name__ == "__main__":
    main()
