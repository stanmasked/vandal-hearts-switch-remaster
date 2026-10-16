#!/usr/bin/env python3
"""Independent exhaustive v57 GP0(E6) BGR555 oracle, synthetic only.

Real ORIGINAL PC-port C executes DrawOTag/FillQuad/DDA/PutPixel for each
1/2/4 worker configuration. Python never calls its rasterizer: it calculates
every 48x48 native and 96x96 hi-res halfword, including mask writes/skips,
transparent texels, STP/ABR and half-open clipping. This does not validate
retail screenshots, unhandled GP0 packets, or HD texture replacement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from .verify_map02_pixels_v48 import modulate, blend

CASES = {
    "default_overwrite": (0x03e0,0x8010,0,0,0,0,0,0,320,240,0),
    "masked_preserved":  (0x03e0,0x8010,0,1,0,0,0,0,320,240,0),
    "unmasked_allowed":  (0x03e0,0x0010,0,1,0,0,0,0,320,240,0),
    "force_opaque":      (0x03e0,0x0010,1,0,0,0,0,0,320,240,0),
    "force_and_check":   (0x03e0,0x0010,1,1,0,0,0,0,320,240,0),
    "masked_force_skip": (0x03e0,0x8010,1,1,0,0,0,0,320,240,0),
    "zero_texel_force":  (0x0000,0x0010,1,0,1,0,0,0,320,240,0),
    "masked_stp_skip":   (0x801f,0x9210,0,1,1,0,0,0,320,240,0),
    "stp_abr0":          (0x801f,0x4210,1,0,1,0,0,0,320,240,0),
    "stp_abr1":          (0x83e0,0x2529,1,0,1,1,0,0,320,240,0),
    "stp_abr2":          (0xfc00,0x5ad6,1,0,1,2,0,0,320,240,0),
    "stp_abr3":          (0x801f,0x18c6,1,0,1,3,0,0,320,240,0),
    "nonstp_opaque":     (0x001f,0x4210,1,0,1,1,0,0,320,240,0),
    "mask_clip":         (0x83e0,0x0010,1,1,1,1,75,74,10,12,0),
    "mask_transition":   (0x001f,0x0010,1,0,0,0,0,0,320,240,1),
}
SPEC_KEYS = ("texel","background","maskset","maskcheck","semi","abr",
             "clipx","clipy","clipw","cliph","two")
NUM_KEYS = ("workers",)+SPEC_KEYS+("native_probe","hires_probe",
    "outside_native","outside_hires","pixels")
HASH_KEYS = ("nativehash","hihash","directhash")
ALL_KEYS = {"name",*NUM_KEYS,*HASH_KEYS}
LINE = re.compile(r"^V57CASE (.*)$")
FNV0=1469598103934665603
FNV1=1099511628211
M64=(1<<64)-1

class BadMask(ValueError):
    pass

def parse(line: str):
    m=LINE.fullmatch(line.strip())
    if m is None:
        raise BadMask("missing real original GPU V57CASE record")
    row={}
    for part in m.group(1).split():
        if part.count("=")!=1:raise BadMask("malformed field")
        key,value=part.split("=",1)
        if key in row:raise BadMask("duplicate field")
        if key=="name":
            if value not in CASES:raise BadMask("unknown GPU case")
            row[key]=value
        elif key in HASH_KEYS:
            if not re.fullmatch(r"[a-f0-9]{16}",value):
                raise BadMask("invalid 64-bit original C hash")
            row[key]=value
        elif key in NUM_KEYS:
            if not re.fullmatch(r"[0-9]+",value):raise BadMask("non-numeric GPU field")
            row[key]=int(value)
        else:raise BadMask("unexpected C field")
    if set(row)!=ALL_KEYS:raise BadMask("missing/extra original GPU metadata")
    if tuple(row[key] for key in SPEC_KEYS)!=CASES[row["name"]]:
        raise BadMask("original GPU mask/texture/clip source modified")
    if row["workers"] not in (1,2,4) or row["pixels"]!=96*96:
        raise BadMask("incorrect worker count or framebuffer coverage")
    for key in ("native_probe","hires_probe","outside_native","outside_hires"):
        if not 0<=row[key]<=65535:raise BadMask("bad BGR555 pixel")
    return row

def output_pixel(spec: tuple[int,...], x: int,y: int,scale: int) -> int:
    raw,bg,setbit,checkbit,semi,abr,cx,cy,cw,ch,two=spec
    inside=(70*scale<=x<90*scale and 70*scale<=y<90*scale
            and cx*scale<=x<(cx+cw)*scale
            and cy*scale<=y<(cy+ch)*scale)
    dest=bg
    if not inside:return dest
    steps=[(raw,setbit,checkbit,semi)]
    if two:steps.append((0x03e0,0,1,0))
    for source,force,check,semi_flag in steps:
        if source==0 or (check and (dest&0x8000)):continue
        front=modulate(source,128,128,128,x,y,0)
        result=blend(front,dest,abr) if semi_flag and (source&0x8000) else front
        dest=(result | (0x8000 if force else 0))&0xffff
    return dest

def hash_image(spec,scale):
    h=FNV0
    for y in range(64*scale,112*scale):
        for x in range(64*scale,112*scale):
            h=((h^output_pixel(spec,x,y,scale))*FNV1)&M64
    return f"{h:016x}"

def audit(lines,worker):
    problems=[]
    seen={}
    count=0
    for line in lines:
        if not line.strip():continue
        count+=1
        try:
            record=parse(line)
            name=record["name"]
            if name in seen:raise BadMask("duplicate real C case")
            if record["workers"]!=worker:raise BadMask("worker label mismatch")
            spec=CASES[name]
            expectations={
                "nativehash":hash_image(spec,1),
                "hihash":hash_image(spec,2),
                "directhash":hash_image(spec,2),
                "native_probe":output_pixel(spec,80,80,1),
                "hires_probe":output_pixel(spec,161,161,2),
                "outside_native":spec[1],
                "outside_hires":spec[1],
            }
            for key,value in expectations.items():
                if record[key]!=value:
                    raise BadMask(f"{name} {key} actual {record[key]} expected {value}")
            seen[name]=record
        except BadMask as exc:
            problems.append(str(exc))
    missing=set(CASES)-set(seen)
    if missing:problems.append("missing executed GPU cases: "+", ".join(sorted(missing)))
    if count!=len(CASES):problems.append("incorrect original C case count")
    return {
        "status":"refused" if problems else "original_gp0_e6_mask_verified",
        "errors":problems,
        "workers":worker,
        "real_original_gpu_cases":len(seen),
        "independent_native_halfword_comparisons":len(seen)*48*48,
        "independent_hd_halfword_comparisons":len(seen)*96*96,
        "direct_deferred_halfword_comparisons":len(seen)*96*96,
        "mask_test_implemented_in_disposable_original_PC_port":not problems,
        "GP0_E6_retail_command_integration_proven":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
    }

def compare(logs:dict[int,list[str]]):
    errors=[]
    if set(logs)!={1,2,4}:errors.append("all three worker traces required")
    reports={worker:audit(lines,worker) for worker,lines in logs.items()}
    for worker,rep in reports.items():
        if rep["status"]!="original_gp0_e6_mask_verified":
            errors.append(f"worker {worker}: {rep['errors'][:3]}")
    if not errors:
        parsed={w:{r["name"]:r for r in map(parse,logs[w]) if r} for w in (1,2,4)}
        for name in CASES:
            for key in HASH_KEYS+("native_probe","hires_probe"):
                observed={parsed[w][name][key] for w in (1,2,4)}
                if len(observed)!=1:errors.append(f"cross-worker {name} {key} drift")
    return {
        "status":"refused" if errors else "verified",
        "errors":errors,
        "threads_checked":sorted(reports),
        "reports":{str(k):v for k,v in reports.items()},
        "real_original_gpu_scenarios":len(CASES)*3 if not errors else 0,
        "independent_native_halfword_comparisons":len(CASES)*48*48*3 if not errors else 0,
        "independent_hd_halfword_comparisons":len(CASES)*96*96*3 if not errors else 0,
        "direct_deferred_halfword_comparisons":len(CASES)*96*96*3 if not errors else 0,
        "GP0_E6_retail_command_integration_proven":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("worker1",type=Path)
    p.add_argument("worker2",type=Path)
    p.add_argument("worker4",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    result=compare({i:path.read_text().splitlines()
        for i,path in zip((1,2,4),(args.worker1,args.worker2,args.worker4))})
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"]=="verified" else 1

if __name__=="__main__":
    raise SystemExit(main())
