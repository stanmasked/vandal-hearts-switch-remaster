#!/usr/bin/env python3
"""V53 independent original DrawOTag mixed primitive compositor oracle.

Tests original real OT walk with mixed TILE, FT4, DR_MODE, SPRT, F4;
the oracle independently computes ordered BGR555 pixels. All C
inputs are deliberately SYNTHETIC; no original MAP02.PRS is used.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from .verify_map02_pixels_v48 import pack,modulate,blend

RX=re.compile(r"^V53 (.*)$")
VAL=re.compile(r"([a-z0-9_]+)=([0-9a-f]+)")
HASH=re.compile(r"^[0-9a-f]{16}$")
EXPECTED={"scene","workers","primitive_count","native","hires","direct",
          "othash","directhash","pixels","clut4","clut8",
          "sprite_tpage","sprite_mask","sprite_offset"}
S_SEQ=((0,1,2,3,4,5,6,7),(0,1,7,3,4,5,6,2))
class BadOT(ValueError):pass

def parse(line):
    m=RX.fullmatch(line.strip())
    if not m:
        if line.startswith("V53"):raise BadOT("malformed v53 original OT trace")
        return None
    d={}
    for word in m.group(1).split():
        v=VAL.fullmatch(word)
        if not v:raise BadOT("invalid field "+word[:80])
        k,val=v.groups()
        if k in d:raise BadOT("duplicate field "+k)
        if k in ("othash","directhash"):
            if not HASH.fullmatch(val):raise BadOT("bad hi-res framebuffer fingerprint")
            d[k]=val
        else:
            if not val.isdigit():raise BadOT("non-decimal integer")
            d[k]=int(val)
    if set(d)!=EXPECTED:raise BadOT("unexpected or missing actual OT fields")
    if d["scene"] not in (0,1) or d["workers"] not in (1,2,4) or d["primitive_count"]!=72:
        raise BadOT("invalid original OT scene/worker/primitive count")
    if any(d[x]!=value for x,value in (("pixels",10240),("clut4",31978),
         ("clut8",31914),("sprite_tpage",422),("sprite_mask",1),("sprite_offset",1))):
        raise BadOT("invalid original GP0 texture/state/CLUT metadata")
    if any(not 0<=d[k]<65536 for k in ("native","hires","direct")):
        raise BadOT("invalid BGR555 framebuffer halfword")
    return d

def composition(scene,x,y):
    if scene not in (0,1):raise BadOT("unrecognized synthetic scene")
    color=0
    for id in S_SEQ[scene]:
        if id==0: # DR_MODE texture state, no pixel operation
            continue
        if id==1: # TILE (no semi)
            color=pack(40,64,88)
        elif id==2: # 4bpp TEX4, raw CLUT1 red, STP clear
            color=modulate(0x001f,128,128,128,x,y,0)
        elif id==3: # DR_MODE enables sprite 8bpp + window (x/y mask and offset 1)
            continue
        elif id==4: # 8bpp SPRT with effective (u,v)=(40,56), palette1 STP green
            front=modulate(0x83e0,128,128,128,x,y,0)
            color=blend(front,color,1)
        elif id==5: # DR_MODE sets untextured ABR3 and clears texture window
            continue
        elif id==6: # F4 semi, 8-bit RGB (128,0,128) 5-bit ABR3
            color=blend(pack(128,0,128),color,3) & 0x7fff
        elif id==7: # 15bpp TEX15 STP red, ABR2 subtraction
            front=modulate(0x801f,128,128,128,x,y,0)
            color=blend(front,color,2)
        else:
            raise BadOT("invalid primitive")
    return color

def audit_worker(lines,worker):
    rows={}
    errors=[]
    for line in lines:
        try:
            d=parse(line)
            if d is None:continue
            if d["scene"] in rows:raise BadOT("duplicate original OT scene")
            rows[d["scene"]]=d
        except BadOT as exc:errors.append(str(exc))
    if set(rows)!={0,1}:errors.append("missing one or both OT draw order scenes")
    for scene,record in rows.items():
        if record["workers"]!=worker:errors.append("worker count not independently confirmed")
        predicted_native=composition(scene,88,88)
        predicted_hd=composition(scene,177,176)
        if record["native"]!=predicted_native:
            errors.append(f"scene{scene}: original OT native BGR555 != independent order oracle")
        if record["hires"]!=predicted_hd or record["direct"]!=predicted_hd:
            errors.append(f"scene{scene}: real deferred/direct 2x result != oracle")
        if record["othash"]!=record["directhash"]:
            errors.append(f"scene{scene}: complete 32x320 FT4/sprite/F4/TILE OT region differs")
    if rows.get(0) and rows.get(1) and rows[0]["native"]==rows[1]["native"]:
        errors.append("OT packet order reordering has no measurable effect")
    return {"schema":"vh-map02-v53-actual-mixed-original-ot",
            "status":"mixed_real_ot_verified" if not errors else "refused",
            "all_inputs_synthetic":True,"retail_map_authenticity_proven":False,
            "genuine_gameplay_proven":False,"HD_replacement_approved":False,
            "threads":worker,"scene_count":len(rows),"ordered_packet_count_per_scene":72,
            "full_hi_res_pixel_comparisons_per_scene":10240,
            "prim_types":["DR_MODE","TILE","POLY_FT4","SPRT","POLY_F4"],
            "scenes":{str(x):{"native":d["native"],"hd":d["hires"],"hash":d["othash"]}
                      for x,d in rows.items()},
            "errors":errors}

def compare_threads(logs):
    errors=[]
    if set(logs)!={1,2,4}:errors.append("missing/extra worker setting")
    reports={n:audit_worker(lines,n) for n,lines in logs.items()}
    for n,r in reports.items():
        if r["status"]!="mixed_real_ot_verified":errors.append(f"worker{n} failed: "+str(r["errors"][:4]))
    if not errors:
        for scene in ("0","1"):
            baseline=reports[1]["scenes"][scene]
            for n in (2,4):
                if baseline!=reports[n]["scenes"][scene]:
                    errors.append(f"scene{scene} original DrawOTag differs between 1 and {n} threads")
    return {"schema":"vh-map02-v53-real-ot-cross-thread",
            "status":"verified" if not errors else "refused",
            "threads_checked":[1,2,4],
            "original_ot_scenes":2,
            "whole_H_D_pixel_comparisons_per_compiler":2*3*10240,
            "HD_replacement_approved":False,"reports":reports,"errors":errors}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("logs",nargs=3,type=Path,help="corresponding 1/2/4 thread executions")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        logs={}
        for n,path in zip((1,2,4),a.logs):
            if path.stat().st_size>1024*1024:raise BadOT("excessive GPU log")
            logs[n]=path.read_text(encoding="utf-8").splitlines()
        result=compare_threads(logs)
        data=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as f:f.write(data)
        else:sys.stdout.write(data)
        return 0 if result["status"]=="verified" else 1
    except (OSError,UnicodeError,ValueError) as exc:
        print("[v53-ot] REFUSED: "+str(exc),file=sys.stderr)
        return 1
if __name__=="__main__":raise SystemExit(main())
