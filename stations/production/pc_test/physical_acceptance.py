"""Guided physical acceptance fixture; no firmware/reset or application changes.

One serial owner. Human actions use stdin; evidence is flushed at every stage.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import serial
from serial.tools import list_ports
from gateway_client import ProductionRun, RetryStopped
from retry import write_retry_csv


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM3')
    parser.add_argument('--log',type=Path,default=Path('results/physical_acceptance.json'))
    parser.add_argument('--phase',choices=('all','producing'),default='all',help='Resume remaining production cable check without repeating idle disconnect')
    args=parser.parse_args()
    report=dict(started_utc=datetime.now(timezone.utc).isoformat(),tx=[],events=[],rx_chunks_hex=[],
                checks=[],actions=[],observations=[],port=args.port,passed=False)
    port=serial.Serial(port=None,baudrate=115200,timeout=.02,write_timeout=.5,
                       xonxoff=False,rtscts=False,dsrdtr=False)
    port.dtr=port.rts=False; port.port=args.port
    run=None

    def save():
        report['port_closed']=not port.is_open
        args.log.parent.mkdir(parents=True,exist_ok=True)
        args.log.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        write_retry_csv(report,args.log.with_suffix('.csv'))

    def note(kind,**details):
        record=dict(type=kind,monotonic=time.monotonic(),utc=datetime.now(timezone.utc).isoformat(),**details)
        report['observations'].append(record); save(); print(json.dumps(record),flush=True)

    def check(name,condition,**details):
        report['checks'].append(dict(name=name,result='PASS' if condition else 'FAIL',**details))
        save()
        if not condition: raise AssertionError(name)

    def action(label):
        note('WAIT_FOR_PHYSICAL_ACTION',action=label)
        answer=input('ACTION: '+label+' [done / skip]: ').strip().lower()
        report['actions'].append(dict(action=label,answer=answer,monotonic=time.monotonic()))
        save()
        if answer not in ('done','unplugged','replugged'):
            report['checks'].append(dict(name=label,result='NOT RUN',reason='Physical action not confirmed'))
            save(); raise RuntimeError('Physical action not performed; stopped without claiming acceptance')

    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end: run.observe(.02)

    def loss(label):
        started=time.monotonic(); error=None
        try: pump(6)
        except OSError as exc: error=f'{type(exc).__name__}: {exc}'
        # Continue monotonic liveness checking even if Windows reports serial loss first.
        guard=run.client.receiver.guard
        end=time.monotonic()+6
        while guard.check() and time.monotonic()<end: time.sleep(.05)
        run.observe(0) if error is None else None
        if guard.fault: run.configured=run.started=False
        note('COMMUNICATION_LOSS',phase=label,serial_error=error,elapsed_since_observation=time.monotonic()-started,
             last_heartbeat=guard.last_heartbeat,available=guard.available,fault=guard.fault)
        check(label+'_loss',not guard.available and not run.started,serial_error=error,fault=guard.fault)
        port.close(); save()

    def reopen(label,old):
        action('Reconnect the same ESP32 USB cable for '+label)
        note('PORT_INVENTORY',ports=[dict(device=p.device,description=p.description) for p in list_ports.comports()])
        port.open()  # Same port; no reset pulse, no alternative port guessing.
        snapshot=run.read_status(3)['event']
        pump(1.2)
        note('RECONNECTED_STATUS',phase=label,old_boot_id=old,status=snapshot,
             fault=run.client.receiver.guard.fault,started=run.started,configured=run.configured)
        check(label+'_no_auto_resume',not run.started and not run.configured)
        if snapshot['boot_id']!=old:
            check(label+'_restart_fence',run.client.receiver.guard.fault=='RESTART')
            # Diagnostic old-session probe: valid unused op, but old boot. Never production.
            before=copy.deepcopy(snapshot)
            seq=run.client.send(dict(type='CONFIGURE_PRODUCTION',boot_id=old,op_no=before['high_water']+1,
                                    cmd_id=f"old-session:{before['high_water']+1}",production_time_ms=500),bind_session=False)
            end=time.monotonic()+1; rejected=None
            while time.monotonic()<end:
                item=run.client.next(.03,strict_session=False)
                if item and item['seq']==seq and item['event']['type']=='REJECTED':
                    rejected=item; break
            check(label+'_old_session_rejected',bool(rejected and rejected['event'].get('reason')=='SESSION_MISMATCH'),response=rejected)
            after=run.read_status(1)['event']
            check(label+'_probe_no_settings_or_history_change',all(after[k]==before[k] for k in
                  ('boot_id','state','production_time_ms','high_water','active_op_no')))
        else:
            check(label+'_same_session_fault_latched',bool(run.client.receiver.guard.fault))
        return snapshot

    def recover(label,part):
        status=run.connect_or_recover(); n=status['high_water']+1
        run.configure(n,f'physical-config:{n}',1000); run.start()
        result=run.produce(n+1,f'physical-job:{n+1}',f'physical-{label}',part)
        check(label+'_explicit_recovery_job',result['outcome']=='COMPLETED',operation_result=result)
        note('EXPLICIT_RECOVERY_COMPLETED',phase=label,boot_id=run.client.receiver.guard.boot_id,op_no=n+1)

    try:
        port.open()
        run=ProductionRun(port,report)
        initial=run.connect_or_recover()
        note('INITIAL_DISCOVERY',status=initial)
        check('initial_station_not_busy',initial['state']!='PRODUCING')
        if args.phase=='all':
            # Explicit configuration establishes the idle case without resetting RAM.
            n=initial['high_water']+1
            run.configure(n,f'physical-idle:{n}',1000)
            idle=run.read_status(1)['event']; check('idle_baseline',idle['state']=='IDLE')
            action('UNPLUG the ESP32 USB cable while IDLE; leave it unplugged')
            loss('idle')
            reopen('idle',idle['boot_id'])
            action('Confirm explicit recovery and a NEW short test job after the idle disconnect')
            recover('idle',1)

        status=run.read_status(1)['event']; n=status['high_water']+1
        run.configure(n,f'physical-long:{n}',60000); run.start()
        def on_response(item,attempt):
            if item['event']['type']=='ACCEPTED':
                note('LONG_JOB_ACCEPTED',response=item,duration_ms=60000)
                action('UNPLUG USB NOW during the accepted 60-second job; leave it unplugged')
            return False
        run.controller.omit=on_response
        try:
            result=run.produce(n+1,f'physical-long-job:{n+1}','physical-interrupted',2)
        except RetryStopped as exc: result=exc.result
        finally: run.controller.omit=None
        note('INTERRUPTED_OPERATION_OUTCOME',result=result)
        check('physical_action_during_production',any(a['action'].startswith('UNPLUG USB NOW') for a in report['actions']))
        check('interrupted_outcome_not_claimed_complete',result['outcome'] in ('UNRESOLVED','FAULT'))
        frozen=copy.deepcopy(run.ledger.results[(result['request']['boot_id'],n+1)])
        loss('producing')
        reconnected=reopen('producing',result['request']['boot_id'])
        before=len(report['tx'])
        retry=run.controller.execute(result['request'],60000)
        check('stopped_work_no_new_transmission_or_budget',len(report['tx'])==before and not retry['attempts'] and
              run.ledger.results[(result['request']['boot_id'],n+1)]==frozen)
        note('UNCERTAIN_PART_RETAINED',original_result=frozen,confirmed_evidence=run.operation_evidence(n+1,result['request']['boot_id']),
             actual_reconnected_status=reconnected)
        action('Confirm explicit recovery and a DIFFERENT new job; the interrupted part stays uncertain')
        recover('producing',3)
        report['passed']=True
    except (OSError,RuntimeError,ValueError,AssertionError,EOFError,KeyboardInterrupt) as exc:
        report['error']=f'{type(exc).__name__}: {exc}'
        print('STOPPED: '+report['error'],flush=True)
    finally:
        port.close(); report['finished_utc']=datetime.now(timezone.utc).isoformat(); save()
        print(f"FINISHED passed={report['passed']} port_closed={report['port_closed']}",flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
