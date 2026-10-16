#!/usr/bin/env python3
"""v63 synthetic-only PS1 DMA2 register-state sequences + GP1 boundary sidecar."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
from .verify_map02_v60_ps1_dma import FORMAT
from .audit_map02_v63_gp0_gp1_state import GP1_SCHEMA

BASE=0x6000

def xy(x,y):
    return (x&0xffff)|((y&0xffff)<<16)

def ft4():
    return [0x2c808080,xy(70,70),0x0000c014,
            xy(90,70),0x0107c014,
            xy(70,90),0x0000c014,
            xy(90,90),0xe6000003] # E6-looking UV payload, not command

MODE0=(3|(1<<4)|(2<<5)|(2<<7)|(1<<9)|(1<<10))
WIN0=(1|(3<<5)|(1<<10)|(2<<15))
E1_0=0xe1000000|MODE0
E2_0=0xe2000000|WIN0
E3_0=0xe3000000|(64|(70<<10))
E4_0=0xe4000000|(200|(180<<10))
E5_0=0xe5000000|((-24&0x7ff)|(15<<11))
E6_0=0xe6000003

MODE2=(8|(1<<5)|(1<<7)|(1<<10))
E1_2=0xe1000000|MODE2
E2_1=0xe2000000|(31|(31<<5)|(12<<10)|(5<<15))
E5_2=0xe5000000|((13&0x7ff)|((-17&0x7ff)<<11))

def scenes():
    return [
        [
            [],
            [E1_0,E2_0,E3_0,E4_0,E5_0,E6_0],
            ft4(),
            [0x600000ff,xy(80,80),xy(4,4)],
            [0x020000ff,xy(0,0),xy(4,4)],
        ],
        [
            [],
            ft4(),  # E1..E6 persist from prior frame
            [E2_1],
            [0x640000ff,xy(80,80),0xe6000003,xy(4,4)],
            [0xa0000000,xy(4,4),xy(2,2),0xe6000001,0xe6000003],
        ],
        [
            [],
            ft4(),  # GP1 full reset to zero before this frame
            [E1_2,0xe3000000|xy(20,30),0xe4000000|xy(200,180),E5_2,0xe6000001],
            [0x400000ff,xy(5,5),xy(8,8)],
        ],
        [
            [],
            ft4(),  # GP1(01) FIFO clear but drawing state remains
            [0xe6000002],
            ft4(),
            [0x80000000,xy(0,0),xy(40,40),xy(4,4)],
        ]
    ]

def generate():
    frames=scenes()
    offsets=[]
    total=0
    for nodes in frames:
        ids=[]
        for payload in nodes:
            if len(payload)>255:raise AssertionError("DMA node >255 words")
            ids.append(BASE+total)
            total+=4+len(payload)*4
        offsets.append(ids)
    out=bytearray(total)
    for nodes,addresses in zip(frames,offsets):
        for i,words in enumerate(nodes):
            address=addresses[i]-BASE
            nxt=addresses[i+1] if i+1<len(addresses) else 0xffffff
            struct.pack_into("<I",out,address,(len(words)<<24)|nxt)
            for k,word in enumerate(words):
                struct.pack_into("<I",out,address+4+4*k,word)
    data=bytes(out)
    manifest={
        "format":FORMAT,"source_class":"synthetic",
        "base_address":BASE,"entry_points":[nodes[0] for nodes in offsets],
        "sha256":hashlib.sha256(data).hexdigest()
    }
    gp1={"schema":GP1_SCHEMA,"events":[
        {"before_frame":2,"word":0x00000000},
        {"before_frame":3,"word":0x01000000}
    ]}
    return data,manifest,gp1

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--ram",type=Path,required=True)
    a.add_argument("--manifest",type=Path,required=True)
    a.add_argument("--gp1",type=Path,required=True)
    v=a.parse_args()
    data,manifest,gp1=generate()
    for p in (v.ram,v.manifest,v.gp1):p.parent.mkdir(parents=True,exist_ok=True)
    v.ram.write_bytes(data)
    v.manifest.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    v.gp1.write_text(json.dumps(gp1,sort_keys=True,indent=2)+"\n")
    print("V63_SYNTHETIC_GP0_GP1 frames=4 nodes=19 gp1_full_reset=1 gp1_fifo_reset=1")
    return 0

if __name__=="__main__":raise SystemExit(main())
