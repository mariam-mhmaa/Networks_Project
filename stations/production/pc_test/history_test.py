"""Step 5A hardware checks. Explicit duplicate probes, no automatic retries."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import serial
from production_test import Client
from two_way_test import drain_startup

PLAN = ["identifier_validation", "active_duplicate_and_conflicts", "completed_replay",
        "configuration_history", "gaps_and_rejected_progress", "eviction_and_new_work",
        "restart_limitation", "maximum_operation_number"]


def config(n, ms=500, label="cfg"):
    return dict(type="CONFIGURE_PRODUCTION",op_no=n,cmd_id=f"{label}:{n}",production_time_ms=ms)


def job(n, part=1, label="job"):
    return dict(type="PRODUCE_PART",op_no=n,job_id=f"{label}:{n}",batch_id="history-batch",part_id=part)


def ids(obj):
    return {key:obj[key] for key in ("op_no","cmd_id","job_id","batch_id","part_id") if key in obj}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True)
    parser.add_argument("--log",type=Path,default=Path("results/step5a_history.json"))
    args=parser.parse_args()
    report=dict(started_utc=datetime.now(timezone.utc).isoformat(),port=args.port,
                tx=[],rx_chunks_hex=[],events=[],timings=[],checks=[],passed=False)
    port=None
    try:
        with serial.Serial(port=None,baudrate=115200,timeout=0.01,write_timeout=0.5,
                           xonxoff=False,rtscts=False,dsrdtr=False) as port:
            port.dtr=port.rts=False; port.port=args.port; port.open()

            def reset():
                port.rts=True; time.sleep(0.1); port.rts=False
                startup,quiet=drain_startup(port)
                report.setdefault("reset_startups_hex",[]).append(startup.hex(" "))
                assert quiet
                client=Client(port,report,assign_operations=False)
                client.discover()
                return client

            c=reset()

            def events(obj,types,reason=None,timeout=2,raw=None):
                seq=c.send(obj if raw is None else None,raw=raw)
                result=c.expect(seq,types,ids(obj),reason,timeout)
                return seq,result

            def accept_config(obj):
                seq,result=events(obj,["RECEIVED","ACCEPTED","PRODUCTION_CONFIGURED"])
                assert result[-1]["event"]["production_time_ms"]==obj["production_time_ms"]
                assert result[-1]["event"]["replayed"] is False
                return seq

            def reject(obj,reason):
                # Invalid op numbers must not be echoed as validated op_no.
                seq=c.send(obj)
                identity=ids(obj)
                if type(obj.get("op_no")) is not int or not 1<=obj["op_no"]<=0xFFFFFFFF:
                    identity.pop("op_no",None)
                c.expect(seq,["RECEIVED","REJECTED"],identity,reason)

            def finish(seq,obj,accepted,ms):
                completed=c.expect(seq,["PART_PRODUCED"],ids(obj),timeout=ms/1000+1)[0]
                assert completed["event"]["replayed"] is False
                elapsed=(completed["monotonic"]-accepted["monotonic"])*1000
                report["timings"].append(dict(op_no=obj["op_no"],configured_ms=ms,elapsed_ms=elapsed))
                assert ms-100<=elapsed<=ms+500,elapsed
                assert c.next(0.15) is None,"unexpected extra completion"

            def validation():
                for bad in ("cfg", "cfg:2", "cfg:01", "cfg:001", "cfg:1x", ":1"):
                    obj=config(1); obj["cmd_id"]=bad
                    reject(obj,"INVALID_OPERATION_ID")
                obj=config(1); obj["cmd_id"]="cfg:+1"
                c.send(obj); assert c.next(0.2) is None # Invalid ID alphabet, no usable identity.
                for value in (0,-1,True,False,1.5,"1",None,4294967296,1.0):
                    obj=config(1); obj["op_no"]=value
                    reject(obj,"INVALID_OPERATION_NUMBER")
                obj=config(1); del obj["op_no"]
                reject(obj,"INVALID_OPERATION_NUMBER")
                # JSON 01 is malformed; do not trust its apparent identity.
                c.send(raw=b'{"type":"CONFIGURE_PRODUCTION","op_no":01,"cmd_id":"cfg:1","production_time_ms":500}')
                assert c.next(0.2) is None
                too_long=config(1,label="x"*47) # 49 total
                c.send(too_long); assert c.next(0.2) is None
                boundary=config(1,1200,label="x"*46) # 48 total, room for session-tagged probes
                assert len(boundary["cmd_id"])==48
                accept_config(boundary) # Rejections did not consume op 1.
                for bad in ("job", "job:2", "job:03"):
                    obj=job(3); obj["job_id"]=bad
                    reject(obj,"INVALID_OPERATION_ID")
                obj=job(3,label="x"*47)
                c.send(obj); assert c.next(0.2) is None

            active_job=job(3,label="j"*46) # exact 48-character job_id
            original_seq=None

            def active():
                nonlocal original_seq
                original_seq,result=events(active_job,["RECEIVED","ACCEPTED"])
                accepted=result[-1]
                time.sleep(0.45)
                # Same fields, different whitespace/order and new ATR sequence.
                raw=json.dumps(dict(reversed(list(dict(active_job,boot_id=c.receiver.guard.boot_id).items()))),indent=2).encode()
                query_seq,status=events(active_job,["RECEIVED","OPERATION_RUNNING"],raw=raw)
                assert query_seq!=original_seq
                changed=dict(active_job,part_id=2)
                reject(changed,"OPERATION_CONFLICT")
                changed=dict(active_job,job_id="different:3")
                reject(changed,"OPERATION_CONFLICT")
                reject(config(100),"BUSY") # Must not advance high-water to 100.
                finish(original_seq,active_job,accepted,1200)
                assert report["timings"][-1]["elapsed_ms"]<1500,"active duplicate restarted the deadline"

            def completed():
                _,result=events(active_job,["RECEIVED","PART_PRODUCED"])
                assert result[-1]["event"]["replayed"] is True
                reject(dict(active_job,batch_id="changed"),"OPERATION_CONFLICT")
                assert c.next(0.65) is None,"duplicate executed another part"
                # Same old job ID at a higher number must never execute.
                reject(dict(active_job,op_no=4),"INVALID_OPERATION_ID")

            old_cfg=config(4,1000)

            def configuration():
                accept_config(old_cfg)
                accept_config(config(5,2500))
                _,result=events(old_cfg,["RECEIVED","PRODUCTION_CONFIGURED"])
                assert result[-1]["event"]["replayed"] is True
                assert result[-1]["event"]["production_time_ms"]==1000
                reject(dict(old_cfg,production_time_ms=1001),"OPERATION_CONFLICT")
                reject(dict(old_cfg,op_no=6),"INVALID_OPERATION_ID")
                work=job(6)
                seq,result=events(work,["RECEIVED","ACCEPTED"])
                # Cached config can also replay while busy, without touching timer.
                events(old_cfg,["RECEIVED","PRODUCTION_CONFIGURED"])
                finish(seq,work,result[-1],2500) # Proves replay did not revert 2500.

            def gaps():
                accept_config(config(10,30))
                reject(config(8,30),"STALE_RESULT_UNAVAILABLE") # Gap never executed.
                reject(config(11,0),"INVALID_CONFIGURATION")
                accept_config(config(11,30)) # Rejected number can still be accepted.

            def eviction():
                for n in range(12,22):
                    accept_config(config(n,30))
                reject(active_job,"STALE_RESULT_UNAVAILABLE")
                reject(old_cfg,"STALE_RESULT_UNAVAILABLE")
                reject(dict(active_job,op_no=22),"INVALID_OPERATION_ID")
                reject(dict(old_cfg,op_no=22),"INVALID_OPERATION_ID")
                # FIFO: 14..21 retained after ten newer completions.
                reject(config(13,30),"STALE_RESULT_UNAVAILABLE")
                _,result=events(config(14,30),["RECEIVED","PRODUCTION_CONFIGURED"])
                assert result[-1]["event"]["replayed"] is True
                work=job(22)
                seq,result=events(work,["RECEIVED","ACCEPTED"])
                finish(seq,work,result[-1],30)

            def restart():
                nonlocal c
                c=reset()
                accept_config(config(1,30)) # RAM history genuinely gone.
                accept_config(old_cfg) # Exact pre-reset operation can execute again.

            def maximum():
                accept_config(config(0xFFFFFFFF,30))
                events(config(0xFFFFFFFF,30),["RECEIVED","PRODUCTION_CONFIGURED"])
                reject(config(2,30),"STALE_RESULT_UNAVAILABLE")
                reject(config(0x100000000,30),"INVALID_OPERATION_NUMBER")

            for name,action in zip(PLAN,[validation,active,completed,configuration,gaps,eviction,restart,maximum]):
                check=dict(name=name,passed=False); report["checks"].append(check)
                action(); check["passed"]=True; print(name+": PASS")
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


if __name__=="__main__":
    raise SystemExit(main())
