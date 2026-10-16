#!/usr/bin/env python3
"""v69 private GPU plugin dispatch *callback* entry/return audit.

A successful callback RETURN is not proof that a GPU packet was decoded,
rendered, or that VRAM pixels match a real PS1. Only call pairing/order
and bounded aggregate counts are exposed. Logs contain NO GPU input
words, coordinates, VRAM or texture pixels.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .audit_map02_v61_private_capture import local_bytes,reject_duplicate_keys
from .verify_map02_v60_ps1_dma import DmaError

MAX_BYTES=1024*1024
MAX_RECORDS=8192
APIS={"writeData","writeDataMem","writeStatus","dmaChain"}

def audit(raw:bytes):
    if not isinstance(raw,bytes) or not raw or len(raw)>MAX_BYTES or not raw.endswith(b"\n"):
        raise DmaError("bounded callback log or final newline invalid")
    records=raw.split(b"\n")[:-1]
    if not 1<=len(records)<=MAX_RECORDS:
        raise DmaError("GPU callback event count invalid")
    pending=None
    bound=False
    counts={name:0 for name in sorted(APIS)}
    for index,line in enumerate(records):
        if not line or len(line)>2048:
            raise DmaError("invalid GPU callback event length")
        try:obj=json.loads(line,object_pairs_hook=reject_duplicate_keys)
        except (ValueError,UnicodeError) as e:raise DmaError("invalid JSON callback event") from e
        if (not isinstance(obj,dict) or set(obj)!={"kind","seq","api","stage"} or
            obj["kind"]!="GPU_PLUGIN_CALLBACK" or
            type(obj["seq"])!=int or obj["seq"]!=index+1):
            raise DmaError("GPU callback record schema/sequence invalid")
        api=obj["api"]; stage=obj["stage"]
        if index==0:
            if api!="bind" or stage!="complete":
                raise DmaError("first GPU callback event must bind the actual plugin")
            bound=True
            continue
        if api not in APIS or stage not in ("enter","return"):
            raise DmaError("unsupported GPU dispatch callback")
        if stage=="enter":
            if pending is not None:
                raise DmaError("overlapping GPU callback dispatch not supported")
            pending=api
        else:
            if pending!=api:
                raise DmaError("GPU plugin callback returned without matching entry")
            counts[api]+=1
            pending=None
    if pending or not bound:
        raise DmaError("incomplete GPU plugin callback or missing bind")
    return {
        "status":"unverified_gpu_plugin_dispatch_observed",
        "callback_bind_events":1,
        "plugin_callbacks_entered_and_returned":sum(counts.values()),
        "plugin_callback_counts":counts,
        "callbacks_completed_without_exception":True,
        "gpu_plugin_fifo_consumption_verified":False,
        "gpu_rendering_or_pixel_parity_verified":False,
        "real_game_boot_verified":False,
        "retail_gp0_provenance_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "raw_gpu_payload_exported":False,
    }

def main():
    p=argparse.ArgumentParser(description="Local GPU callback dispatch audit; not raster parity")
    p.add_argument("--log",type=Path,required=True)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        summary=audit(local_bytes(a.log,MAX_BYTES))
    except (DmaError,ValueError,TypeError,OSError,OverflowError) as exc:
        summary={"status":"refused","error_category":type(exc).__name__,
                 "gpu_plugin_fifo_consumption_verified":False,
                 "retail_gp0_provenance_verified":False,
                 "HD_replacement_approved":False,
                 "raw_gpu_payload_exported":False}
    if a.output is not None:
        if a.output.is_symlink() or a.output.resolve()==a.log.resolve():
            print("Refusing capture log overwrite",file=sys.stderr)
            return 2
        try:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
        except OSError:
            print("Unable to save sanitized callback report",file=sys.stderr)
            return 2
    print(json.dumps(summary,sort_keys=True))
    return 1 if summary["status"]=="refused" else 0

if __name__=="__main__":
    raise SystemExit(main())
