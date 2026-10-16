#!/usr/bin/env python3
"""v58 independent synthetic DrawOTag GP0(E6) ordered mask oracle.

Correlates the *actual* TrcPrim original OT walk (including every synthetic
mask command and textured quad) with full native/2x output computed without
calling original rasterizer code. Retail GPU packet decoding is NOT proven.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from .verify_map02_pixels_v48 import blend, modulate

E6=0xe6000000
CASES={
    "mark_skip":(0x0010,0,0,320,240,0,[(E6+1,0x001f,0),(E6+2,0x03e0,0)]),
    "reopen":(0x0010,0,0,320,240,0,[(E6+1,0x001f,0),(E6+2,0x03e0,0),
                                      (E6+0,0x7c00,0),(E6+2,0x03e0,0)]),
    "abr0":(0x0010,0,0,320,240,0,[(E6+1,0x001f,0),(E6+0,0x7c00,0),(E6+2,0x83e0,1)]),
    "abr1":(0x0010,0,0,320,240,1,[(E6+1,0x001f,0),(E6+0,0x7c00,0),(E6+2,0x83e0,1)]),
    "abr2":(0x0010,0,0,320,240,2,[(E6+1,0x001f,0),(E6+0,0x7c00,0),(E6+2,0x83e0,1)]),
    "abr3":(0x0010,0,0,320,240,3,[(E6+1,0x001f,0),(E6+0,0x7c00,0),(E6+2,0x83e0,1)]),
    "zero_texel":(0x0010,0,0,320,240,0,[(E6+1,0,1),(E6+2,0x03e0,0)]),
    "invalid_reserved":(0x0010,0,0,320,240,0,[(E6+1,0x001f,0),(E6+4,0x03e0,0)]),
    "clip_mask":(0x0010,75,74,10,12,0,[(E6+1,0x001f,0),(E6+3,0x83e0,1)]),
}
FNV0=1469598103934665603
FNV1=1099511628211
MASK=(1<<64)-1
CASE_RE=re.compile(r"^V58CASE (.*)$")
OT_RE=re.compile(r"^V58OT (.*)$")
HASH_KEYS=("nativehash","hihash","directhash")
CASE_KEYS={"name","workers","n","background","clipx","clipy","clipw",
           "cliph","abr",*HASH_KEYS,"native_probe","hires_probe",
           "outside_native","outside_hires","pixels"}

class BadOrder(ValueError): pass

def read_record(line,prefix,expected):
    m=prefix.fullmatch(line.strip())
    if not m:raise BadOrder("malformed executed GPU record")
    row={}
    for item in m.group(1).split():
        if item.count("=")!=1:raise BadOrder("malformed OT metadata")
        k,v=item.split("=",1)
        if k in row:raise BadOrder("duplicate field")
        if k in ("name","type"):
            row[k]=v
        elif k in HASH_KEYS:
            if not re.fullmatch(r"[0-9a-f]{16}",v):raise BadOrder("bad FNV64")
            row[k]=v
        else:
            if not re.fullmatch(r"[0-9]+",v):raise BadOrder("bad numeric GPU metadata")
            row[k]=int(v)
    if set(row)!=expected:raise BadOrder("missing/extra metadata")
    if row["name"] not in CASES:raise BadOrder("unknown v58 case")
    return row

def output_pixel(spec,x,y,scale):
    bg,cx,cy,cw,ch,abr,steps=spec
    if not (70*scale<=x<90*scale and 70*scale<=y<90*scale and
            cx*scale<=x<(cx+cw)*scale and cy*scale<=y<(cy+ch)*scale):
        return bg
    out=bg
    maskset=maskcheck=0
    for command,source,semi in steps:
        if (command & ~3)==E6:
            maskset=command&1
            maskcheck=(command>>1)&1
        if not source or (maskcheck and (out&0x8000)):
            continue
        front=modulate(source,128,128,128,x,y,0)
        result=blend(front,out,abr) if semi and (source&0x8000) else front
        out=(result | (0x8000 if maskset else 0))&0xffff
    return out

def hash_image(spec,scale):
    result=FNV0
    for y in range(64*scale,112*scale):
        for x in range(64*scale,112*scale):
            result=((result^output_pixel(spec,x,y,scale))*FNV1)&MASK
    return f"{result:016x}"

def audit(lines,workers):
    errors=[]
    packets={name:[] for name in CASES}
    observed={}
    for line in lines:
        if not line.strip(): continue
        try:
            if line.startswith("V58OT"):
                t=line.split(" type=")
                if len(t)!=2:raise BadOrder("invalid OT type")
                kind=t[1].split()[0]
                keys=({"name","index","type","command"} if kind=="mask"
                      else {"name","index","type","uv","semi","abr"})
                p=read_record(line,OT_RE,keys)
                if p["type"] not in ("mask","quad"):raise BadOrder("unexpected OT type")
                packets[p["name"]].append(p)
            elif line.startswith("V58CASE"):
                p=read_record(line,CASE_RE,CASE_KEYS)
                if p["name"] in observed:raise BadOrder("duplicate final framebuffer case")
                observed[p["name"]]=p
            else:
                raise BadOrder("unrecognized stdout from original GPU")
        except BadOrder as exc:
            errors.append(str(exc))
    for name,spec in CASES.items():
        bg,cx,cy,cw,ch,abr,steps=spec
        record=observed.get(name)
        expected_packets=[]
        for i,(command,source,semi) in enumerate(steps):
            expected_packets.append({
                "name":name,"index":2*i,"type":"mask","command":command
            })
            expected_packets.append({
                "name":name,"index":2*i+1,"type":"quad",
                "uv":20+i,"semi":semi,"abr":abr
            })
        if packets[name]!=expected_packets:
            errors.append(f"{name} original TrcPrim mask/FT4 ordering differed")
        if record is None:
            errors.append(f"{name} missing real C framebuffer")
            continue
        exact={
            "workers":workers,"n":len(steps),"background":bg,
            "clipx":cx,"clipy":cy,"clipw":cw,"cliph":ch,"abr":abr,
            "nativehash":hash_image(spec,1),"hihash":hash_image(spec,2),
            "directhash":hash_image(spec,2),
            "native_probe":output_pixel(spec,80,80,1),
            "hires_probe":output_pixel(spec,161,161,2),
            "outside_native":bg,"outside_hires":bg,"pixels":96*96
        }
        for key,value in exact.items():
            if record[key]!=value:
                errors.append(f"{name} {key}: actual={record[key]} expected={value}")
    if len(observed)!=len(CASES):errors.append("incorrect original C scene count")
    return {
        "status":"refused" if errors else "ordered_gp0_e6_gpu_verified",
        "errors":errors[:30],
        "workers":workers,
        "real_ordered_ot_scenes":len(observed),
        "real_traced_state_packets":sum(len(v)//2 for v in packets.values()),
        "independent_native_halfwords":len(CASES)*48*48,
        "independent_hd_halfwords":len(CASES)*96*96,
        "direct_deferred_halfwords":len(CASES)*96*96,
        "retail_gp0_dma_packet_decoding_proven":False,
        "HD_replacement_approved":False
    }

def compare(logs):
    reports={w:audit(lines,w) for w,lines in logs.items()}
    errors=[]
    if set(reports)!={1,2,4}:errors.append("missing real worker configurations")
    for w,report in reports.items():
        if report["status"]!="ordered_gp0_e6_gpu_verified":
            errors.append(f"worker={w} {report['errors'][:3]}")
    if not errors:
        parsed={w:{read_record(l,CASE_RE,CASE_KEYS)["name"]:
                   read_record(l,CASE_RE,CASE_KEYS)
                   for l in logs[w] if l.startswith("V58CASE")} for w in (1,2,4)}
        for name in CASES:
            for key in HASH_KEYS+("native_probe","hires_probe"):
                if len({parsed[w][name][key] for w in (1,2,4)})!=1:
                    errors.append(f"{name} cross-worker {key} differs")
    valid=not errors
    return {
        "status":"verified" if valid else "refused","errors":errors,
        "threads_checked":sorted(reports),"reports":{str(w):rep for w,rep in reports.items()},
        "real_executed_gpu_scenarios":len(CASES)*3 if valid else 0,
        "independent_native_halfwords":len(CASES)*48*48*3 if valid else 0,
        "independent_hd_halfwords":len(CASES)*96*96*3 if valid else 0,
        "direct_deferred_halfwords":len(CASES)*96*96*3 if valid else 0,
        "retail_gp0_dma_packet_decoding_proven":False,
        "HD_replacement_approved":False
    }

def main():
    ap=argparse.ArgumentParser()
    for s in ("worker1","worker2","worker4"):ap.add_argument(s,type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    report=compare({w:p.read_text().splitlines()
        for w,p in zip((1,2,4),(args.worker1,args.worker2,args.worker4))})
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
    return 0 if report["status"]=="verified" else 1

if __name__=="__main__":
    raise SystemExit(main())
