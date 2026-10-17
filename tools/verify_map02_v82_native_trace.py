#!/usr/bin/env python3
"""Strict independent reader for private v82 *synthetic emulator* event trace.

Never treat DMA2 start addresses as decoded GP0 words or frame pixels.
"""
import argparse
import json
from pathlib import Path

KINDS={"vblank","gp1_mmio","gpu_dma2_start","gp0_unai_handled","unai_sample_delta","unai_store_count","unai_same_store_count"}
FIELDS={"kind","seq","value","cycle","frame"}

class Refused(ValueError):pass

def validate(content: bytes):
    if not content or len(content)>524288 or not content.endswith(b"\n"):
        raise Refused("size or newline framing")
    try:
        strings=content.decode("ascii").splitlines()
    except UnicodeError as e:
        raise Refused("non-ASCII payload") from e
    edges=[]
    gp1=0
    prev_seq=0
    prev_kind=None
    prev_value=None
    result=[]
    for index,line in enumerate(strings,1):
        try:
            item=json.loads(line,parse_constant=lambda _: (_ for _ in ()).throw(Refused("nonfinite")))
        except (ValueError,TypeError) as e:
            raise Refused(f"invalid JSON at record {index}") from e
        if not isinstance(item,dict) or set(item)!=FIELDS or item.get("kind") not in KINDS:
            raise Refused(f"bad schema {index}")
        if any(type(item[k]) is not int or not 0<=item[k]<=0xffffffff for k in FIELDS-{"kind"}):
            raise Refused(f"bad number {index}")
        if item["seq"]!=prev_seq+1:raise Refused(f"sequence gap at {index}")
        prev_seq=item["seq"]
        if item["kind"]=="vblank":
            if item["value"]!=0:raise Refused("VBlank payload nonzero")
            if edges and (item["frame"]!=edges[-1]["frame"]+1 or
                          item["cycle"]<=edges[-1]["cycle"]):
                raise Refused("nonconsecutive VBlank frame/cycle")
            edges.append(item)
        else:
            if item["frame"]!=0:raise Refused("GPU submission asserted frame identity")
            if item["kind"]=="unai_store_count" and (prev_kind!="unai_sample_delta" or
                item["value"]==0xffffffff or item["cycle"]!=0):
                raise Refused("bad actual Unai 16-bit store count")
            if item["kind"]=="unai_same_store_count" and (prev_kind!="unai_store_count" or
                item["value"]>prev_value or item["cycle"]!=0):
                raise Refused("impossible same-value native pixel-store count")
            if item["kind"]=="gp1_mmio":gp1+=1
            if item["kind"]=="unai_sample_delta":
                if prev_kind!="gp0_unai_handled" or item["cycle"]!=0 or item["value"]>24:
                    raise Refused("invalid paired Unai sample comparison")
            if item["kind"]=="gp0_unai_handled" and item["cycle"]!=0:
                raise Refused("renderer GPU handler has no observed CPU cycle")
            if item["kind"]=="gp0_unai_handled" and not (
                (item["value"]>>24)==2
                or 0x20 <= (item["value"]>>24) <= 0x43
                or 0x48 <= (item["value"]>>24) <= 0x53
                or 0x58 <= (item["value"]>>24) <= 0x6b
                or 0x70 <= (item["value"]>>24) <= 0x7f
                or 0xe1 <= (item["value"]>>24) <= 0xe6):
                raise Refused("unrecognized renderer-handled opcode")
            if item["kind"]=="gpu_dma2_start" and item["value"]>0x1fffff:
                raise Refused("DMA2 start outside PSX RAM")
        result.append(item)
        prev_kind=item["kind"]
        prev_value=item["value"]
    if len(edges)!=4 or gp1<2:raise Refused("missing VBlank or GP1 evidence")
    if result[0]["kind"]=="vblank" and result[0]["frame"]==0:
        # Frame zero is permissible; avoid conflating with unknown GP1 frames.
        pass
    return {"classification":"emulator_observed_synthetic_input_only",
            "events":len(result),"vblank_edges":len(edges),"gp1_mmio":gp1,
            "gpu_dma2_start":sum(e["kind"]=="gpu_dma2_start" for e in result),
            "gp0_unai_handled":sum(e["kind"]=="gp0_unai_handled" for e in result),
            "unai_sample_delta":sum(e["kind"]=="unai_sample_delta" for e in result),
            "sampled_pixels_changed":sum(e["value"] for e in result if e["kind"]=="unai_sample_delta"),
            "unai_store_count_events":sum(e["kind"]=="unai_store_count" for e in result),
            "unai_same_store_count_events":sum(e["kind"]=="unai_same_store_count" for e in result),
            "bytes":len(content),"original_retail_MAP02_verified":False,
            "HD_replacement_approved":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_file",type=Path)
    p.add_argument("--expected-events",type=int)
    p.add_argument("--expected-bytes",type=int)
    a=p.parse_args()
    try:
        raw=a.private_file.read_bytes()
        result=validate(raw)
        if a.expected_events is not None and result["events"]!=a.expected_events:
            raise Refused("reported event count differs from stored trace")
        if a.expected_bytes is not None and result["bytes"]!=a.expected_bytes:
            raise Refused("reported byte count differs from stored trace")
    except (OSError,Refused) as exc:p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":main()
