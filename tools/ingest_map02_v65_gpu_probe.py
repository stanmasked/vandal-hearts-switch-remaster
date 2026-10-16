#!/usr/bin/env python3
"""v65 local-only consumer for GPU instrumentation observations.

Input is newline-delimited JSON, emitted by a cooperating emulator's
DMA2-submit and GP1-register-write hooks. Event order and the actual GP0
word stream MUST be observed separately and compared byte-for-byte
against a captured DMA RAM image; no trusting addresses or hashes alone.

The reference C probe demonstrates the hook interface on synthetic data,
NOT integration with a real retail PS1 emulator or physical console.
Self-authored probe lines remain UNVERIFIED even if their digests match.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .audit_map02_v61_private_capture import local_bytes,local_json,reject_duplicate_keys
from .audit_map02_v64_event_journal import (
    SCHEMA as V64_SCHEMA,audit as audit_v64,seal_events,words_hash
)
from .verify_map02_v60_ps1_dma import DmaError,manifest_check,walk_dma

SCHEMA="map02-v65-local-gpu-probe-jsonl-v1"
MAX_LOG_BYTES=8*1024*1024
MAX_EVENTS=512
MAX_TOTAL_WORDS=1048576
MAX_WORDS_PER_SUBMISSION=65536
HEADER_KEYS={"kind","schema","source_class","clock","initial_state"}
DMA_KEYS={"kind","tick","frame","head","words"}
GP1_KEYS={"kind","tick","before_frame","word"}

def parse_observations(raw:bytes):
    if not isinstance(raw,bytes) or not raw or len(raw)>MAX_LOG_BYTES:
        raise DmaError("probe log missing or exceeds bounded maximum")
    if not raw.endswith(b"\n"):
        raise DmaError("probe JSONL capture lacks final newline")
    records=[]
    for line in raw.split(b"\n")[:-1]:
        if not line or len(line)>1024*1024:
            raise DmaError("probe record empty or too large")
        try:
            r=json.loads(line.decode("utf-8"),object_pairs_hook=reject_duplicate_keys)
        except (ValueError,UnicodeError) as e:
            raise DmaError("malformed or duplicate-key probe JSON record") from e
        if not isinstance(r,dict):
            raise DmaError("probe record must be an object")
        records.append(r)
        if len(records)>MAX_EVENTS+1:
            raise DmaError("too many probe events")
    if not records:
        raise DmaError("probe capture has no header")
    header=records.pop(0)
    if set(header)!=HEADER_KEYS or header["kind"]!="CAPTURE_BEGIN" or header["schema"]!=SCHEMA:
        raise DmaError("probe header contract mismatch")
    if (header["source_class"] not in ("synthetic","user-supplied-unverified")
        or header["clock"]!="producer-monotonic-counter"
        or header["initial_state"]!="power-on-assumed"):
        raise DmaError("unsupported capture source or clock assumptions")
    return header,records

def translate(ram:bytes,manifest:dict,raw_probe:bytes):
    manifest_check(ram,manifest)
    header,observed=parse_observations(raw_probe)
    if header["source_class"]!=manifest["source_class"]:
        raise DmaError("probe source class disagrees with separately captured RAM")
    count=len(manifest["entry_points"])
    if not count<=len(observed)<=2*count:
        raise DmaError("probe events require exactly one DMA2 submission per frame")
    next_frame=0
    gp1_pending=False
    tick=-1
    total=0
    journal_events=[]
    gp1_count=0
    for event in observed:
        kind=event.get("kind")
        if kind=="GP1_WRITE":
            if set(event)!=GP1_KEYS:
                raise DmaError("GP1 observation has unexpected fields")
        elif kind=="GP0_DMA2":
            if set(event)!=DMA_KEYS:
                raise DmaError("GP0 DMA observation has unexpected fields")
        else:
            raise DmaError("unsupported GPU observation kind; never guess port")
        timestamp=event["tick"]
        if type(timestamp)!=int or timestamp<=tick or timestamp>10**15:
            raise DmaError("probe producer clock is not strictly increasing")
        tick=timestamp
        if kind=="GP1_WRITE":
            frame=event["before_frame"]
            word=event["word"]
            if (type(frame)!=int or frame!=next_frame or frame>=count
                    or gp1_pending or type(word)!=int
                    or word not in (0x00000000,0x01000000)):
                raise DmaError("GP1 reset write not adjacent to expected DMA frame")
            gp1_pending=True
            gp1_count+=1
            journal_events.append({"kind":"GP1_WRITE","tick":tick,
                                   "before_frame":frame,"word":word})
            continue
        frame=event["frame"]
        head=event["head"]
        words=event["words"]
        if (type(frame)!=int or frame!=next_frame or
            type(head)!=int or head!=manifest["entry_points"][frame]):
            raise DmaError("DMA submit head/frame order does not match raw RAM capture")
        if (not isinstance(words,list) or not 1<=len(words)<=MAX_WORDS_PER_SUBMISSION
                or any(type(w)!=int or not 0<=w<=0xffffffff for w in words)):
            raise DmaError("DMA GP0 observed words are invalid or over limit")
        total+=len(words)
        if total>MAX_TOTAL_WORDS:
            raise DmaError("too many observed GP0 payload words")
        original,_=walk_dma(ram,manifest["base_address"],head)
        if words!=original:
            raise DmaError("independent DMA probe words differ from captured RAM linked list")
        journal_events.append({
            "kind":"GP0_DMA2","tick":tick,"frame":frame,"head":head,
            "gp0_word_count":len(words),"gp0_sha256":words_hash(words)
        })
        next_frame+=1
        gp1_pending=False
    if next_frame!=count or gp1_pending:
        raise DmaError("incomplete capture frame or dangling GP1 write")
    journal={
        "schema":V64_SCHEMA,"source_class":header["source_class"],
        "ram_sha256":manifest["sha256"],
        "initial_state":"power-on-assumed",
        "events":seal_events(journal_events)
    }
    return journal,{"captured_dma_submissions":next_frame,
                    "captured_gp1_reset_writes":gp1_count,
                    "observed_gp0_words":total}

def audit(ram:bytes,manifest:dict,raw_probe:bytes):
    journal,meta=translate(ram,manifest,raw_probe)
    base=audit_v64(ram,manifest,journal)
    return {
        "status":("synthetic_probe_adapter_consistency_verified"
                  if manifest["source_class"]=="synthetic"
                  else "unverified_emulator_probe_consistency_verified"),
        "source_class":manifest["source_class"],
        "probe_protocol":SCHEMA,
        "frames":base["frames"],
        "ordered_events":base["ordered_events"],
        "gp0_dma_submissions":meta["captured_dma_submissions"],
        "gp1_write_events":meta["captured_gp1_reset_writes"],
        "observed_gp0_words":meta["observed_gp0_words"],
        "gp0_dma_ram_word_for_word_equal":True,
        "gp0_gp1_relative_order_consistent":True,
        "ordered_journal_cross_audit_succeeded":True,
        "capture_log_integrity_not_authenticity":True,
        "producer_instrumentation_actually_installed":False,
        "independent_capture_provenance_verified":False,
        "gp1_write_proven_to_originate_from_hardware":False,
        "original_retail_MAP02_verified":False,
        "retail_gp0_provenance_verified":False,
        "HD_replacement_approved":False,
        "raw_gpu_payload_exported":False
    }

def main():
    p=argparse.ArgumentParser(description="Offline local GPU probe log/PS1 RAM cross-check")
    p.add_argument("--ram",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--probe",type=Path,required=True)
    p.add_argument("--output",type=Path)
    p.add_argument("--private-journal-out",type=Path,
                   help="Opt-in PRIVATE v64 journal containing RAM heads and GP1 words")
    args=p.parse_args()
    sources={args.ram.resolve(),args.manifest.resolve(),args.probe.resolve()}
    destinations=[x for x in (args.output,args.private_journal_out) if x is not None]
    if (any(x.is_symlink() or x.resolve() in sources for x in destinations)
        or len({x.resolve() for x in destinations})!=len(destinations)):
        print("Refusing symlink output or overwrite of private source",file=sys.stderr)
        return 2
    journal=None
    try:
        ram=local_bytes(args.ram,4*1024*1024)
        manifest=local_json(args.manifest,16384)
        observations=local_bytes(args.probe,MAX_LOG_BYTES)
        result=audit(ram,manifest,observations)
        if args.private_journal_out is not None:
            journal,_=translate(ram,manifest,observations)
    except (DmaError,ValueError,OverflowError,TypeError,OSError) as e:
        result={"status":"refused","error_category":type(e).__name__,
                "producer_instrumentation_actually_installed":False,
                "gp1_write_proven_to_originate_from_hardware":False,
                "retail_gp0_provenance_verified":False,
                "HD_replacement_approved":False,
                "raw_gpu_payload_exported":False}
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        except OSError:
            print("Unable to write sanitized report",file=sys.stderr)
            return 2
    if journal is not None:
        try:
            args.private_journal_out.parent.mkdir(parents=True,exist_ok=True)
            # Opt-in private DMA heads: never overwrite and create mode 0600.
            fd=os.open(args.private_journal_out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as out:
                out.write(json.dumps(journal,sort_keys=True,indent=2)+"\n")
        except OSError:
            print("Unable to write private event journal",file=sys.stderr)
            return 2
    print(json.dumps(result,sort_keys=True))
    return 1 if result["status"]=="refused" else 0

if __name__=="__main__":
    raise SystemExit(main())
