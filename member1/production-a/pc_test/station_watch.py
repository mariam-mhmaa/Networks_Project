"""Read-only station observation; never configure, produce or resubmit work."""
import argparse
import json
import time
import serial
from protocol import encode_atr,slip_encode
from receiver import Receiver
from session import SessionGuard,SessionFault


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True)
    parser.add_argument("--seconds",type=float,default=30)
    args=parser.parse_args()
    guard=SessionGuard(); report={}; port=None; receiver=None
    end=time.monotonic()+args.seconds; previous=None
    try:
        while time.monotonic()<end:
            try:
                if port is None:
                    port=serial.Serial(port=None,baudrate=115200,timeout=0.02,write_timeout=0.5,
                                       xonxoff=False,rtscts=False,dsrdtr=False)
                    port.dtr=port.rts=False; port.port=args.port; port.open()
                    receiver=Receiver(port,report,guard)
                    receiver.expected_status.add(0xFFFFFFFE)
                    # Read-only discovery on connection; no work is retried.
                    wire=slip_encode(encode_atr(0,0xFFFFFFFE,b'{"type":"GET_STATUS"}'))
                    sent=0; deadline=time.monotonic()+1
                    while sent<len(wire):
                        if time.monotonic()>deadline: raise RuntimeError("discovery write timeout")
                        sent+=port.write(wire[sent:])
                receiver.pump(0.02)
                while receiver.pending:
                    item=receiver.pending.pop(0)
                    if item["test_id"]==0 and item["event"].get("type")=="STATUS" and guard.boot_id is None:
                        guard.bind(item["event"])
            except (serial.SerialException,OSError):
                if port is not None: port.close()
                port=None; receiver=None
                time.sleep(0.05)
            guard.check()
            state=(guard.available,guard.fault,guard.boot_id,guard.observed_boot_id)
            if state!=previous:
                print(json.dumps(dict(available=state[0],fault=state[1],intended_boot_id=state[2],
                                      observed_boot_id=state[3],work_resumed=False)))
                previous=state
    except KeyboardInterrupt: pass
    finally:
        if port is not None: port.close()
    print("Observation ended; port closed; no production commands sent")


if __name__=="__main__": main()
