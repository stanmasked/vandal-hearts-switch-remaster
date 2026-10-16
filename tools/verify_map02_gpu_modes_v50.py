#!/usr/bin/env python3
"""v50 independent oracle for ACTUALLY EXECUTED original FillQuad/DDA.

Synthetic fixtures deliberately include 4/8/15-bit PS1 textures, CLUT,
texture-window, opaque, zero texel, STP and four ABR decisions. Unlike a
mock of the native GPU, the observations are actual post-FillQuad VRAM.
"""
from __future__ import annotations
from collections import Counter
import argparse
import json
from pathlib import Path
import re
import sys

from .verify_map02_vram_v49 import independent_sample, BadSource
from .verify_map02_pixels_v48 import modulate,blend

RX=re.compile(r"^V50 (.*)$")
PAIR=re.compile(r"([a-z]+)=(-?\d+|[a-z][a-z0-9_]*)")
REQ={"name","depth","tpage","clut","u","v","maskx","masky","offx","offy",
     "tx","ty","word","index","palx","paly","palette","raw",
     "before","after","semi","abr","dither","x","y"}
EXPECTED={
 "indexed4_opaque","indexed4_zero","indexed4_no_stp",
 "indexed4_abr0","indexed4_abr1","indexed4_abr2","indexed4_abr3",
 "indexed4_stp_black","indexed4_dither",
 "indexed8_lo","indexed8_hi","indexed8_stp",
 "direct15_opaque","direct15_stp","direct15_zero",
 "window_mask_xy","window_offset_xy","window_8bit"
}
class V50Bad(ValueError):pass


def parse(line):
    match=RX.match(line.strip())
    if not match:return None
    d={}
    for token in match.group(1).split():
        m=PAIR.fullmatch(token)
        if not m:raise V50Bad("bad native DDA token: "+token)
        k,v=m.groups()
        if k in d:raise V50Bad("duplicate native token field "+k)
        d[k]=v if k=="name" else int(v)
    if set(d)!=REQ:raise V50Bad("missing/extra native fields")
    if d["name"] not in EXPECTED:raise V50Bad("unexpected native GPU case")
    if not 0<=d["depth"]<=2 or not 0<=d["semi"]<=1 or not 0<=d["dither"]<=1 or not 0<=d["abr"]<4:
        raise V50Bad("invalid primitive state")
    if any(not 0<=d[k]<=65535 for k in ("word","palette","raw","before","after")):
        raise V50Bad("invalid 16-bit GPU halfword")
    return d


def reference(p):
    # Validate the C test's own fixture addresses and packed texture/CLUT,
    # independently of the CPU rasterizer, using v49's separate oracle.
    metadata=dict(p)
    metadata["maskx"]=p["maskx"]
    metadata["masky"]=p["masky"]
    metadata["palx"]=p["palx"]
    metadata["paly"]=p["paly"]
    try:
        kind=independent_sample(metadata)
    except BadSource as exc:
        raise V50Bad("source VRAM or CLUT mismatch: "+str(exc)) from exc
    expected_kind=("indexed4","indexed8","direct15")[p["depth"]]
    if kind!=expected_kind:raise V50Bad("texture depth disagrees with native source type")
    raw=p["raw"]
    if raw==0:
        expected=p["before"]
        decision="transparent_skip"
    else:
        front=modulate(raw,128,128,128,p["x"],p["y"],p["dither"])
        if p["semi"] and raw&0x8000:
            expected=blend(front,p["before"],p["abr"])
            decision="stp_abr"+str(p["abr"])
        else:
            expected=front
            decision="opaque"
    if p["after"]!=expected:
        raise V50Bad(f"{p['name']}: ORIGINAL native FillQuad wrote {p['after']} "
                     f"instead of expected {expected}, {decision}")
    return kind,decision


def audit(lines):
    names=set()
    counts=Counter()
    errors=[]
    observations=[]
    for line in lines:
        try:
            p=parse(line)
            if p is None:continue
            if p["name"] in names:
                raise V50Bad("repeated native DDA case "+p["name"])
            names.add(p["name"])
            kind,decision=reference(p)
            counts[kind]+=1;counts[decision]+=1
            observations.append({"case":p["name"],"format":kind,"decision":decision,
                                 "raw":p["raw"],"before":p["before"],"after":p["after"]})
        except (V50Bad,KeyError,TypeError) as exc:
            errors.append(str(exc))
    if names!=EXPECTED:
        errors.append("missing mode cases: "+", ".join(sorted(EXPECTED-names)))
    if set(counts).isdisjoint({"stp_abr0","stp_abr1","stp_abr2","stp_abr3"}):
        errors.append("no original ABR cases were executed")
    for mode in range(4):
        if counts.get("stp_abr"+str(mode),0)<1:
            errors.append("missing actual ABR mode "+str(mode))
    for item in ("indexed4","indexed8","direct15","transparent_skip","opaque"):
        if not counts.get(item,0):errors.append("missing actual GPU path "+item)
    return {
        "schema":"vh-map02-v50-real-original-gpu-dda-modes",
        "status":"original_dda_modes_verified" if not errors else "refused",
        "all_test_data_synthetic":True,
        "genuine_gameplay_proven":False,
        "full_map_visual_fidelity_proven":False,
        "HD_replacement_approved":False,
        "executed_original_dda_cases":len(observations),
        "texture_formats":{"indexed4":counts["indexed4"],"indexed8":counts["indexed8"],
                           "direct15":counts["direct15"]},
        "transparent_skips":counts["transparent_skip"],
        "opaque_decisions":counts["opaque"],
        "stp_abr_modes":{str(i):counts["stp_abr"+str(i)] for i in range(4)},
        "cases":observations,
        "errors":errors,
        "note":"Original compiled DDA executed FillQuad with synthetic VRAM; independent Python reference validates actual post-framebuffer pixels."
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("log",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        if a.log.stat().st_size>1024*1024:raise V50Bad("excessive native GPU fixture output")
        r=audit(a.log.read_text(encoding="utf-8").splitlines())
        output=json.dumps(r,indent=2,sort_keys=True)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as f:f.write(output)
        else:sys.stdout.write(output)
        return 0 if r["status"]=="original_dda_modes_verified" else 1
    except (OSError,UnicodeError,V50Bad) as exc:
        print("[v50-gpu] REFUSED: "+str(exc),file=sys.stderr)
        return 1

if __name__=="__main__":raise SystemExit(main())
