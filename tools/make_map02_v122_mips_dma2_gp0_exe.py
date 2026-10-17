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

MAGIC=b"VH122SY!"
MARKER_ADDR=0x80011140
PACKET_ADDR=0x80012000
DMA2_MADR=PACKET_ADDR & 0x1fffff
DMA2_BCR=0x00010003  # one block of three 32-bit GPU command words
DMA2_CHCR=0x01000201 # mem->GPU, block DMA, start
DMA2_DPCR=0x00000800 # enable GPU channel 2, priority 0, other channels off
MARKERS=tuple(0x12200000+i for i in range(6))


def set_word(rt,address,value):
    """Store a complete 32-bit constant at the register address in rt."""
    return (lui(9,value>>16),ori(9,9,value & 0xffff),sw(9,address,rt))


def stage_body(index):
    if not 0<=index<=5:
        raise ValueError("six bounded stages only")
    if index==0:
        body=[lui(8,0x1f80),ori(8,8,0x1810)]
        body.extend(gpu_writes(SETUP))
        body.extend((lui(11,0x1f80),ori(11,11,0x1000)))
        body.extend(set_word(11,0xf0,DMA2_DPCR))
    else:
        body=[lui(10,PACKET_ADDR>>16),ori(10,10,PACKET_ADDR & 0xffff)]
        # CPU, not host, authors GPU FIFO source bytes in mapped PSX RAM.
        for offset,word in enumerate((COLORS[index-1],RECT_XY,RECT_SIZE)):
            body.extend(set_word(10,4*offset,word))
        body.extend((lui(11,0x1f80),ori(11,11,0x1000)))
        # Disarm previous transfer before initiating the new one:
        # the preceding phase has already completed and been read back.
        body.append(sw(0,0xa8,11))
        body.extend(set_word(11,0xa0,DMA2_MADR))
        body.extend(set_word(11,0xa4,DMA2_BCR))
        body.extend(set_word(11,0xa8,DMA2_CHCR))
    mark=MARKERS[index]
    body.extend((lui(12,MARKER_ADDR>>16),
                 ori(12,12,(MARKER_ADDR+4*index) & 0xffff),
                 lui(9,mark>>16),ori(9,9,mark & 0xffff),
                 sw(9,0,12)))
    return tuple(body)


def build():
    bodies=tuple(stage_body(i) for i in range(6))
    starts=[START]
    for body in bodies[:-1]:
        starts.append(starts[-1]+(len(body)+2)*4)
    stops=[]
    ops=[]
    for index,body in enumerate(bodies):
        dest=starts[index+1] if index<5 else starts[index]+len(body)*4
        stops.append(dest)
        ops.extend(body)
        ops.extend(((2<<26)|((dest>>2)&0x03ffffff),0))
    payload=b"".join(struct.pack("<I",w) for w in ops)
    if len(payload)>SECTION_SIZE:
        raise ValueError("synthetic MIPS DMA2 program exceeds EXE load section")
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
    print("VH122_SYNTHETIC_MIPS_DMA2_GP0",len(data),
          "mips_ops",len(ops),"stage_end",[hex(x) for x in stops],
          "sha256",hashlib.sha256(data).hexdigest())


if __name__=="__main__":
    main()
