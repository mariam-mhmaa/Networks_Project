"""Passive, identity-validated part evidence. Never transmits or changes run gates."""
import copy
import json
import math
from protocol import decode_atr


def uncertain_part_owner(ledger,request,key):
    if request.get("type")!="PRODUCE_PART": return None
    for owner,frozen in ledger.requests.items():
        previous=json.loads(frozen)
        if owner==key or previous.get("type")!="PRODUCE_PART": continue
        if (previous.get("batch_id"),previous.get("part_id"))!=(request.get("batch_id"),request.get("part_id")): continue
        result=ledger.results.get(owner)
        if result is None or result["outcome"] in ("UNRESOLVED","FAULT"):
            return owner
    return None


def known_part_owner(ledger,request,key):
    if request.get("type")!="PRODUCE_PART": return None
    for owner,frozen in ledger.requests.items():
        previous=json.loads(frozen)
        if owner==key or previous.get("type")!="PRODUCE_PART" or type(previous.get("part_id")) is not int: continue
        if (previous.get("batch_id"),previous.get("part_id"))!=(request.get("batch_id"),request.get("part_id")): continue
        result=ledger.results.get(owner)
        if result is None or result["outcome"]!="REJECTED": return owner
    return None


def record_part_evidence(ledger,item,guard,report,clock):
    """Revalidate ATR + semantics; retry history and session faults remain untouched."""
    def reject(reason):
        report.setdefault("evidence_rejections",[]).append(dict(reason=reason,item=copy.deepcopy(item)))
        return dict(valid=False,new_confirmation=False,reason=reason)
    try:
        tid,seq,payload=decode_atr(bytes.fromhex(item["atr_hex"]))
        event=json.loads(payload.decode("utf-8"))
        if tid!=0 or item.get("test_id")!=tid or item.get("seq")!=seq or event!=item.get("event"):
            return reject("ATR_EVENT_MISMATCH")
        if not isinstance(event,dict) or event.get("type")!="PART_PRODUCED": return reject("NOT_PART_COMPLETION")
        if type(event.get("op_no")) is not int: return reject("INVALID_OPERATION_NUMBER")
        key=(event.get("boot_id"),event["op_no"])
        if key[0]!=guard.boot_id or getattr(guard,"observed_boot_id",key[0]) not in (None,key[0]):
            return reject("OTHER_SESSION")
        frozen=ledger.requests.get(key)
        if frozen is None: return reject("UNKNOWN_OPERATION")
        request=json.loads(frozen)
        if request.get("type")!="PRODUCE_PART": return reject("WRONG_OPERATION_TYPE")
        if seq not in ledger.sequences.get(key,set()): return reject("UNKNOWN_SEQUENCE")
        for field in ("job_id","batch_id","part_id"):
            if type(event.get(field)) is not type(request.get(field)) or event.get(field)!=request.get(field):
                return reject("IDENTITY_MISMATCH")
        if type(event.get("part_id")) is not int or event["part_id"]<1 or type(event.get("replayed")) is not bool:
            return reject("INVALID_PART_RESULT")
        result=ledger.results.get(key)
        if result is None: return reject("OPERATION_STILL_IN_FLIGHT")
        if result["outcome"]=="REJECTED": return reject("REJECTED_OPERATION")
        received=item.get("monotonic")
        if type(received) not in (int,float) or not math.isfinite(received) or received<result["original_time"]:
            return reject("INVALID_RECEIVE_TIME")
        if key in ledger.part_evidence:
            return dict(valid=True,new_confirmation=False,reason="ALREADY_CONFIRMED",evidence=copy.deepcopy(ledger.part_evidence[key]))
        late=result["outcome"]!="COMPLETED"
        evidence=dict(boot_id=key[0],op_no=key[1],job_id=event["job_id"],batch_id=event["batch_id"],
                      part_id=event["part_id"],seq=seq,received_at=received,recorded_at=clock(),
                      original_retry_outcome=result["outcome"],late_after_stop=late,
                      atr_hex=item["atr_hex"],event=copy.deepcopy(event))
        ledger.part_evidence[key]=evidence
        audit=dict(type="PART_RESOLVED_LATE" if late else "PART_CONFIRMED",boot_id=key[0],op_no=key[1],
                   time=clock(),original_retry_outcome=result["outcome"],seq=seq)
        ledger.resolution_audit.append(audit)
        report.setdefault("resolution_audit",[]).append(copy.deepcopy(audit))
        report.setdefault("part_confirmations",[]).append(copy.deepcopy(evidence))
        return dict(valid=True,new_confirmation=True,evidence=copy.deepcopy(evidence))
    except (KeyError,TypeError,ValueError,UnicodeError):
        return reject("INVALID_COMPLETION_FRAME")
