#!/usr/bin/env python3
"""v56 independent original GPU FT4 raster coverage + shared diagonal oracle.

The REAL C DrawOTag uses original fixed-point DDA and real deferred 2x
threads. For axis-aligned polygons, Python independently specifies ALL
48x48 native and 96x96 HD halfwords, including clipping, STP/ABR and
transparent texel skips. A skewed quad is compared exactly against
separately executed ORIGINAL FillQuad, but its pixel geometry is NOT
independently proven. No original retail game assets enter this test.

The source PC-port does not implement the independent GPU destination
mask-bit checking behavior; bit15-on-background test characterizes its
ACTUAL overwrite, and is explicitly NOT hardware fidelity approval.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from .verify_map02_pixels_v48 import modulate, blend

CASES={
 "stp_abr0":(0x801f,0x4210,1,0,70,70,90,90,0,0,320,240,0),
 "stp_abr1":(0x83e0,0x2529,1,1,70,70,90,90,0,0,320,240,0),
 "stp_abr2":(0xfc00,0x5ad6,1,2,70,70,90,90,0,0,320,240,0),
 "stp_abr3":(0x801f,0x18c6,1,3,70,70,90,90,0,0,320,240,0),
 "nonstp_opaque":(0x001f,0x4210,1,1,70,70,90,90,0,0,320,240,0),
 "transparent_zero":(0x0000,0x369c,1,0,70,70,90,90,0,0,320,240,0),
 "clipped_edges":(0x83e0,0x4210,1,1,70,70,90,90,75,74,10,12,0),
 "destination_bit15":(0x03e0,0x8010,0,0,70,70,90,90,0,0,320,240,0),
 "skewed_quad":(0x801f,0x4210,1,0,70,70,90,90,0,0,320,240,1)
}
KEYS=("texel","background","semi","abr","minx","miny","maxx","maxy",
      "clipx","clipy","clipw","cliph","shape")
NAMES={"name","workers","shape","abr","semi","texel","background",
       "minx","miny","maxx","maxy","clipx","clipy","clipw","cliph",
       "nativehash","hihash","directhash","native_probe","hires_probe",
       "outside_native","outside_hires","pixels"}
RX=re.compile(r"^V56CASE (.*)$")
HALF_MASK=(1<<64)-1
FNV0=1469598103934665603
FNV1=1099511628211
class BadSeam(ValueError):pass

def parse(line):
    m=RX.fullmatch(line.strip())
    if not m:
        if line.startswith("V56"):raise BadSeam("bad original seam GPU record")
        return None
    record={}
    for segment in m.group(1).split():
        if "=" not in segment:raise BadSeam("bad C record field")
        key,val=segment.split("=",1)
        if key in record:raise BadSeam("duplicate output field")
        if key=="name":
            if val not in CASES:raise BadSeam("unknown original GPU test name")
            record[key]=val
        elif key in ("nativehash","hihash","directhash"):
            if not re.fullmatch(r"[0-9a-f]{16}",val):
                raise BadSeam("malformed original framebuffer hash")
            record[key]=val
        else:
            if not re.fullmatch(r"[0-9]+",val):raise BadSeam("bad numeric GPU field")
            record[key]=int(val)
    if set(record)!=NAMES:raise BadSeam("missing or extra C record data")
    if record["workers"] not in (1,2,4) or record["pixels"]!=96*96:
        raise BadSeam("incorrect real worker or 96x96 2x coverage size")
    expected=CASES[record["name"]]
    observed=tuple(record[x] for x in KEYS)
    if expected!=observed:raise BadSeam("synthetic original GPU source primitive modified")
    for name in ("native_probe","hires_probe","outside_native","outside_hires"):
        if not 0<=record[name]<=65535:raise BadSeam("out-of-range BGR555 pixel")
    return record

def output_pixel(spec,x,y,scale):
    raw,bg,semi,abr,left,top,right,bottom,cx,cy,cw,ch,skew=spec
    if skew:raise BadSeam("skew coverage must not be guessed from bounding box")
    covered=(left*scale<=x<right*scale and
             top*scale<=y<bottom*scale and
             cx*scale<=x<(cx+cw)*scale and
             cy*scale<=y<(cy+ch)*scale)
    if not covered or raw==0:return bg
    front=modulate(raw,128,128,128,x,y,0)
    return blend(front,bg,abr) if semi and (raw&0x8000) else front

def hash_image(spec,scale):
    h=FNV0
    for y in range(64*scale,112*scale):
        for x in range(64*scale,112*scale):
            h^=output_pixel(spec,x,y,scale)
            h=(h*FNV1)&HALF_MASK
    return f"{h:016x}"

def check(record):
    if record["hihash"]!=record["directhash"]:
        raise BadSeam("actual DrawOTag and direct original-GPU hi-res differ")
    spec=CASES[record["name"]]
    if record["outside_native"]!=spec[1] or record["outside_hires"]!=spec[1]:
        raise BadSeam("original GPU escaped the test polygon at 66,66")
    if not spec[-1]:
        expect_native=hash_image(spec,1)
        expect_hd=hash_image(spec,2)
        if (record["nativehash"],record["hihash"])!=(expect_native,expect_hd):
            raise BadSeam("full native/2x BGR555 image differs from independent half-open coverage reference")
        if record["native_probe"]!=output_pixel(spec,80,80,1):
            raise BadSeam("original native shared-triangle-diagonal pixel incorrect")
        if record["hires_probe"]!=output_pixel(spec,161,161,2):
            raise BadSeam("original 2x shared-triangle-diagonal pixel incorrect")
        return "independent_all_pixels_and_shared_diagonal"
    return "original_native_skew_and_exact_direct_deferred_only"

def audit(lines,threads):
    errors=[]
    rows={}
    categories={}
    for line in lines:
        try:
            obj=parse(line)
            if obj is None:continue
            name=obj["name"]
            if name in rows:raise BadSeam("duplicate scenario")
            if obj["workers"]!=threads:raise BadSeam("wrong actual worker label")
            rows[name]=obj
            categories[name]=check(obj)
        except (BadSeam,ValueError,KeyError) as exc:errors.append(str(exc))
    if set(rows)!=set(CASES):
        errors.append("missing/extra original FT4 seam/clip cases")
    return {
        "schema":"vh-map02-v56-original-ft4-diagonal-clip",
        "status":"original_ft4_coverage_verified" if not errors else "refused",
        "workers":threads,
        "scenario_count":len(rows),
        "independent_full_image_cases":sum(v=="independent_all_pixels_and_shared_diagonal" for v in categories.values()),
        "skew_reference_only_cases":sum(v=="original_native_skew_and_exact_direct_deferred_only" for v in categories.values()),
        "native_pixels_independently_checked":sum(v=="independent_all_pixels_and_shared_diagonal" for v in categories.values())*48*48,
        "hires_pixels_independently_checked":sum(v=="independent_all_pixels_and_shared_diagonal" for v in categories.values())*96*96,
        "mask_destination_test_implemented_in_original_PC_port":False,
        "mask_destination_test_hardware_parity_proven":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "scenarios":{name:{"nativehash":r["nativehash"],"hihash":r["hihash"],"evidence":categories[name]} for name,r in rows.items() if name in categories},
        "errors":errors[:30],
    }

def compare(logs):
    errors=[]
    if set(logs)!={1,2,4}:errors.append("need exact 1/2/4 worker logs")
    reports={key:audit(rows,key) for key,rows in logs.items()}
    for worker,report in reports.items():
        if report["status"]!="original_ft4_coverage_verified":
            errors.append(f"worker {worker}: "+str(report["errors"][:3]))
    if not errors:
        for name in CASES:
            one=reports[1]["scenarios"][name]
            for worker in (2,4):
                if reports[worker]["scenarios"][name]!=one:
                    errors.append(f"{name}: original 1 vs {worker} worker differs")
    return {
        "schema":"vh-map02-v56-original-ft4-coverage-crossworkers",
        "status":"verified" if not errors else "refused",
        "threads_checked":[1,2,4],
        "real_original_DDA_scenarios":9*3,
        "independent_native_halfword_comparisons":8*48*48*3,
        "independent_hi_res_halfword_comparisons":8*96*96*3,
        "direct_vs_deferred_hi_res_halfword_comparisons":9*96*96*3,
        "destination_mask_still_unimplemented":True,
        "HD_replacement_approved":False,
        "reports":reports,"errors":errors
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("logs",nargs=3,type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    try:
        inputs={}
        for worker,path in zip((1,2,4),args.logs):
            if path.stat().st_size>1024*1024:raise BadSeam("input log too large")
            inputs[worker]=path.read_text(encoding="utf-8").splitlines()
        result=compare(inputs)
        data=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if args.output:
            with args.output.open("x",encoding="utf-8") as f:f.write(data)
        else:print(data,end="")
        return 0 if result["status"]=="verified" else 1
    except (ValueError,OSError,UnicodeError) as exc:
        print("[v56-seams] REFUSED: "+str(exc),file=__import__("sys").stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
