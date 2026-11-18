"""Run a real USB A -> gateway queue -> TCP B batch without the operator UI."""
import argparse
import asyncio
import json
import sqlite3
from .client import AClient, ProductionSettings
from .coordinator import BatchGateway
from gateway.inspection.client import BClient, Settings
from gateway.inspection.coordinator import GatewayFault
from gateway.inspection.wire import ProtocolError


async def exercise(args):
    gateway = BatchGateway(
        AClient(args.serial_port, heartbeat_age=args.a_stale_seconds),
        BClient(args.host, args.port), queue_capacity=args.queue_capacity,
        full_policy=args.full_policy, ledger_path=args.state_file)
    try:
        await gateway.start_run(ProductionSettings(args.production_ms),
                                Settings(args.inspection_ms, args.rule_n, args.rule_k), args.parts)
        await gateway.wait()
        # Wait for a current idle heartbeat after the final job, bounded by
        # the configured A stale window. No job deadline/retry is extended.
        end = asyncio.get_running_loop().time() + args.a_stale_seconds
        while not (gateway._ready(gateway.a) and gateway._ready(gateway.b.client)):
            if asyncio.get_running_loop().time() >= end:
                raise GatewayFault("fresh idle evidence unavailable for closure")
            await asyncio.sleep(.05)
        print(json.dumps(await gateway.close_run(), indent=2))
    except BaseException:
        print(json.dumps(gateway.snapshot(), indent=2))
        raise
    finally:
        await gateway.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial_port", help="identified A port, e.g. COM5")
    parser.add_argument("host", help="B's current IPv4 address")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--parts", type=int, required=True)
    parser.add_argument("--production-ms", type=int, required=True)
    parser.add_argument("--inspection-ms", type=int, required=True)
    parser.add_argument("--rule-n", type=int, required=True)
    parser.add_argument("--rule-k", type=int, required=True)
    parser.add_argument("--queue-capacity", type=int, required=True)
    parser.add_argument("--full-policy", choices=["block", "fault"], required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--a-stale-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 < args.a_stale_seconds < float("inf"):
        parser.error("port/stale settings must be finite and positive; port <=65535")
    try:
        asyncio.run(exercise(args))
    except (GatewayFault, ProtocolError, ValueError, OSError, sqlite3.Error, asyncio.TimeoutError) as exc:
        parser.exit(1, f"FAILED: {exc}\nBatch evidence retained; explicit recovery is required.\n")


if __name__ == "__main__":
    main()
