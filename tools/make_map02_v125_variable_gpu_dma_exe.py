#!/usr/bin/env python3
"""Original bounded MIPS EXE: three variable GPU DMA2 lists (1+2+2 draws).

The interpreted CPU writes ALL RAM node headers and GP0 payload words,
triggers DMA2 at 0x12000, 0x13000 and 0x14000. One middle node carries
two full three-word GP0 rectangles. Five post-handler colors: A-B-C-D-A.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,lui,ori,sw
from .make_map02_v121_mips_gp0_return_exe import (
    HEADER_SIZE,SECTION_SIZE,COLORS,SETUP,RECT_XY,RECT_SIZE,gpu_writes,
)
from .make_map02_v124_mips_single_list_return_exe import set_word

MAGIC=b"VH125SY!"
MARKER_ADDR=0x800111a0
MARKERS=tuple(0x12500000+i for i in range(4))
BASES=(0x12000,0x13000,0x14000)
DMA2_BCR=0
DMA2_CHCR=0x01000401
DMA2_DPCR=0x00000800
# Encoded as CPU-written (offset, 32-bit word) pairs for each DMA list.
# Actual signed CPU stages write these to emulated PlayStation RAM.
def chain_entries(index):
    if index not in (0,1,2):
        raise ValueError("three variable GPU DMA chains only")
    base=BASES[index]
    colors=((COLORS[0],),(COLORS[1],COLORS[2]),(COLORS[3],COLORS[4]))[index]
    items=[(0,base+0x100)]    # empty entry node -> draw node
    if index==0:
        payload=tuple(v for color in colors for v in (color,RECT_XY,RECT_SIZE))
        items.extend([(0x100,(3<<24)|(base+0x200))])
        items.extend((0x104+4*i,v) for i,v in enumerate(payload))
        items.append((0x200,0x00800000))
    elif index==1:
        # Two GP0 commands inside a single 6-word packet node.
        payload=tuple(v for color in colors for v in (color,RECT_XY,RECT_SIZE))
        items.append((0x100,(6<<24)|(base+0x200)))
        items.extend((0x104+4*i,v) for i,v in enumerate(payload))
        items.append((0x200,0x00800000))
    else:
        # Distinct two 3-word nodes, D then A; an extra link traversal.
        items.append((0x100,(3<<24)|(base+0x200)))
        items.extend((0x104+4*i,v) for i,v in enumerate((colors[0],RECT_XY,RECT_SIZE)))
        items.append((0x200,(3<<24)|(base+0x300)))
        items.extend((0x204+4*i,v) for i,v in enumerate((colors[1],RECT_XY,RECT_SIZE)))
        items.append((0x300,0x00800000))
    return tuple(items)


def stage_body(index):
    if not 0<=index<4:
        raise ValueError("four bounded MIPS stages only")
    if index==0:
        body=[lui(8,0x1f80),ori(8,8,0x1810)]
        body.extend(gpu_writes(SETUP))
        body.extend((lui(11,0x1f80),ori(11,11,0x1000)))
        body.extend(set_word(11,0xf0,DMA2_DPCR))
    else:
        base=BASES[index-1]
        body=[lui(10,0x8001),ori(10,10,base & 0xffff)]
        for off,word in chain_entries(index-1):
            body.extend(set_word(10,off,word))
        body.extend((lui(11,0x1f80),ori(11,11,0x1000)))
        body.append(sw(0,0xa8,11))
        body.extend(set_word(11,0xa0,base))
        body.extend(set_word(11,0xa4,DMA2_BCR))
        body.extend(set_word(11,0xa8,DMA2_CHCR))
    mark=MARKERS[index]
    body.extend((lui(12,MARKER_ADDR>>16),
                 ori(12,12,(MARKER_ADDR+4*index)&0xffff),
                 lui(9,mark>>16),ori(9,9,mark&0xffff),sw(9,0,12)))
    return tuple(body)


def build():
    bodies=tuple(stage_body(i) for i in range(4))
    starts=[START]
    for body in bodies[:-1]:
        starts.append(starts[-1]+4*(len(body)+2))
    stops=[]
    ops=[]
    for i,body in enumerate(bodies):
        dest=starts[i+1] if i<3 else starts[i]+4*len(body)
        stops.append(dest)
        ops.extend(body)
        ops.extend(((2<<26)|((dest>>2)&0x03ffffff),0))
    payload=b"".join(struct.pack("<I",w) for w in ops)
    if len(payload)>SECTION_SIZE:
        raise ValueError("original synthetic MIPS variable-DMA program too long")
    hdr=bytearray(HEADER_SIZE)
    hdr[:8]=b"PS-X EXE"
    struct.pack_into("<I",hdr,0x10,START)
    struct.pack_into("<I",hdr,0x18,START)
    struct.pack_into("<I",hdr,0x1c,SECTION_SIZE)
    struct.pack_into("<I",hdr,0x30,0x801fff00)
    hdr[0x4c:0x54]=MAGIC
    return bytes(hdr)+payload.ljust(SECTION_SIZE,b"\0"),tuple(stops),tuple(ops),tuple(starts)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    data,stops,ops,_=build()
    if args.output.is_symlink() or args.output.exists():
        p.error("will not overwrite a file or symbolic link")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(data)
    print("VH125_SYNTHETIC_VARIABLE_MIPS_GPU_DMA",len(data),
          "instructions",len(ops),"stops",[hex(x) for x in stops],
          "sha256",hashlib.sha256(data).hexdigest())


if __name__=="__main__":
    main()
