"""Host the existing toy-workshop screen and real serial/TCP gateway."""
import argparse
import uvicorn
from gateway.production.client import AClient
from gateway.inspection.client import BClient
from gateway.production.coordinator import BatchGateway
from .server import create_app
from .service import OperatorService
from .evidence import EventLog


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("serial_port", help="identified A port, for example COM5")
    p.add_argument("inspection_host", help="B's current IPv4 address")
    p.add_argument("--inspection-port", type=int, default=5001)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--state-file", required=True)
    p.add_argument("--operator-stale-seconds", type=float, default=5.0)
    p.add_argument("--serial-trace", "--events", dest="serial_trace", default="serial.local.jsonl",
                   help="append-only raw A serial trace (--events remains a compatible alias)")
    args = p.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.inspection_port <= 65535:
        p.error("Ports must be in 1..65535")
    capture = EventLog(args.serial_trace)
    factories = {"A": lambda: AClient(args.serial_port, log=capture.serial_logger()), "B": lambda: BClient(args.inspection_host, args.inspection_port)}
    core = BatchGateway(factories["A"](), factories["B"](), queue_capacity=1, full_policy="block", ledger_path=args.state_file)
    service = OperatorService(core, factories=factories, lease_s=args.operator_stale_seconds, evidence=capture)
    try:
        capture.emit("gateway","server_started",{"gateway_id":service.gateway_id,"serial_port":args.serial_port,
            "inspection_host":args.inspection_host,"inspection_port":args.inspection_port,
            "listen_host":args.host,"listen_port":args.port})
        print("Application history: " + core.b.ledger.path, flush=True)
        print("Raw A serial trace: " + str(capture.path), flush=True)
        uvicorn.run(create_app(service), host=args.host, port=args.port, workers=1, ws_max_size=4096)
    finally:
        capture.close()


if __name__ == "__main__": main()
