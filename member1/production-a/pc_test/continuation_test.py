"""Targeted client-only status/reconciliation/explicit different-work hardware checks."""
import argparse
import copy
import json
from pathlib import Path
import time
import serial
from gateway_client import ProductionRun,OperationUnresolved,ContinuationBlocked
from production_test import Client
from protocol import encode_atr
from two_way_test import drain_startup

PLAN=["unresolved_is_not_station_unavailable","eligibility_and_explicit_different_part",
      "status_dispatch_reconciles_late_result_once","busy_and_queued_status_rejected",
      "restart_fault_and_unconfigured_assessment"]

def job(n,part=None):
    return dict(type="PRODUCE_PART",op_no=n,job_id=f"work:{n}",batch_id="continuation-test",part_id=n if part is None else part)

def item(seq,event):
    raw=encode_atr(0,seq,json.dumps(event,separators=(",",":")).encode())
    return dict(test_id=0,seq=seq,event=event,monotonic=time.monotonic(),atr_hex=raw.hex(" "))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True)
    parser.add_argument("--log",type=Path,default=Path("results/continuation_hardware.json"))
    args=parser.parse_args()
    report=dict(tx=[],rx_chunks_hex=[],events=[],checks=[],passed=False)
    port=None
    try:
        with serial.Serial(port=None,baudrate=115200,timeout=.01,write_timeout=.5,
                           xonxoff=False,rtscts=False,dsrdtr=False) as port:
            port.dtr=port.rts=False; port.port=args.port; port.open()
            port.rts=True; time.sleep(.1); port.rts=False # Explicit initial test reset.
            startup,quiet=drain_startup(port); assert quiet
            report["startup_rx_hex"]=startup.hex(" ")
            run=ProductionRun(port,report); run.connect_or_recover()
            original=None; frozen=None; held=[]; latest_status=None

            def unresolved():
                nonlocal original,frozen
                run.configure(1,"cfg:1",300); run.start()
                def omit(received,attempt):
                    if received["event"]["type"]=="PART_PRODUCED" and not received["event"].get("replayed"):
                        held.append(copy.deepcopy(received))
                    return True # Diagnostic response loss only; heartbeat routing remains active.
                run.controller.omit=omit
                try: run.produce(2,"work:2","continuation-test",2)
                except OperationUnresolved as exc: original=exc.result
                else: raise AssertionError("expected unresolved simulated response loss")
                assert len(original["attempts"])==3 and held
                assert run.client.receiver.guard.available and run.client.receiver.guard.fault is None
                assert not run.configured and not run.started
                frozen=copy.deepcopy(run.ledger.results[(original["request"]["boot_id"],2)])
                snapshot=run.read_status(.8)
                assert snapshot["event"]["state"]=="IDLE"
                assert not run.operation_evidence(2)["confirmed_produced"],"STATUS falsely proved production"
                run.controller.omit=None

            def different_part():
                assessment=run.assess_continuation(job(3),.8)
                assert assessment["eligible"] and not run.started and not run.configured
                bad=run.assess_continuation(job(3,part=2),.8)
                assert "UNRESOLVED_PART_IDENTITY_REUSE" in bad["reasons"]
                result=run.produce_different(3,"work:3","continuation-test",3,.8)
                assert result["outcome"]=="COMPLETED"
                assert not run.started and not run.configured
                assert not run.operation_evidence(2)["confirmed_produced"]
                assert run.operation_evidence(3)["confirmed_produced"]
                assert run.ledger.results[(original["request"]["boot_id"],2)]==frozen

            def late_dispatch():
                nonlocal latest_status
                client=run.client; real_send=client.send; released=[False]
                def send_with_release(obj=None,**kwargs):
                    seq=real_send(obj,**kwargs)
                    if obj and obj.get("type")=="GET_STATUS" and not released[0]:
                        released[0]=True
                        client.receiver.pending.append(copy.deepcopy(held[0]))
                        report.setdefault("test_injections",[]).append(dict(type="release real withheld completion after stop",released_at=time.monotonic(),frame=held[0]))
                    return seq
                client.send=send_with_release
                try: latest_status=run.read_status(.8)
                finally: client.send=real_send
                assert latest_status["query_seq"]==client.seq and latest_status["event"]["state"]=="IDLE"
                assert run.dispatch.confirmed_part_count==2
                assert run.operation_evidence(2)["retry_outcome"]=="UNRESOLVED"
                assert run.operation_evidence(2)["confirmed_produced"]
                assert not run.operation_evidence(2)["automatic_retry_allowed"]
                for _ in range(2): assert not run.dispatch.reconcile(held[0])["new_confirmation"]
                wrong=copy.deepcopy(held[0]["event"]); wrong["job_id"]="other:2"
                assert not run.dispatch.reconcile(item(held[0]["seq"],wrong))["valid"]
                assert run.dispatch.confirmed_part_count==2 and not run.started
                before=len(report["tx"]); retry=run.controller.execute(original["request"],300)
                assert retry["outcome"]=="UNRESOLVED" and not retry["attempts"]
                assert len(report["tx"])==before
                assert run.ledger.results[(original["request"]["boot_id"],2)]==frozen

            def busy_and_stale():
                run.configure(4,"cfg:4",3000)
                request=job(5); seq=run.client.send(request)
                identity={k:request[k] for k in ("op_no","job_id","batch_id","part_id")}
                run.client.expect(seq,["RECEIVED","ACCEPTED"],identity)
                stale=item(Client._seq_counter+1,copy.deepcopy(latest_status["event"]))
                stale["monotonic"]=time.monotonic()-1
                run.client.receiver.pending.append(stale)
                report.setdefault("test_injections",[]).append(dict(type="synthetic queued old IDLE status with upcoming seq",frame=stale))
                assessment=run.assess_continuation(job(6),.8)
                assert not assessment["eligible"] and "STATION_NOT_IDLE" in assessment["reasons"]
                assert assessment["status"]["event"]["state"]=="PRODUCING"
                run.client.expect(seq,["PART_PRODUCED"],identity,timeout=4)

            def restart_and_unconfigured():
                old_boot=run.client.receiver.guard.boot_id
                port.rts=True; time.sleep(.1); port.rts=False # Explicit restart test.
                end=time.monotonic()+4
                while run.client.receiver.guard.fault!="RESTART" and time.monotonic()<end:
                    run.observe(.02)
                assert run.client.receiver.guard.fault=="RESTART"
                assessment=run.assess_continuation(job(6),.8)
                assert not assessment["eligible"] and run.client.receiver.guard.fault=="RESTART"
                assert assessment["status"] is not None and assessment["status"]["event"]["boot_id"]!=old_boot
                assert assessment["status"]["event"]["state"]=="UNCONFIGURED"
                assert not run.dispatch.reconcile(held[0])["valid"]
                new=run.connect_or_recover() # Explicit recovery discovery only; no configure or start.
                assert new["boot_id"]!=old_boot and new["state"]=="UNCONFIGURED"
                candidate=job(1); candidate["batch_id"]="explicit-new-session"
                assessment=run.assess_continuation(candidate,.8)
                assert not assessment["eligible"] and "STATION_UNCONFIGURED" in assessment["reasons"]
                assert not run.started and not run.configured
                assert run.ledger.results[(old_boot,2)]==frozen

            for name,action in zip(PLAN,[unresolved,different_part,late_dispatch,busy_and_stale,restart_and_unconfigured]):
                check=dict(name=name,passed=False); report["checks"].append(check)
                action(); check["passed"]=True; print(name+": PASS")
            report["passed"]=True
    except (OSError,RuntimeError,ValueError,AssertionError,KeyboardInterrupt) as exc:
        report["error"]=f"{type(exc).__name__}: {exc}"; print("FAIL:",report["error"])
    finally:
        report["not_run"]=PLAN[len(report["checks"]):]
        report["port_closed"]=port is None or not port.is_open
        args.log.parent.mkdir(parents=True,exist_ok=True)
        args.log.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}; port_closed={report['port_closed']}; log={args.log}")
    return 0 if report["passed"] and report["port_closed"] else 1

if __name__=="__main__": raise SystemExit(main())
