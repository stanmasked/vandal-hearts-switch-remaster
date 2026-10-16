#!/usr/bin/env python3
"""Generate deterministic, unmistakably SYNTHETIC PS1-format DMA2 RAM.

No PC-port token format, no retail files, no copyrighted assets. Generates
empty OT bucket -> GP0(E1) -> 2..4 (E6 + real 9-word GP0 FT4) DMA nodes per
frame. Tests the distinct raw hardware transport without claiming actual
retail command provenance. Payload contains an E6-looking word on purpose.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

from .verify_map02_v59_trace import FRAMES
from .verify_map02_v60_ps1_dma import FORMAT

BASE=0x1000

def polygon(step:int, abr:int, texel:int, semi:int):
    code=((0x2c | (2 if semi else 0))<<24)|0x808080
    tpage=7|(abr<<5)|(2<<7)
    xy=lambda x,y: (x&0xffff)|((y&0xffff)<<16)
    uv=lambda u,v,attr=0:(u&255)|((v&255)<<8)|((attr&0xffff)<<16)
    # Upper half of the final texture-coordinate word deliberately resembles
    # an E6 command; parser MUST consume it as FT4 vertex payload.
    return [code,xy(70,70),uv(20+step,192),
            xy(90,70),uv(20+step,192,tpage),
            xy(70,90),uv(20+step,192),
            xy(90,90),0xe6000003]

def generate():
    chains=[]
    for name,bg,clip,abr,steps in FRAMES:
        nodes=[[]]  # one real empty OT bucket node, not a GPU command
        nodes.append([0xe1000000|(7|(abr<<5)|(2<<7))])
        for i,(cmd,texel,semi) in enumerate(steps):
            nodes.append([cmd]+polygon(i,abr,texel,semi))
        chains.append(nodes)
    offset=0
    addresses=[]
    raw=[]
    for nodes in chains:
        addrs=[]
        for words in nodes:
            addr=BASE+offset
            addrs.append(addr)
            raw.append((addr,words))
            offset+=4*(len(words)+1)
        addresses.append(addrs)
    mem=bytearray(offset)
    for addrs,nodes in zip(addresses,chains):
        for i,words in enumerate(nodes):
            addr=addrs[i]
            next_addr=addrs[i+1] if i+1<len(addrs) else 0xffffff
            struct.pack_into("<I",mem,addr-BASE,(len(words)<<24)|next_addr)
            for k,w in enumerate(words):
                struct.pack_into("<I",mem,addr-BASE+4+4*k,w)
    data=bytes(mem)
    manifest={
        "format":FORMAT,
        "source_class":"synthetic",
        "base_address":BASE,
        "entry_points":[x[0] for x in addresses],
        "sha256":hashlib.sha256(data).hexdigest(),
    }
    return data,manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ram",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    a=p.parse_args()
    raw,manifest=generate()
    a.ram.parent.mkdir(parents=True,exist_ok=True)
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    a.ram.write_bytes(raw)
    a.manifest.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    print("SYNTHETIC_PS1_DMA2 frames=4 gp0_mask=11 source_sha256="+manifest["sha256"])
    return 0

if __name__=="__main__":
    raise SystemExit(main())
