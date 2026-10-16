#!/usr/bin/env python3
"""v64 offline proof that a GP0 DMA2 capture and GP1 event log are coherent.

A self-contained *sequence-numbered, digest-chained* event journal is
independently matched against actual RAM bytes and DMA2 head order.
A digest chain detects accidental edits, but IS NOT cryptographic
authentication of a real PlayStation capture or trustworthy GP1 writes:
an author can recalculate the whole journal. No untrusted journal can
promote any retail / hardware evidence flags.

Event format is a narrow immutable producer contract, not a VHT1 trace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from .audit_map02_v61_private_capture import local_bytes,local_json
from .audit_map02_v63_gp0_gp1_state import GP1_SCHEMA,interpret_capture,GpuState
from .verify_map02_v60_ps1_dma import DmaError,manifest_check,walk_dma

SCHEMA="map02-v64-ordered-gpu-event-journal-v1"
MAX_JOURNAL_BYTES=65536
MAX_EVENTS=512
JOURNAL_KEYS={"schema","source_class","ram_sha256","initial_state","events"}
EVENT_COMMON={"seq","tick","kind","previous","digest"}
DMA_KEYS=EVENT_COMMON|{"frame","head","gp0_word_count","gp0_sha256"}
GP1_KEYS=EVENT_COMMON|{"before_frame","word"}
LOWER_HEX=set("0123456789abcdef")
ZERO_SHA="0"*64

def _hash(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def _json_bytes(obj:dict)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def _is_sha(value)->bool:
    return type(value)==str and len(value)==64 and all(c in LOWER_HEX for c in value)

def words_hash(words:list[int])->str:
    return _hash(b"".join(struct.pack("<I",x) for x in words))

def event_digest(fields:dict)->str:
    return _hash(_json_bytes(fields))

def seal_events(events:list[dict])->list[dict]:
    """For a synthetic fixture/producer. Not proof of observed hardware."""
    out=[]
    previous=ZERO_SHA
    for index,item in enumerate(events):
        event=dict(item)
        event["seq"]=index
        event["previous"]=previous
        event["digest"]=event_digest({k:v for k,v in event.items() if k!="digest"})
        previous=event["digest"]
        out.append(event)
    return out

def check_journal(ram:bytes,manifest:dict,journal:dict):
    manifest_check(ram,manifest)
    if not isinstance(journal,dict) or set(journal)!=JOURNAL_KEYS:
        raise DmaError("journal schema has missing or extra fields")
    if journal["schema"]!=SCHEMA or journal["initial_state"]!="power-on-assumed":
        raise DmaError("unrecognized journal schema or initial GPU-state assumption")
    if journal["source_class"]!=manifest["source_class"]:
        raise DmaError("journal source class disagrees with RAM manifest")
    if journal["source_class"] not in ("synthetic","user-supplied-unverified"):
        raise DmaError("journal cannot attest real retail or hardware provenance")
    if journal["ram_sha256"]!=manifest["sha256"]:
        raise DmaError("journal and RAM manifest source hashes differ")
    records=journal["events"]
    frame_heads=manifest["entry_points"]
    if not isinstance(records,list) or not len(frame_heads)<=len(records)<=min(MAX_EVENTS,2*len(frame_heads)):
        raise DmaError("journal event count violates one DMA per frame / at most one GP1 boundary")
    last_tick=-1
    previous=ZERO_SHA
    next_frame=0
    gp1_pending=None
    gp1_events=[]
    checked_dma=0
    for idx,e in enumerate(records):
        if not isinstance(e,dict):
            raise DmaError("journal entry must be an object")
        kind=e.get("kind")
        if kind=="GP0_DMA2":
            if set(e)!=DMA_KEYS:
                raise DmaError("DMA journal field set mismatch")
        elif kind=="GP1_WRITE":
            if set(e)!=GP1_KEYS:
                raise DmaError("GP1 journal field set mismatch")
        else:
            raise DmaError("unsupported journal port (only GP0_DMA2 and GP1_WRITE)")
        if (type(e["seq"])!=int or e["seq"]!=idx or
            type(e["tick"])!=int or e["tick"]<=last_tick or e["tick"]>10**15):
            raise DmaError("non-monotonic event sequence/capture tick")
        last_tick=e["tick"]
        if not _is_sha(e["previous"]) or e["previous"]!=previous or not _is_sha(e["digest"]):
            raise DmaError("event hash-chain linkage invalid")
        actual_digest=event_digest({k:v for k,v in e.items() if k!="digest"})
        if e["digest"]!=actual_digest:
            raise DmaError("event digest mismatch")
        previous=e["digest"]
        if kind=="GP1_WRITE":
            index=e["before_frame"]
            word=e["word"]
            if (type(index)!=int or index!=next_frame or
                next_frame>=len(frame_heads) or gp1_pending is not None or
                type(word)!=int or word not in (0x00000000,0x01000000)):
                raise DmaError("GP1 event must immediately precede exactly one DMA frame; GP1(00/01) only")
            gp1_pending=word
            gp1_events.append({"before_frame":index,"word":word})
            continue
        frame=e["frame"]
        head=e["head"]
        count=e["gp0_word_count"]
        if (type(frame)!=int or frame!=next_frame or type(head)!=int or
            head!=frame_heads[frame] or type(count)!=int or
            count<1 or count>65536 or not _is_sha(e["gp0_sha256"])):
            raise DmaError("journal DMA frame order / head / word count is invalid")
        words,_=walk_dma(ram,manifest["base_address"],head)
        if len(words)!=count or words_hash(words)!=e["gp0_sha256"]:
            raise DmaError("DMA journal digest does not match actual linked RAM words")
        checked_dma+=1
        next_frame+=1
        gp1_pending=None
    if next_frame!=len(frame_heads) or gp1_pending is not None:
        raise DmaError("missing or dangling DMA frame after GP1 event")
    return {"dma_events":checked_dma,"gp1_events":gp1_events,
            "journal_events":len(records),"last_hash":previous}

def audit(ram:bytes,manifest:dict,journal:dict):
    checked=check_journal(ram,manifest,journal)
    side={"schema":GP1_SCHEMA,"events":checked["gp1_events"]}
    interpreted=interpret_capture(ram,manifest,side)
    assert len(interpreted["frames"])==checked["dma_events"]
    reg_count=interpreted["registers"]
    return {
        "status":("synthetic_ordered_gpu_event_journal_consistent"
                  if manifest["source_class"]=="synthetic"
                  else "unverified_ordered_gpu_event_journal_consistent"),
        "source_class":manifest["source_class"],
        "frames":checked["dma_events"],
        "ordered_events":checked["journal_events"],
        "gp0_dma_events":checked["dma_events"],
        "gp1_full_reset_events":interpreted["gp1_reset_count"],
        "gp1_fifo_reset_events":interpreted["gp1_fifo_reset_count"],
        "gp0_register_updates":reg_count,
        "gp0_ram_payload_digest_matches":True,
        "gp0_gp1_event_order_consistent":True,
        "journal_digest_chain_consistent":True,
        "capture_tick_sequence_monotonic":True,
        "initial_gpu_state_is_assumed_not_observed":True,
        "gp1_write_proven_to_originate_from_hardware":False,
        "independent_retail_capture_authenticity_proven":False,
        "unknown_unlogged_external_gpu_events_possible":True,
        "retail_gp0_provenance_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "raw_gpu_payload_exported":False,
    }

def main():
    p=argparse.ArgumentParser(description="OFFLINE capture event consistency: not retail provenance")
    p.add_argument("--ram",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--journal",type=Path,required=True)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    try:
        data=local_bytes(args.ram,4*1024*1024)
        manifest=local_json(args.manifest,16384)
        journal=local_json(args.journal,MAX_JOURNAL_BYTES)
        result=audit(data,manifest,journal)
    except (OSError,DmaError,ValueError,TypeError,OverflowError,AssertionError) as e:
        result={"status":"refused","error_category":type(e).__name__,
                "retail_gp0_provenance_verified":False,
                "gp1_write_proven_to_originate_from_hardware":False,
                "HD_replacement_approved":False,
                "raw_gpu_payload_exported":False}
    if args.output is not None:
        if (args.output.is_symlink() or args.output.resolve() in {
            args.ram.resolve(),args.manifest.resolve(),args.journal.resolve()
        }):
            print("Refusing symlink output or overwrite of private capture input",file=__import__("sys").stderr)
            return 2
        try:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        except OSError:
            print("Unable to save sanitized report",file=__import__("sys").stderr)
            return 2
    print(json.dumps(result,sort_keys=True))
    return 1 if result["status"]=="refused" else 0

if __name__=="__main__":
    raise SystemExit(main())
