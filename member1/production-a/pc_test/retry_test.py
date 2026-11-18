"""Step 5C real-board tests with deterministic client-side response omission."""
import argparse
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import serial
from production_test import Client
from retry import RetryController,write_retry_csv
from session import SessionFault
from two_way_test import drain_startup

PLAN=["no_loss","acceptance_omission","completion_omission_and_late_duplicate",
      "retry_budget_exhaustion","repeated_running_deadline","configuration_historical_replay",
      "restart_interrupt","heartbeat_loss_interrupt","terminal_rejection"]

def cfg(n,ms): return dict(type="CONFIGURE_PRODUCTION",op_no=n,cmd_id=f"cfg:{n}",production_time_ms=ms)
def part(n=2): return dict(type="PRODUCE_PART",op_no=n,job_id=f"job:{n}",batch_id="retry-tests",part_id=n)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True)
    parser.add_argument("--log",type=Path,default=Path("results/step5c_retries.json"))
    parser.add_argument("--csv",type=Path,default=Path("results/step5c_retries.csv"))
    args=parser.parse_args()
    report=dict(started_utc=datetime.now(timezone.utc).isoformat(),port=args.port,
                tx=[],rx_chunks_hex=[],events=[],checks=[],passed=False)
    port=None
    try:
        with serial.Serial(port=None,baudrate=115200,timeout=0.01,write_timeout=0.5,
                           xonxoff=False,rtscts=False,dsrdtr=False) as port:
            port.dtr=port.rts=False; port.port=args.port; port.open()

            def fresh():
                port.rts=True; time.sleep(.1); port.rts=False # Explicit test isolation reset.
                startup,quiet=drain_startup(port); assert quiet
                report.setdefault("reset_startup_hex",[]).append(startup.hex(" "))
                client=Client(port,report,assign_operations=False)
                client.discover()
                return client,RetryController(client)

            def status(c):
                seq=c.send(dict(type="GET_STATUS"),bind_session=False)
                item=c.next(2)
                assert item and item["seq"]==seq and item["event"]["type"]=="STATUS",item
                return item["event"]

            def configure(e,n,ms):
                result=e.execute(cfg(n,ms))
                assert result["outcome"]=="COMPLETED",result
                return result

            def verify(result,outcome,attempts):
                assert result["outcome"]==outcome,(outcome,result)
                assert len(result["attempts"])==attempts,result["attempts"]
                # Actual serial bytes, identical JSON payload; only ATR seq differs.
                seqs=[a["seq"] for a in result["attempts"]]
                tx=[t for t in report["tx"] if t["seq"] in seqs and
                    json.loads(bytes.fromhex(t["payload_hex"]).decode()).get("boot_id")==result["request"]["boot_id"]]
                assert len(tx)==attempts
                assert len({t["payload_hex"] for t in tx})==1
                assert len(set(seqs))==len(seqs)
                assert result["finished_at"]<=result["absolute_deadline"]+.15,result

            def evidence(c,result):
                snapshot=status(c)
                responses=[t["response"] for t in result["trace"] if t["event"] in ("RESPONSE","IGNORED_RESPONSE")]
                event_types=[i["event"]["type"] for i in responses]
                accepted=[i for i in responses if i["event"]["type"]=="ACCEPTED"]
                terminal=[i for i in responses if i["event"]["type"]=="PART_PRODUCED"]
                assert len(accepted)<=1,"station accepted a duplicate again"
                assert snapshot["high_water"]==result["request"]["op_no"]
                assert snapshot["active_op_no"] is None
                original=[i for i in terminal if i["event"].get("replayed") is False]
                assert len(original)<=1
                if original:
                    assert original[0]["seq"]==result["attempts"][0]["seq"]
                result["station_evidence"]=dict(status=snapshot,accepted_frames=len(accepted),
                    original_terminal_frames=len(original),event_types=event_types,
                    cached_replay_frames=sum(i["event"].get("replayed") is True for i in terminal))

            def no_loss():
                c,e=fresh(); configure(e,1,300)
                result=e.execute(part(),300); verify(result,"COMPLETED",1); evidence(c,result)

            def acceptance_loss():
                c,e=fresh(); configure(e,1,1800)
                e.omit=lambda i,a:i["event"]["type"]=="ACCEPTED"
                result=e.execute(part(),1800); verify(result,"COMPLETED",2)
                assert result["completion"]["seq"]==result["attempts"][0]["seq"]
                assert result["completion"]["event"]["replayed"] is False
                assert result["finished_at"]-result["original_time"]<2.3,"timer restarted"
                assert any(t["event"]=="RESPONSE" and t["response"]["event"]["type"]=="OPERATION_RUNNING" for t in result["trace"])
                evidence(c,result)

            def completion_loss():
                c,e=fresh(); configure(e,1,300)
                e.omit=lambda i,a:i["event"]["type"]=="PART_PRODUCED" and not i["event"].get("replayed")
                result=e.execute(part(),300); verify(result,"COMPLETED",2); evidence(c,result)
                assert result["completion"]["event"]["replayed"] is True
                old=next(t["response"] for t in result["trace"] if t["event"]=="IGNORED_RESPONSE")
                # Explicit PC-side late duplicate injection, not a second station execution.
                c.receiver.pending.append(copy.deepcopy(old))
                report.setdefault("test_injections",[]).append(dict(kind="late completion copy",frame=old))
                e.omit=None
                next_result=configure(e,3,300)
                assert any(t["event"]=="QUARANTINED_RESPONSE" for t in next_result["trace"])
                count=e.completion_count
                again=e.execute(part(),300)
                assert again["outcome"]=="COMPLETED" and not again["new_logical_completion"]
                assert e.completion_count==count

            def exhaustion():
                c,e=fresh(); configure(e,1,300)
                e.omit=lambda i,a:True
                result=e.execute(part(),300); verify(result,"UNRESOLVED",3)
                assert result["finished_at"]-result["original_time"]>=3.3
                evidence(c,result) # Read-only status, NOT another attempt of the exhausted operation.
                assert result["station_evidence"]["cached_replay_frames"]>=1
                assert result["station_evidence"]["original_terminal_frames"]==1
                tx_count=len(report["tx"])
                again=e.execute(part(),300)
                assert again["outcome"]=="UNRESOLVED" and not again["attempts"]
                assert len(report["tx"])==tx_count,"re-entry reset an exhausted budget"

            def running_deadline():
                c,e=fresh(); configure(e,1,1800)
                original_next=c.next; template=[None]
                def copied_running(timeout,strict_session=True):
                    item=original_next(timeout,strict_session=strict_session)
                    if item and item["event"].get("type")=="OPERATION_RUNNING": template[0]=copy.deepcopy(item)
                    if item is None and template[0] is not None and timeout>0:
                        item=copy.deepcopy(template[0]); item["monotonic"]=time.monotonic()
                        report.setdefault("test_injections",[]).append(dict(kind="repeated captured running frame",frame=item))
                    return item
                c.next=copied_running
                e.omit=lambda i,a:i["event"]["type"] in ("ACCEPTED","PART_PRODUCED")
                result=e.execute(part(),1800); verify(result,"UNRESOLVED",3)
                assert template[0] is not None
                assert result["finished_at"]-result["original_time"]<4.95
                c.next=original_next
                evidence(c,result)

            def config_replay():
                c,e=fresh()
                ignored=[False]
                def omit(i,a):
                    if i["event"]["type"]=="PRODUCTION_CONFIGURED" and not ignored[0]:
                        ignored[0]=True
                        newer=RetryController(c).execute(cfg(2,1500))
                        assert newer["outcome"]=="COMPLETED"
                        report.setdefault("test_injections",[]).append(dict(kind="new configuration during withheld old result",op_no=2))
                        return True
                    return False
                e.omit=omit
                result=e.execute(cfg(1,500)); verify(result,"COMPLETED",2)
                assert result["completion"]["event"]["replayed"] is True
                assert status(c)["production_time_ms"]==1500
                e.omit=None
                produced=e.execute(part(3),1500); verify(produced,"COMPLETED",1)
                elapsed=produced["finished_at"]-produced["original_time"]
                assert 1.4<=elapsed<=2.0,elapsed
                evidence(c,produced)

            def restart():
                c,e=fresh(); configure(e,1,4000)
                old=c.receiver.guard.boot_id; reset=[False]
                def omit(i,a):
                    if i["event"]["type"]=="ACCEPTED" and not reset[0]:
                        port.rts=True; time.sleep(.1); port.rts=False
                        reset[0]=True
                        report.setdefault("test_injections",[]).append(dict(kind="deliberate restart after acceptance"))
                        return True
                    return False
                e.omit=omit
                result=e.execute(part(),4000)
                assert result["outcome"]=="FAULT" and "RESTART" in result["reason"],result
                assert len(result["attempts"])<=2
                sent=len(result["attempts"])
                end=time.monotonic()+1.2
                while time.monotonic()<end: c.receiver.pump(.02)
                assert len(result["attempts"])==sent
                new=Client(port,report,assign_operations=False); discovered=new.discover()
                assert discovered["boot_id"]!=old and discovered["high_water"]==0
                assert discovered["production_time_ms"]==0

            def heartbeat_loss():
                c,e=fresh(); configure(e,1,7000)
                guard=c.receiver.guard; real_observe=guard.observe
                dropped=[0]
                def suppress(event,seq=0):
                    if event.get("type")=="HEARTBEAT": dropped[0]+=1; return False
                    return real_observe(event,seq)
                guard.observe=suppress
                result=e.execute(part(),7000)
                assert result["outcome"]=="FAULT" and "HEARTBEAT_TIMEOUT" in result["reason"],result
                assert len(result["attempts"])==1
                report.setdefault("test_injections",[]).append(dict(kind="RX heartbeat suppression",count=dropped[0]))
                guard.observe=real_observe
                end=time.monotonic()+2.8
                while time.monotonic()<end: c.receiver.pump(.02)
                assert guard.available and guard.fault=="HEARTBEAT_TIMEOUT"
                try: guard.require_send()
                except SessionFault: pass
                else: raise AssertionError("heartbeat recovery resumed retrying")
                assert len(result["attempts"])==1

            def rejection():
                c,e=fresh(); configure(e,1,500)
                other=RetryController(c) # Ask firmware to identify the conflict, not the local ledger.
                result=other.execute(cfg(1,501)); verify(result,"REJECTED",1)
                assert result["reason"]=="OPERATION_CONFLICT"
                bad=other.execute(cfg(2,0)); verify(bad,"REJECTED",1)
                assert bad["reason"]=="INVALID_CONFIGURATION"

            actions=[no_loss,acceptance_loss,completion_loss,exhaustion,running_deadline,config_replay,restart,heartbeat_loss,rejection]
            for name,action in zip(PLAN,actions):
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
        write_retry_csv(report,args.csv)
    print(f"{'PASS' if report['passed'] else 'FAIL'}; port_closed={report['port_closed']}; JSON={args.log}; CSV={args.csv}")
    return 0 if report["passed"] and report["port_closed"] else 1


if __name__=="__main__": raise SystemExit(main())
