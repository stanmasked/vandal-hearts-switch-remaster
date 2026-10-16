#!/usr/bin/env python3
"""Independent BGR555 pixel decision audit for *executed* original GPU DDA.

The v48 log captures values on either side of the ORIGINAL PutPixel call.
This tool computes original accurate PS1 front-color dithering, semi-transparent
5-bit blends, opaque writes and transparent skips independently in Python.
No pixels are substituted, and real retail map authenticity is not inferred.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path
import re
import sys

from .preflight_map02_prs_v45 import inspect_file, read_prs, unpack_bounded, load_v24
from .verify_map02_faces_v47 import verify as verify_faces, _read_lines

MARK = re.compile(r"\[v48-terrain-pixel\]\s+(.*)$")
FIELD = re.compile(r"([a-z]+)=(-?\d+)")
FIELDS = {"f","token","gfx","route","target","x","y","u","v","raw",
          "draw","front","before","after","semi","abr","dither",
          "mr","mg","mb","scale"}
DITHER = ((-4,0,-3,1),(2,-2,3,-1),(-3,1,-4,0),(3,-1,2,-2))
ERROR_CAP = 50

class BadPixelTrace(ValueError):
    pass


def parse(line):
    m=MARK.search(line)
    if not m:
        return None
    d={}
    for token in m.group(1).split():
        hit=FIELD.fullmatch(token)
        if hit is None: raise BadPixelTrace("invalid pixel trace field "+token[:80])
        k,v=hit.group(1),int(hit.group(2))
        if k in d: raise BadPixelTrace("duplicate pixel trace field "+k)
        d[k]=v
    if set(d)!=FIELDS:
        raise BadPixelTrace("bad pixel fields missing="+str(sorted(FIELDS-set(d)))+
                            " extra="+str(sorted(set(d)-FIELDS)))
    if (not 1<=d["f"]<=0xffffffff or not 1<=d["token"]<65536
            or not 1<=d["gfx"]<870 or d["route"] not in (1,2,3)
            or d["target"] not in (0,1) or d["draw"] not in (0,1)
            or d["semi"] not in (0,1) or d["dither"] not in (0,1)
            or d["abr"] not in (0,1,2,3)
            or d["scale"] not in (1,2,3,4)
            or (d["target"]==0 and d["scale"]!=1)
            or (d["target"]==1 and d["scale"]<=1)
            or not 0 <=d["x"]<1024*d["scale"] or not 0<=d["y"]<512*d["scale"]
            or not 0<=d["u"]<=255 or not 0<=d["v"]<=255
            or any(not 0<=d[k]<=65535 for k in ("raw","front","before","after"))
            or any(not 0<=d[k]<=255 for k in ("mr","mg","mb"))):
        raise BadPixelTrace("out-of-range v48 pixel record")
    return d


def pack(r,g,b):
    def component(x):
        return min(255,max(0,x))>>3
    return (component(b)<<10)|(component(g)<<5)|component(r)


def modulate(raw,mr,mg,mb,x,y,dither):
    components=(((raw>>0)&31)*8,((raw>>5)&31)*8,((raw>>10)&31)*8)
    rgb=[(components[i]*c)//128 for i,c in enumerate((mr,mg,mb))]
    if dither:
        offset=DITHER[y&3][x&3]
        rgb=[c+offset for c in rgb]
    return pack(*rgb)


def blend(fg,bg,abr):
    """Exact unsigned PS1 5-bit G1 packed BGR555 blend on 16-bit inputs."""
    fg=(fg|0x8000)&0xffff
    bg=bg&0xffff
    if abr==0:
        bg|=0x8000
        color=(fg+bg-((fg^bg)&0x0421))>>1
    elif abr==1:
        bg &= ~0x8000
        summ=fg+bg
        carry=(summ-((fg^bg)&0x8421))&0x8420
        color=(summ-carry)|(carry-(carry>>5))
    elif abr==2:
        bg |= 0x8000
        fg &= ~0x8000
        diff=bg-fg+0x108420
        borrow=(diff-((bg^fg)&0x108420))&0x108420
        color=(diff-borrow)&(borrow-(borrow>>5))
    else:
        bg &= ~0x8000
        fg=((fg>>2)&0x1ce7)|0x8000
        summ=fg+bg
        carry=(summ-((fg^bg)&0x8421))&0x8420
        color=(summ-carry)|(carry-(carry>>5))
    return color&0xffff


def verify_pixel(p):
    raw=p["raw"]
    if p["draw"] != (raw!=0):
        raise BadPixelTrace("draw decision not equal to nonzero raw texel")
    if raw==0:
        if p["front"]!=0 or p["after"]!=p["before"]:
            raise BadPixelTrace("transparent texel must leave framebuffer intact")
        return "transparent_skip"
    front=modulate(raw,p["mr"],p["mg"],p["mb"],
                   p["x"],p["y"],p["dither"])
    if p["front"]!=front:
        raise BadPixelTrace("dither/modulated front BGR555 disagrees with independent reference")
    effective_semi=bool(p["semi"] and (raw&0x8000))
    expected=blend(front,p["before"],p["abr"]) if effective_semi else front
    if p["after"] != expected:
        raise BadPixelTrace("pixel output disagrees with independent PS1 STP/ABR blend")
    return "stp_blend_"+str(p["abr"]) if effective_semi else "opaque"


def audit(lines,decoded,slots,source_sha=None):
    owner=verify_faces(decoded,slots,lines,synthetic=True,source_sha=source_sha)
    if owner["status"]=="refused":
        raise BadPixelTrace("upstream v47 terrain provenance refused: "+
                            str(owner["errors"][:4]))
    tagged=set()
    pairs={}
    for line in lines:
        if "[v47-terrain-face-ot]" in line:
            m=re.search(r"\bf=(\d+) token=(\d+)",line)
            if m: tagged.add((int(m.group(1)),int(m.group(2))))
    for p in (parse(line) for line in lines):
        if p is None: continue
        pairs.setdefault((p["f"],p["token"]),[]).append(p)
    errors=[]
    counts=Counter()
    native=hires=0
    observed=set()
    for key,samples in sorted(pairs.items()):
        if key not in tagged:
            errors.append(f"v48 pixel not attributed to tagged terrain OT {key}")
            continue
        for p in samples:
            try:
                kind=verify_pixel(p)
            except BadPixelTrace as exc:
                if len(errors)<ERROR_CAP:
                    errors.append(f"f={p['f']} token={p['token']} x={p['x']} y={p['y']}: {exc}")
                continue
            counts[kind]+=1
            observed.add(key)
            if p["target"]: hires+=1
            else: native+=1
    state=("refused" if errors else
           "pixel_decisions_correlated" if native and hires and owner["matched_face_count"] else
           "insufficient_sparse_evidence")
    return {
        "schema":"vh-map02-original-gpu-pixel-proof-v48",
        "status":state,
        "retail_map_authenticity_proven":False,
        "genuine_gameplay_proven":False,
        "pixel_perfect_visual_fidelity_proven":False,
        "full_map_coverage_proven":False,
        "HD_replacement_approved":False,
        "source_sha256":source_sha,
        "matched_source_face_count":owner["matched_face_count"],
        "per_token_pixel_observed_count":len(observed),
        "native_pixel_observations":native,
        "hires_pixel_observations":hires,
        "pixel_decisions":dict(counts),
        "abr_modes_observed":sorted(int(k[-1]) for k in counts if k.startswith("stp_blend_")),
        "errors":errors,
        "note":"Original GPU pixel snapshots on synthetic resources only. Sparse native/hires coordinates are different pixels; do not compare their colors directly.",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("prs",type=Path)
    p.add_argument("gpu_log",type=Path)
    p.add_argument("--v24",type=Path,default=Path(__file__).resolve().parents[1]/
                   "tests/fixtures/vh_map02_hd_lookup_v24.h")
    p.add_argument("--synthetic-fixture",action="store_true")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        pre=inspect_file(a.prs,a.v24,synthetic=a.synthetic_fixture)
        payload,_,_=read_prs(a.prs)
        report=audit(_read_lines(a.gpu_log),unpack_bounded(payload),load_v24(a.v24),pre["sha256_input"])
        txt=json.dumps(report,sort_keys=True,indent=2)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as fp: fp.write(txt)
        else:
            sys.stdout.write(txt)
        return {"pixel_decisions_correlated":0,"refused":1,"insufficient_sparse_evidence":2}[report["status"]]
    except (OSError,UnicodeError,ValueError) as exc:
        print("[v48-pixel-proof] REFUSED: "+str(exc),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
