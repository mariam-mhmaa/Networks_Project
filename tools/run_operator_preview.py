"""Explicit local SOFTWARE preview using the real native A/B C applications.

Requires MSVC; never opens a COM port or connects to a physical station.
The screen labels this test mode. The production launcher is gateway.operator.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "member1/production-a/tests"))
import test_integrated as native
from gateway.production.client import AClient
from gateway.inspection.client import BClient
from gateway.production.coordinator import BatchGateway
from gateway.operator.service import OperatorService
from gateway.operator.server import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--drop-first-production", action="store_true", help="fault scenario; use a fresh state file")
    args = parser.parse_args()
    fixture = native.IntegratedTests
    processes = []
    fixture.setUpClass()
    try:
        for exe, flags in ((fixture.exe, ["--drop-first-request"] if args.drop_first_production else []), (fixture.bexe, [])):
            process = subprocess.Popen([str(exe), *flags], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(process)
        aport, bport = [int(process.stdout.readline()) for process in processes]
        factories = {"A": lambda: AClient(f"socket://127.0.0.1:{aport}"), "B": lambda: BClient("127.0.0.1", bport)}
        core = BatchGateway(factories["A"](), factories["B"](), queue_capacity=5, full_policy="block", ledger_path=args.state_file)
        service = OperatorService(core, simulation=True, factories=factories)
        print(f"SOFTWARE PREVIEW http://127.0.0.1:{args.port} (native C peers; no physical hardware)", flush=True)
        uvicorn.run(create_app(service), host="127.0.0.1", port=args.port, workers=1, ws_max_size=4096)
    finally:
        for process in processes:
            if process.poll() is None: process.terminate()
            process.wait(timeout=5); process.stdout.close(); process.stderr.close()
        fixture.doClassCleanups()


if __name__ == "__main__": main()
