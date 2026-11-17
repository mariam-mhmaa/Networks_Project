"""Standalone B functional exercise with a clearly simulated production source."""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import time
import sqlite3
from .client import BClient, Settings
from .coordinator import GatewayFault, InspectionGateway
from .wire import ProtocolError


async def exercise(args):
    events = asyncio.Queue(maxsize=1024) if args.events else None
    async def write_events():
        def append(lines):
            with Path(args.events).open("a", encoding="utf-8") as file:
                file.writelines(lines)
        while True:
            line = await events.get()
            if line is None:
                return
            lines = [line]
            while not events.empty() and len(lines) < 64:
                item = events.get_nowait()
                if item is None:
                    await asyncio.to_thread(append, lines)
                    return
                lines.append(item)
            await asyncio.to_thread(append, lines)
    event_writer = asyncio.create_task(write_events()) if events is not None else None
    def log(kind, body):
        if events is not None:
            if event_writer.done():
                event_writer.result()
            events.put_nowait(json.dumps({"monotonic_s": time.monotonic(), "kind": kind,
                                          "body": body}, separators=(",", ":")) + "\n")
    client = BClient(args.host, args.port, log=log)
    gateway = InspectionGateway(client, queue_capacity=args.queue_capacity,
                                full_policy=args.full_policy, ledger_path=args.state_file)
    try:
        await gateway.start_run(Settings(args.inspection_ms, args.rule_n, args.rule_k), args.parts)
        for _ in range(args.parts):
            part = await gateway.reserve_part()
            # Test harness only. The real A adapter calls produced() after its
            # actual, matching, completed production operation.
            await gateway.produced(part)
        snapshot = await gateway.wait_inspection()
        outcomes = [asdict(value) for value in gateway.results.values()]
        closed = await gateway.close_run()
        if closed.state != "COMPLETED":
            raise GatewayFault("inspection run completed but closure is unresolved")
        print(json.dumps({"scope": "B functional test; production source simulated, USB A/UI NOT TESTED",
                          "batch": snapshot, "outcomes": outcomes,
                          "close": asdict(closed)}, indent=2))
    finally:
        await gateway.shutdown()
        if events is not None:
            if not event_writer.done():
                await events.put(None)
            await event_writer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--parts", type=int, required=True)
    parser.add_argument("--inspection-ms", type=int, required=True)
    parser.add_argument("--rule-n", type=int, required=True)
    parser.add_argument("--rule-k", type=int, required=True)
    parser.add_argument("--queue-capacity", type=int, required=True)
    parser.add_argument("--full-policy", choices=["block", "fault"], required=True)
    parser.add_argument("--state-file", required=True, help="local SQLite evidence/counter file")
    parser.add_argument("--events", help="optional local JSONL network evidence")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    try:
        asyncio.run(exercise(args))
    except (GatewayFault, ProtocolError, ValueError, OSError, sqlite3.Error, asyncio.TimeoutError) as exc:
        parser.exit(1, f"FAILED: {exc}\nNo unknown inspection is counted as PASS or FAIL.\n")


if __name__ == "__main__":
    main()
