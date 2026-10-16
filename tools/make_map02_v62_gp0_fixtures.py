#!/usr/bin/env python3
"""v62 4-frame entirely synthetic hardware-format GPU packet corpus.

Deliberately places GP0(E6)-looking words *inside* gouraud colors, FT4
texture attributes, polyline vertices, rectangle UV and packed VRAM data.
Packet parsing must never treat payload words as independent E6 commands.
Also splits one 12-word gouraud textured polygon across two DMA2 nodes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

from .verify_map02_v60_ps1_dma import FORMAT
BASE=0x4000
E6=0xe6000003
def xy(x,y):
    return (y&0xffff)<<16|(x&0xffff)
def uv(u,v,attr=0):
    return ((attr&0xffff)<<16)|((v&255)<<8)|(u&255)

def scenarios():
    gtex=[0x3c808080,xy(40,40),uv(20,192),
          0xe6000001,xy(60,40),uv(20,192,0x0107),
          0x123456,xy(40,60),uv(20,192),
          0xe6000002,xy(60,60),uv(20,192)]
    assert len(gtex)==12
    return [
        [[],[0xe1000107],
         [0x30808080,xy(10,10),0xe6000001,xy(11,10),0x00123456,xy(11,11)],
         gtex[:5],gtex[5:],[0xe6000001]],
        [[],[0x400000ff,xy(10,20),xy(12,22)],
         [0x500000ff,xy(10,20),0xe6000002,xy(12,22)],
         [0x480000ff,xy(10,20),xy(12,22),0xe6000001,xy(20,20),0x55555555],
         [0x580000ff,xy(10,20),0xe6000001,xy(12,22),
          0xe6000002,xy(20,20),0x50005000]],
        [[],[0x600000ff,xy(10,10),xy(5,6)],
         [0x640000ff,xy(10,10),uv(8,8,0xe600),xy(5,6)],
         [0x680000ff,xy(10,10)],
         [0x6c0000ff,xy(10,10),uv(8,8,0xe600)],
         [0x700000ff,xy(10,10)],
         [0x740000ff,xy(10,10),uv(8,8,0xe600)],
         [0x780000ff,xy(10,10)],
         [0x7c0000ff,xy(10,10),uv(8,8,0xe600)],
         [0xe6000002]],
        [[],[0x020000ff,xy(0,0),xy(4,4)],
         [0x80000000,xy(0,0),xy(8,8),xy(4,4)],
         [0xa0000000,xy(10,10),xy(3,2),
          0xe6000003,0xe6000001,0x50005000],
         [0xc0000000,xy(10,10),xy(3,2)],
         [0xe6000000]]
    ]

def generate():
    groups=scenarios()
    flat=[]
    heads=[]
    offset=0
    for nodes in groups:
        items=[]
        for payload in nodes:
            if len(payload)>255:raise AssertionError("synthetic DMA node count >255")
            items.append((BASE+offset,payload))
            offset+=(len(payload)+1)*4
        heads.append(items[0][0])
        flat.append(items)
    out=bytearray(offset)
    for items in flat:
        for i,(addr,words) in enumerate(items):
            next_addr=items[i+1][0] if i+1<len(items) else 0xffffff
            struct.pack_into("<I",out,addr-BASE,len(words)<<24|next_addr)
            for j,w in enumerate(words):
                struct.pack_into("<I",out,addr-BASE+4+4*j,w)
    raw=bytes(out)
    manifest={"format":FORMAT,"source_class":"synthetic",
              "base_address":BASE,"entry_points":heads,
              "sha256":hashlib.sha256(raw).hexdigest()}
    return raw,manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ram",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True)
    args=ap.parse_args()
    raw,manifest=generate()
    args.ram.parent.mkdir(parents=True,exist_ok=True)
    args.manifest.parent.mkdir(parents=True,exist_ok=True)
    args.ram.write_bytes(raw)
    args.manifest.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    print("SYNTHETIC_V62_PS1_GP0 frames=4 nodes="+str(sum(map(len,scenarios())))+
          " sha256="+manifest["sha256"])
    return 0

if __name__=="__main__":
    raise SystemExit(main())
