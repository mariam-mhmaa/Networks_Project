"""Targeted gateway check: local old configuration is historical, not current."""
import argparse
import json
from pathlib import Path
import time
import serial
from gateway_client import ProductionRun
from session import SessionFault
from retry import write_retry_csv
from two_way_test import drain_startup

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True)
    parser.add_argument("--log",type=Path,default=Path("results/step5c_gateway_cache.json"))
    args=parser.parse_args()
    report=dict(tx=[],rx_chunks_hex=[],events=[],passed=False); port=None
    try:
        with serial.Serial(port=None,baudrate=115200,timeout=.01,write_timeout=.5) as port:
            port.dtr=port.rts=False; port.port=args.port; port.open()
            port.rts=True; time.sleep(.1); port.rts=False # Explicit test reset.
            startup,quiet=drain_startup(port); assert quiet
            report["startup_rx_hex"]=startup.hex(" ")
            run=ProductionRun(port,report); run.connect_or_recover()
            run.configure(1,"cfg:1",500); run.configure(2,"cfg:2",1500)
            old=run.configure(1,"cfg:1",500)
            assert old["outcome"]=="COMPLETED" and old["local_result_only"] and not old["attempts"]
            assert run.production_time_ms==1500 and not run.configured and not run.started
            try: run.start()
            except SessionFault: pass
            else: raise AssertionError("cached old setting armed Start")
            assert run.controller.completion_count==2
            report.update(passed=True,current_ms=run.production_time_ms,old_result_was_local=True,start_blocked=True)
    except (OSError,RuntimeError,ValueError,AssertionError) as exc:
        report["error"]=f"{type(exc).__name__}: {exc}"
    finally:
        report["port_closed"]=port is None or not port.is_open
        args.log.parent.mkdir(parents=True,exist_ok=True)
        args.log.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        write_retry_csv(report,args.log.with_suffix(".csv"))
    print(f"{'PASS' if report['passed'] else 'FAIL'}: local historical configuration; port_closed={report['port_closed']}")
    return 0 if report["passed"] and report["port_closed"] else 1

if __name__=="__main__": raise SystemExit(main())
