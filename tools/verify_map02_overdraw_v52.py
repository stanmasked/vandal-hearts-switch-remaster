#!/usr/bin/env python3
"""v52 independent oracle for ORIGINAL multi-layer PS1 GPU drawing order.

Cross-checks five immutable synthetic scene manifests, live recorded packed
VRAM/CLUT metadata, every layer's source and (native, direct-2x, deferred-2x)
composited framebuffer halfwords. Validates 1/2/4 worker output identities
and full 32x32 hashes. Never substitutes pixels or authenticates retail art.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

from .verify_map02_pixels_v48 import modulate, blend
from .verify_map02_vram_v49 import independent_sample, BadSource

SCENES = {
 "mixed_stp":(0x4210,False,[
    (0,0x001f,0,0,0,0,0,0,0,208,192),
    (1,0x83e0,1,0,0,0,0,0,0,210,192),
    (2,0xfc00,1,1,0,0,0,0,0,210,192),
    (0,0x0000,1,2,0,0,0,0,0,220,192),
    (2,0x801f,1,2,0,0,0,0,0,212,192)]),
 "mixed_reversed":(0x4210,True,[
    (0,0x001f,0,0,0,0,0,0,0,208,192),
    (1,0x83e0,1,0,0,0,0,0,0,210,192),
    (2,0xfc00,1,1,0,0,0,0,0,210,192),
    (0,0x0000,1,2,0,0,0,0,0,220,192),
    (2,0x801f,1,2,0,0,0,0,0,212,192)]),
 "abr_chain":(0x294a,False,[
    (2,0x7c00,0,0,0,0,0,0,0,208,192),
    (0,0x801f,1,0,0,0,0,0,0,212,192),
    (1,0x83e0,1,1,0,0,0,0,0,212,192),
    (2,0xfc00,1,2,0,0,0,0,0,211,192),
    (0,0x8210,1,3,0,0,0,0,0,224,192)]),
 "window_interleave":(0x3ad5,False,[
    (0,0x4210,0,0,0,1,1,0,0,216,200),
    (1,0x0000,1,1,0,0,0,0,0,210,192),
    (2,0x83e0,1,0,0,1,1,1,1,210,192),
    (0,0x801f,1,3,0,0,0,0,0,220,192),
    (1,0x7c00,1,2,0,0,0,0,0,216,192)]),
 "dither_overdraw":(0x1ce7,False,[
    (0,0x4210,0,0,1,0,0,0,0,208,192),
    (1,0x83e0,1,0,1,0,0,0,0,210,192),
    (2,0x801f,1,3,1,0,0,0,0,210,192),
    (1,0x0000,1,1,1,0,0,0,0,214,192),
    (0,0xfc00,1,2,1,0,0,0,0,224,192)])
}
META_KEYS=("depth","raw","semi","abr","dither","maskx","masky","offx","offy","u","v")
LAYER_REQ={"scene","seq","source","depth","tpage","clut","u","v",
           "maskx","masky","offx","offy","tx","ty","word","index",
           "palx","paly","palette","raw","semi","abr","dither"}
BOUND_REQ={"scene","y","native","direct","deferred"}
BAND_Y=(55,60,119,120,179,180,190)
RESULT_REQ={"scene","layers","reverse","workers","background","native",
            "direct","deferred","x","y","hx","hy","directhash","deferredhash","pixels"}
RX=re.compile(r"^V52(L|RESULT|BOUND) (.*)$")
NAME_RX=re.compile(r"^([a-z0-9_]+)$")
HASH_RX=re.compile(r"^[0-9a-f]{16}$")
MAX_LOG=1024*1024
class BadLayerEvidence(ValueError):pass


def parse(line):
    m=RX.fullmatch(line.strip())
    if not m:
        if line.startswith("V52"):raise BadLayerEvidence("malformed original GPU output record")
        return None
    kind=m.group(1)
    out={}
    for field in m.group(2).split():
        if "=" not in field:raise BadLayerEvidence("bad field")
        key,value=field.split("=",1)
        if key in out:raise BadLayerEvidence("duplicate original field "+key)
        if key=="scene":
            if not NAME_RX.fullmatch(value):raise BadLayerEvidence("invalid scene")
            out[key]=value
        elif key in ("directhash","deferredhash"):
            if not HASH_RX.fullmatch(value):raise BadLayerEvidence("invalid hash")
            out[key]=value
        else:
            try:out[key]=int(value)
            except ValueError as exc:raise BadLayerEvidence("not an integer "+key) from exc
    if set(out)!=(LAYER_REQ if kind=="L" else BOUND_REQ if kind=="BOUND" else RESULT_REQ):
        raise BadLayerEvidence("unexpected or missing original GPU fields")
    if out["scene"] not in SCENES:
        raise BadLayerEvidence("unknown scene")
    return kind,out


def draw_layer(bg,raw,semi,abr,dither,x,y):
    if raw==0:return bg
    front=modulate(raw,128,128,128,x,y,dither)
    return blend(front,bg,abr) if semi and raw&0x8000 else front


def expected_sample(scene,x,y):
    background,reverse,base=SCENES[scene]
    color=background
    steps=list(reversed(base)) if reverse else base
    for layer in steps:
        color=draw_layer(color,layer[1],layer[2],layer[3],layer[4],x,y)
    return color


def source_provenance(p,expected_source):
    depth,raw,semi,abr,dither,mx,my,ox,oy,u,v=expected_source
    assert_fields={"depth":depth,"raw":raw,"semi":semi,"abr":abr,"dither":dither,
                   "maskx":mx,"masky":my,"offx":ox,"offy":oy,"u":u,"v":v,
                   "tpage":5+(depth<<7),"clut":31978}
    for name,value in assert_fields.items():
        if p[name]!=value:
            raise BadLayerEvidence(f"{p['scene']} seq{p['seq']} {name} changed")
    expected_index=-1 if depth==2 else p["source"]+1 if depth==0 else p["source"]+32
    if p["index"]!=expected_index:
        raise BadLayerEvidence("source packed texel index does not correspond to fixture")
    expected_word=raw if depth==2 else expected_index*0x1111 if depth==0 else expected_index*0x0101
    if p["word"]!=expected_word:
        raise BadLayerEvidence("packed texture memory word modified")
    try:format_name=independent_sample(p)
    except BadSource as exc:raise BadLayerEvidence("source VRAM/CLUT address contradiction: "+str(exc)) from exc
    if format_name!=("indexed4","indexed8","direct15")[depth]:
        raise BadLayerEvidence("wrong source texture format")
    return format_name


def audit(lines,thread_label=None):
    results={}
    layers=defaultdict(dict)
    bounds=defaultdict(dict)
    errors=[]
    for line in lines:
        try:
            entry=parse(line)
            if entry is None:continue
            kind,p=entry
            name=p["scene"]
            if kind=="BOUND":
                if p["y"] in bounds[name]:
                    raise BadLayerEvidence("duplicate GPU band boundary sample")
                bounds[name][p["y"]]=p
            elif kind=="L":
                if p["seq"] in layers[name]:
                    raise BadLayerEvidence("duplicate layer sequence")
                layers[name][p["seq"]]=p
            else:
                if name in results:raise BadLayerEvidence("duplicate rendered scene")
                results[name]=p
        except BadLayerEvidence as exc:
            errors.append(str(exc))
    if set(results)!=set(SCENES):
        errors.append("missing or extra rendered scene")
    if set(layers)!=set(SCENES):
        errors.append("missing source-layer records")
    if set(bounds)!=set(SCENES):
        errors.append("missing high-resolution GPU band boundary samples")
    samples={}
    counts=defaultdict(int)
    for name,(background,reverse,original) in SCENES.items():
        actual=results.get(name)
        if actual is None:continue
        if (actual["layers"],actual["reverse"],actual["background"])!=(len(original),int(reverse),background):
            errors.append(name+": wrong scene layering/background metadata")
        if actual["pixels"]!=10240:
            errors.append(name+": original C did not compare all 10240 hi-res band-crossing pixels")
        if set(bounds.get(name,{}))!=set(BAND_Y):
            errors.append(name+": missing, extra, or wrong worker band boundary samples")
        else:
            for boundary_y,pixel in sorted(bounds[name].items()):
                expected_native=expected_sample(name,88,boundary_y)
                expected_hd=expected_sample(name,177,boundary_y*2)
                if pixel["native"]!=expected_native:
                    errors.append(name+": native border y="+str(boundary_y)+" differs from BGR555 oracle")
                if pixel["direct"]!=expected_hd or pixel["deferred"]!=expected_hd:
                    errors.append(name+": original HD border y="+str(boundary_y)+" disagrees with oracle")
        if thread_label is not None and actual["workers"]!=thread_label:
            errors.append(name+": subprocess worker count differs from request")
        if actual["workers"] not in (1,2,4):
            errors.append(name+": unsupported worker count")
        if (actual["x"],actual["y"],actual["hx"],actual["hy"])!=(88,88,177,176):
            errors.append(name+": wrong original raster pixel positions")
        layer_rows=layers.get(name,{})
        if set(layer_rows)!=set(range(len(original))):
            errors.append(name+": incomplete or duplicate ordered source layers")
        else:
            order=tuple(reversed(range(len(original)))) if reverse else tuple(range(len(original)))
            for n,idx in enumerate(order):
                try:
                    row=layer_rows[n]
                    if row["source"]!=idx:
                        raise BadLayerEvidence(name+": wrong OT/synthetic display-list order")
                    fmt=source_provenance(row,original[idx])
                    counts[fmt]+=1
                    if original[idx][1]==0:counts["transparent"]+=1
                    elif original[idx][2] and original[idx][1]&0x8000:
                        counts["abr"+str(original[idx][3])]+=1
                except BadLayerEvidence as exc:errors.append(str(exc))
        for key,pixelx,pixely in (("native",88,88),("direct",177,176),("deferred",177,176)):
            expected=expected_sample(name,pixelx,pixely)
            if actual[key]!=expected:
                errors.append(f"{name}/{key} original GPU {actual[key]} != independent layered BGR555 {expected}")
        if actual["direct"]!=actual["deferred"] or actual["directhash"]!=actual["deferredhash"]:
            errors.append(name+": hi-res direct/deferred framebuffer mismatch")
        samples[name]={"native":actual["native"],
                       "hires":actual["direct"],
                       "band_probes":{str(y):{"native":bounds[name][y]["native"],
                                              "hires":bounds[name][y]["direct"]}
                                      for y in BAND_Y if y in bounds[name]},
                       "full_hd_32x32_hash":actual["directhash"]}
    if "mixed_stp" in samples and "mixed_reversed" in samples:
        if samples["mixed_stp"]["native"]==samples["mixed_reversed"]["native"]:
            errors.append("original draw order unexpectedly had no measurable effect")
    if counts["transparent"]<3 or any(counts["abr"+str(i)]==0 for i in range(4)):
        errors.append("missing actual original transparent or ABR layers")
    return {
        "schema":"vh-map02-v52-layered-original-gpu",
        "status":"verified_synthetic_layered_GPU" if not errors else "refused",
        "synthetic_only":True,
        "original_map_gameplay_proven":False,
        "HD_replacement_approved":False,
        "scene_count":len(samples),
        "layer_count_per_scene":5,
        "actual_gpu_layer_submissions":sum(len(x) for x in layers.values()),
        "whole_hires_pixels_per_scene":10240,
        "worker_band_boundaries_checked":[60,120,180],
        "cross_band_probes_per_scene":len(BAND_Y),
        "worker_count":thread_label,
        "source_formats":{k:counts[k] for k in ("indexed4","indexed8","direct15")},
        "stp_abr_cases":{str(i):counts["abr"+str(i)] for i in range(4)},
        "transparent_layer_count":counts["transparent"],
        "order_sensitive_pair_different":(
           samples.get("mixed_stp",{}).get("native")!=samples.get("mixed_reversed",{}).get("native")
        ),
        "scenes":samples,
        "errors":errors[:45],
    }


def cross_worker(reports):
    errors=[]
    if set(reports)!={1,2,4}:
        errors.append("need exactly 1,2,4 worker reports")
    else:
        for worker,report in reports.items():
            if report["status"]!="verified_synthetic_layered_GPU" or report["worker_count"]!=worker:
                errors.append("failed worker report "+str(worker))
        if not errors:
            for name in SCENES:
                orig=reports[1]["scenes"][name]
                for worker in (2,4):
                    current=reports[worker]["scenes"][name]
                    if current!=orig:
                        errors.append(f"{name} inconsistent 1 vs {worker} worker pixels or complete-region hash")
    return {"schema":"vh-map02-v52-multithread-reproducibility",
            "status":"verified" if not errors else "refused",
            "workers_checked":[1,2,4],
            "scene_count":len(SCENES),
            "full_hd_pixels_checked_per_run":10240*len(SCENES),
            "HD_replacement_approved":False,
            "errors":errors}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs",nargs=3,type=Path,help="exactly 1, 2 and 4 worker full logs in that order")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    try:
        outputs={}
        for worker,path in zip((1,2,4),args.logs):
            if path.stat().st_size>MAX_LOG:raise BadLayerEvidence("input oversized")
            outputs[worker]=audit(path.read_text(encoding="utf-8").splitlines(),worker)
        result=cross_worker(outputs)
        result["individual_reports"]=outputs
        payload=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if args.output:
            with args.output.open("x",encoding="utf-8") as f:f.write(payload)
        else:
            sys.stdout.write(payload)
        return 0 if result["status"]=="verified" else 1
    except (OSError,UnicodeError,ValueError) as exc:
        print("[v52-layered-gpu] REFUSED: "+str(exc),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
