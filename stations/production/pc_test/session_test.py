"""Step 5B hardware/session tests; controlled RX heartbeat loss, no auto retry."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import serial
from production_test import Client
from session import SessionFault
from two_way_test import drain_startup
from gateway_client import ProductionRun

PLAN=["discovery_and_unconfigured_heartbeats","session_rejections_no_side_effects",
      "idle_and_same_session_reconnect","heartbeat_timeout_and_observed_recovery",
      "long_job_heartbeats_and_restart_fault","old_session_rejected_and_explicit_recovery"]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True)
    parser.add_argument("--log",type=Path,default=Path("results/step5b_sessions.json"))
    args=parser.parse_args()
    report=dict(started_utc=datetime.now(timezone.utc).isoformat(),port=args.port,
                tx=[],rx_chunks_hex=[],events=[],timings=[],checks=[],passed=False)
    port=None
    try:
        with serial.Serial(port=None,baudrate=115200,timeout=0.02,write_timeout=0.5,
                           xonxoff=False,rtscts=False,dsrdtr=False) as port:
            port.dtr=port.rts=False; port.port=args.port; port.open()
            port.rts=True; time.sleep(0.1); port.rts=False # Intentional initial test reset.
            startup,quiet=drain_startup(port); assert quiet
            report["startup_rx_hex"]=startup.hex(" ")
            c=Client(port,report,assign_operations=False)
            initial=None; old=None; recovery=None

            def observe(seconds,state=None,client=None):
                client=client or c
                start=len(report.get("status_events",[])); end=time.monotonic()+seconds
                while time.monotonic()<end:
                    assert client.next(min(0.1,end-time.monotonic())) is None,"unsolicited request response"
                beats=[i for i in report["status_events"][start:] if i["event"]["type"]=="HEARTBEAT"]
                if state:
                    assert len(beats)>=2,(state,len(beats))
                    assert all(i["event"]["state"]==state for i in beats)
                return beats

            def status(client):
                seq=client.send(dict(type="GET_STATUS"),bind_session=False)
                item=client.next(2)
                assert item and item["seq"]==seq and item["event"]["type"]=="STATUS"
                return item["event"]

            def configure(client,n,ms):
                obj=dict(type="CONFIGURE_PRODUCTION",op_no=n,cmd_id=f"cfg:{n}",production_time_ms=ms)
                seq=client.send(obj)
                client.expect(seq,["RECEIVED","ACCEPTED","PRODUCTION_CONFIGURED"],dict(op_no=n,cmd_id=f"cfg:{n}"))

            def discovery():
                nonlocal initial
                initial=c.discover(); report["initial_status"]=initial
                assert initial["state"]=="UNCONFIGURED" and initial["high_water"]==0
                observe(2.2,"UNCONFIGURED")
                again=status(c)
                assert (again["high_water"],again["production_time_ms"],again["active_op_no"])==(0,0,None)

            def session_rejections():
                for session in (None,"0"*32):
                    for kind in ("CONFIGURE_PRODUCTION","PRODUCE_PART"):
                        obj=(dict(type=kind,op_no=1,cmd_id="cfg:1",production_time_ms=10)
                             if kind=="CONFIGURE_PRODUCTION" else
                             dict(type=kind,op_no=2,job_id="job:2",batch_id="session",part_id=1))
                        if session: obj["boot_id"]=session
                        seq=c.send(obj,bind_session=False)
                        identity={k:obj[k] for k in ("op_no","cmd_id","job_id","batch_id","part_id") if k in obj}
                        c.expect(seq,["RECEIVED","REJECTED"],identity,"SESSION_MISMATCH")
                snapshot=status(c)
                assert (snapshot["high_water"],snapshot["production_time_ms"],snapshot["state"])==(0,0,"UNCONFIGURED")

            def idle_reconnect():
                configure(c,1,15000)
                observe(2.2,"IDLE")
                port.close(); time.sleep(0.2); port.open() # Ordinary reopen, no reset pulse.
                observe(2.2,"IDLE")
                assert status(c)["boot_id"]==initial["boot_id"]
                report["ordinary_reopen_boot_unchanged"]=True

            def timeout_recovery():
                guard=c.receiver.guard
                original=guard.observe
                suppressed=[]
                def drop(event,seq=0):
                    if event.get("type")=="HEARTBEAT":
                        suppressed.append(event); return False
                    return original(event,seq)
                guard.observe=drop
                deadline=guard.last_heartbeat+5.1
                detected=None
                while time.monotonic()<deadline:
                    c.receiver.pump(0.02)
                    if guard.fault and detected is None: detected=time.monotonic()-guard.last_heartbeat
                guard.check()
                report["heartbeat_fault_injection"]=dict(method="RX heartbeat suppression; serial still read",
                    suppressed=len(suppressed),elapsed_since_valid_s=time.monotonic()-guard.last_heartbeat,
                    fault=guard.fault,detected_after_s=detected)
                assert guard.fault=="HEARTBEAT_TIMEOUT" and not guard.available
                assert detected is not None and 5<=detected<5.15,detected
                guard.observe=original
                end=time.monotonic()+1.5
                while not guard.available and time.monotonic()<end: c.receiver.pump(0.02)
                assert guard.available and guard.fault=="HEARTBEAT_TIMEOUT"
                try: c.send(dict(type="CONFIGURE_PRODUCTION",op_no=2,cmd_id="cfg:2",production_time_ms=10))
                except SessionFault: pass
                else: raise AssertionError("same-session recovery silently resumed work")
                # Explicit new run: new guard/discovery and configuration, not automatic continuation.
                nonlocal_client=Client(port,report,assign_operations=False)
                assert nonlocal_client.discover()["boot_id"]==initial["boot_id"]
                configure(nonlocal_client,2,15000)
                return nonlocal_client

            def restart_job():
                nonlocal old
                old=c.receiver.guard.boot_id
                obj=dict(type="PRODUCE_PART",op_no=3,job_id="job:3",batch_id="session",part_id=1)
                seq=c.send(obj); c.expect(seq,["RECEIVED","ACCEPTED"],dict(op_no=3,job_id="job:3",batch_id="session",part_id=1))
                beats=observe(2.2,"PRODUCING")
                assert all(i["event"]["active_op_no"]==3 and i["event"]["high_water"]==3 for i in beats)
                port.rts=True; time.sleep(0.1); port.rts=False # Deliberate restart of uncertain work.
                end=time.monotonic()+4
                while c.receiver.guard.fault!="RESTART" and time.monotonic()<end: c.receiver.pump(0.02)
                assert c.receiver.guard.fault=="RESTART"
                assert c.receiver.guard.observed_boot_id!=old
                try: c.next(0.1)
                except SessionFault: pass
                else: raise AssertionError("restart did not stop current run")
                # Continue read-only observation even though work is faulted.
                before=len(report["status_events"])
                end=time.monotonic()+1.2
                while time.monotonic()<end: c.receiver.pump(0.02)
                assert len(report["status_events"])>before

            def explicit_recovery():
                nonlocal recovery
                recovery=Client(port,report,assign_operations=False)
                snapshot=recovery.discover(); report["after_restart_status"]=snapshot
                assert snapshot["boot_id"]!=old
                assert (snapshot["state"],snapshot["high_water"],snapshot["production_time_ms"])==("UNCONFIGURED",0,0)
                obj=dict(type="CONFIGURE_PRODUCTION",op_no=1,cmd_id="cfg:1",production_time_ms=1000,boot_id=old)
                seq=recovery.send(obj)
                recovery.expect(seq,["RECEIVED","REJECTED"],dict(op_no=1,cmd_id="cfg:1"),"SESSION_MISMATCH")
                assert status(recovery)["high_water"]==0
                run=ProductionRun(port,report)
                assert run.connect_or_recover()["boot_id"]==snapshot["boot_id"]
                try: run.start()
                except SessionFault: pass
                else: raise AssertionError("recovery started without configuration")
                run.configure(1,"cfg:1",1000)
                try: run.produce(2,"new-job:2","explicit-new-run",2)
                except SessionFault: pass
                else: raise AssertionError("recovery produced without explicit start")
                run.start()
                run.produce(2,"new-job:2","explicit-new-run",2)
                assert run.client.next(0.2) is None

            actions=[discovery,session_rejections,idle_reconnect,timeout_recovery,restart_job,explicit_recovery]
            for name,action in zip(PLAN,actions):
                check=dict(name=name,passed=False); report["checks"].append(check)
                value=action()
                if name=="heartbeat_timeout_and_observed_recovery": c=value
                check["passed"]=True; print(name+": PASS")
            report["passed"]=True
    except (OSError,RuntimeError,AssertionError,ValueError,KeyboardInterrupt) as exc:
        report["error"]=f"{type(exc).__name__}: {exc}"; print("FAIL:",report["error"])
    finally:
        report["not_run"]=PLAN[len(report["checks"]):]
        report["port_closed"]=port is None or not port.is_open
        args.log.parent.mkdir(parents=True,exist_ok=True)
        args.log.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}; port_closed={report['port_closed']}; log={args.log}")
    return 0 if report["passed"] and report["port_closed"] else 1


if __name__=="__main__": raise SystemExit(main())
