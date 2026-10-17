#!/usr/bin/env python3
"""Self-authored six-stage MIPS-I EXE: real RAM -> DMA2 -> GPU A-B-C-D-A.

Stage 0 sends GP0 draw setup using interpreted MIPS SW and enables only
DMA2 via the real PS1 DPCR register. In each later stage, MIPS writes an
original 3-word GP0(60) packet into PS1 RAM, then writes DMA2 MADR/BCR/
CHCR registers (0x1f8010a0/a4/a8) to *start* block GPU DMA. No host
GPU data submission or prepopulated packet buffer; the PS1 CPU creates
all words itself.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,lui,ori,sw
from .make_map02_v121_mips_gp0_return_exe import (
    HEADER_SIZE, SECTION_SIZE, COLORS, EXPECTED_PIXELS,
    SETUP, RECT_XY, RECT_SIZE, gpu_writes,
)

MAGIC=b"VH124SY!"
MARKER_ADDR=0x80011180
PACKET_ADDR=0x80012000
DMA2_MADR=PACKET_ADDR & 0x1fffff
DMA2_BCR=0x00000000  # ignored in DMA linked-list mode
DMA2_CHCR=0x01000401 # GPU linked-list DMA, start
DMA2_DPCR=0x00000800 # enable GPU channel 2, priority 0, other channels off
MARKERS=(0x12400000,0x12400001)
NODE_FIRST=0x00012000
NODE_DRAWS=tuple(0x00012100+0x100*i for i in range(5))
NODE_END=0x00012600
NODE_ADDRS=(NODE_FIRST,)+NODE_DRAWS+(NODE_END,)
HEAD_FIRST=NODE_DRAWS[0]
HEAD_DRAWS=tuple((3<<24)|NODE_ADDRS[i+2] for i in range(5))
HEAD_END=0x00800000



def set_word(rt,address,value):
    """Store a complete 32-bit constant at the register address in rt."""
    return (lui(9,value>>16),ori(9,9,value & 0xffff),sw(9,address,rt))


def stage_body(index):
    if index not in (0,1):
        raise ValueError("two bounded synthetic CPU stages only")
    if index==0:
        body=[lui(8,0x1f80),ori(8,8,0x1810)]
        body.extend(gpu_writes(SETUP))
        body.extend((lui(11,0x1f80),ori(11,11,0x1000)))
        body.extend(set_word(11,0xf0,DMA2_DPCR))
    else:
        body=[lui(10,PACKET_ADDR>>16),ori(10,10,PACKET_ADDR & 0xffff)]
        # CPU authors every node header and all 15 GP0 words in RAM.
        # 0-word lead -> 5 distinct 3-word rectangles -> 0-word end.
        entries=[(0,HEAD_FIRST)]
        for i,color in enumerate(COLORS):
            offset=0x100*(i+1)
            entries.extend((
                (offset,HEAD_DRAWS[i]),
                (offset+4,color),
                (offset+8,RECT_XY),
                (offset+12,RECT_SIZE),
            ))
        entries.append((0x600,HEAD_END))
        for off,value in entries:
            body.extend(set_word(10,off,value))
        body.extend((lui(11,0x1f80),ori(11,11,0x1000)))
        body.append(sw(0,0xa8,11))
        body.extend(set_word(11,0xa0,DMA2_MADR))
        body.extend(set_word(11,0xa4,DMA2_BCR))
        body.extend(set_word(11,0xa8,DMA2_CHCR))
    marker=MARKERS[index]
    body.extend((lui(12,MARKER_ADDR>>16),
                 ori(12,12,(MARKER_ADDR+4*index)&0xffff),
                 lui(9,marker>>16),ori(9,9,marker&0xffff),sw(9,0,12)))
    return tuple(body)


def build():
    bodies=tuple(stage_body(i) for i in range(2))
    starts=[START]
    for body in bodies[:-1]:
        starts.append(starts[-1]+(len(body)+2)*4)
    stops=[]
    ops=[]
    for index,body in enumerate(bodies):
        dest=starts[index+1] if index<1 else starts[index]+len(body)*4
        stops.append(dest)
        ops.extend(body)
        ops.extend(((2<<26)|((dest>>2)&0x03ffffff),0))
    payload=b"".join(struct.pack("<I",w) for w in ops)
    if len(payload)>SECTION_SIZE:
        raise ValueError("synthetic GPU linked-list MIPS program exceeds EXE load section")
    header=bytearray(HEADER_SIZE)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x54]=MAGIC
    return bytes(header)+payload.ljust(SECTION_SIZE,b"\0"),tuple(stops),tuple(ops),tuple(starts)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    data,stops,ops,_=build()
    if a.output.is_symlink() or a.output.exists():
        p.error("refusing overwrite of synthetic DMA2 EXE")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(data)
    print("VH124_SYNTHETIC_MIPS_FIVE_GP0_ONE_DMA",len(data),
          "mips_ops",len(ops),"stage_end",[hex(x) for x in stops],
          "sha256",hashlib.sha256(data).hexdigest())


if __name__=="__main__":
    main()
