#!/usr/bin/env python3
"""V49 fail-closed proof for VRAM source word, CLUT lookup and GP0 texture window.

The C trace records raw memory halfwords BEFORE original PutPixel. The
Python validator independently derives addressing, texel subword index and
palette selection and compares with the original SampleTexture output.
These samples establish internal consistency, not a cryptographically
independent dump of source VRAM nor the authenticity of game textures.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from .preflight_map02_prs_v45 import inspect_file,read_prs,unpack_bounded,load_v24
from .verify_map02_faces_v47 import _read_lines
from .verify_map02_pixels_v48 import audit as audit_v48, parse as parse_v48

RX=re.compile(r"\[v49-terrain-vram\]\s+(.*)$")
ONE=re.compile(r"([a-z]+)=(-?\d+)")
FIELDS={"f","token","gfx","route","target","x","y","u","v","tpage",
        "clut","maskx","masky","offx","offy",
        "tx","ty","palx","paly","word","index","palette","raw"}


class BadSource(ValueError):
    pass


def parse(line):
    m=RX.search(line)
    if m is None:return None
    d={}
    for pair in m.group(1).split():
        p=ONE.fullmatch(pair)
        if not p:raise BadSource("invalid source field "+pair[:100])
        key,v=p.group(1),int(p.group(2))
        if key in d:raise BadSource("duplicate source field "+key)
        d[key]=v
    if set(d)!=FIELDS:
        raise BadSource("source field set mismatch")
    if not(1<=d["f"]<=0xffffffff and 1<=d["token"]<65536 and
           1<=d["gfx"]<870 and d["route"] in (1,2,3) and
           d["target"] in (0,1) and 0<=d["x"]<4096 and 0<=d["y"]<2048 and
           0<=d["u"]<=255 and 0<=d["v"]<=255 and
           0<=d["tpage"]<=65535 and 0<=d["clut"]<=65535 and
           all(0<=d[k]<=31 for k in ("maskx","masky","offx","offy")) and
           0<=d["tx"]<1024 and 0<=d["ty"]<512 and
           -1<=d["palx"]<1024 and -1<=d["paly"]<512 and
           -1<=d["index"]<=255 and
           all(0<=d[k]<=65535 for k in ("word","palette","raw"))):
        raise BadSource("out-of-bounds source VRAM/CLUT record")
    return d


def independent_sample(p):
    tp=(p["tpage"]>>7)&3
    ppw=4 if tp==0 else 2 if tp==1 else 1
    u=(p["u"] & ~(p["maskx"]*8)) | ((p["offx"]&p["maskx"])*8)
    v=(p["v"] & ~(p["masky"]*8)) | ((p["offy"]&p["masky"])*8)
    tx=(p["tpage"]&15)*64+u//ppw
    ty=((p["tpage"]>>4)&1)*256+v
    if not 0<=tx<1024 or not 0<=ty<512:
        raise BadSource("computed source VRAM address outside framebuffer")
    if (p["tx"],p["ty"])!=(tx,ty):
        raise BadSource("source texture word VRAM address mismatch")
    if tp==0:
        ix=(p["word"]>>(4*(u%4)))&15
    elif tp==1:
        ix=(p["word"]>>(8*(u%2)))&255
    else:
        ix=-1
    if p["index"]!=ix:
        raise BadSource("packed indexed texel nibble/byte mismatch")
    if ix<0:
        if p["palette"]!=0 or (p["palx"],p["paly"])!=(-1,-1):
            raise BadSource("direct 15bpp texel must not look up a palette")
        expected=p["word"]
        typ="direct15"
    else:
        clutx=(p["clut"]&63)*16+ix
        cluty=(p["clut"]>>6)&511
        if not 0<=clutx<1024 or not 0<=cluty<512:
            raise BadSource("computed CLUT address out of bounds")
        if (p["palx"],p["paly"])!=(clutx,cluty):
            raise BadSource("CLUT pixel VRAM address mismatch")
        expected=p["palette"]
        typ="indexed4" if tp==0 else "indexed8"
    if expected!=p["raw"]:
        raise BadSource("original SampleTexture raw texel differs from independent VRAM word/CLUT")
    return typ


def audit(lines,decoded,slots,source_sha=None):
    pixel=audit_v48(lines,decoded,slots,source_sha=source_sha)
    if pixel["status"]=="refused":
        raise BadSource("v48 independent pixel proof refused: "+str(pixel["errors"][:5]))
    v48={}
    v49={}
    for line in lines:
        a=parse_v48(line)
        if a is not None:
            key=tuple(a[k] for k in ("f","token","target","x","y","u","v"))
            if key in v48:raise BadSource("ambiguous repeated v48 pixel key")
            v48[key]=a
        b=parse(line)
        if b is not None:
            key=tuple(b[k] for k in ("f","token","target","x","y","u","v"))
            if key in v49:raise BadSource("duplicate v49 texture sample")
            v49[key]=b
    if set(v48)!=set(v49):
        raise BadSource("missing or extra per-pixel source VRAM evidence")
    counts=Counter()
    errors=[]
    for key,sample in sorted(v49.items()):
        pix=v48[key]
        if any(sample[k]!=pix[k] for k in ("f","token","gfx","route","target",
                                           "x","y","u","v","raw")):
            errors.append(f"{key}: source sample and final output fields disagree")
            continue
        try:
            kind=independent_sample(sample)
        except BadSource as exc:
            errors.append(f"{key}: {exc}")
            continue
        counts[kind]+=1
    status=("refused" if errors else
            "vram_clut_source_correlated" if counts and pixel["status"]=="pixel_decisions_correlated"
            else "insufficient_sparse_evidence")
    return {
        "schema":"vh-map02-vram-clut-window-v49",
        "status":status,
        "per_pixel_source_samples":len(v49),
        "source_type_counts":dict(counts),
        "native_source_samples":sum(v["target"]==0 for v in v49.values()),
        "hires_source_samples":sum(v["target"]==1 for v in v49.values()),
        "reference_pixel_proof":pixel["status"],
        "independently_recomputed_source_matches":sum(counts.values()),
        "source_sha256":source_sha,
        "original_texture_bytes_authenticated":False,
        "retail_map_authenticity_proven":False,
        "genuine_gameplay_proven":False,
        "HD_replacement_approved":False,
        "errors":errors[:40],
        "note":"Original VRAM/CLUT halfwords observed by C before PutPixel. Checks independent addressing and palette math, NOT independently captured full VRAM or retail artwork.",
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
        compressed,_,_=read_prs(a.prs)
        result=audit(_read_lines(a.gpu_log),unpack_bounded(compressed),
                     load_v24(a.v24),pre["sha256_input"])
        contents=json.dumps(result,sort_keys=True,indent=2)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as fp:fp.write(contents)
        else:
            sys.stdout.write(contents)
        return {"vram_clut_source_correlated":0,
                "refused":1,"insufficient_sparse_evidence":2}[result["status"]]
    except (OSError,ValueError,UnicodeError) as exc:
        print("[v49-source] REFUSED: "+str(exc),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
