#!/usr/bin/env python3
"""v62: bounded GP0 packet-boundary decoder (NOT a pixel renderer).

Supports hardware GP0 polygon/line/polyline/rectangle layouts, memory
transfers, rendering state and mask. Strictly counts command payload words;
NEVER scans a vertex/color/VRAM upload payload for apparent E6 opcodes.
The GPU DMA2 linked-list framing remains handled separately by v60.

Hardware description reference: psx-spx.consoledev.net/ps1/gpu/
render-polygon-commands/, render-line-commands/, render-rectangle-commands/,
and memory-transfer-commands/.
"""
from __future__ import annotations

MAX_GP0_WORDS=65536
MAX_POLYLINE_WORDS=4096

def _error(message):
    # Lazy import preserves public v60 DmaError and prevents circular import.
    from .verify_map02_v60_ps1_dma import DmaError
    raise DmaError(message)

def _xy(word:int)->tuple[int,int]:
    x=word&65535
    y=(word>>16)&65535
    return (x-65536 if x>=32768 else x,
            y-65536 if y>=32768 else y)

def _polyline_end(word:int)->bool:
    return word & 0xf000f000 == 0x50005000

def _bounded_polyline(words:list[int], start:int, shaded:bool)->int:
    """Return next GP0 position; terminator is checked only at vertex start.

    Command+two vertices: mono [CMD,XY0,XY1], shaded
    [CMD,XY0,COLOR1,XY1]. Additional vertices: XY (mono) or COLOR+XY
    (shaded). The terminator has (word & 0xf000f000)==0x50005000.
    """
    n=len(words)
    pos=start+(4 if shaded else 3)
    if pos>=n:
        _error("unterminated GP0 polyline")
    limit=min(n,start+MAX_POLYLINE_WORDS)
    stride=2 if shaded else 1
    while pos<limit:
        if _polyline_end(words[pos]):
            return pos+1
        if pos+stride>n:
            _error("partial GP0 polyline vertex")
        pos+=stride
    _error("unterminated or excessively long GP0 polyline")

def _packet_size(words:list[int],pos:int)->int:
    command=words[pos]
    opcode=command>>24
    if opcode in (0x00,0x01,0x1f,0xe1,0xe2,0xe3,0xe4,0xe5,0xe6):
        return 1
    if opcode==0x02:              # GP0(02) fill VRAM
        return 3
    if 0x20<=opcode<=0x3f:       # flat/gouraud textured/solid tri/quad
        vertices=4 if opcode&8 else 3
        textured=bool(opcode&4)
        shaded=bool(opcode&16)
        return 1+vertices+vertices*int(textured)+(vertices-1)*int(shaded)
    if 0x40<=opcode<=0x5f:
        shaded=bool(opcode&16)
        polyline=bool(opcode&8)
        return (_bounded_polyline(words,pos,shaded)-pos if polyline
                else (4 if shaded else 3))
    if 0x60<=opcode<=0x7f:
        textured=bool(opcode&4)
        variable=(opcode&0x18)==0
        return 2+int(textured)+int(variable)
    if 0x80<=opcode<=0x9f:      # VRAM -> VRAM
        return 4
    if 0xa0<=opcode<=0xbf:      # CPU -> VRAM, packed 16-bit halfwords
        if pos+3>len(words):
            _error("truncated GP0 CPU-to-VRAM transfer header")
        size=words[pos+2]
        width=(size&0xffff)&0x3ff
        height=((size>>16)&0xffff)&0x1ff
        if not width:width=1024
        if not height:height=512
        return 3+(width*height+1)//2
    if 0xc0<=opcode<=0xdf:      # VRAM -> CPU; read data via GPUREAD
        return 3
    _error(f"unsupported GP0 opcode 0x{opcode:02x} at word {pos}; no fuzzy E6 scan")

def parse_gp0_v62(words:list[int],initial_mask:tuple[int,int]=(0,0),
                  return_state:bool=False):
    if not (isinstance(initial_mask,tuple) and len(initial_mask)==2 and
            all(type(v)==int and v in (0,1) for v in initial_mask)):
        _error("invalid initial E6 state")
    if len(words)>MAX_GP0_WORDS:
        _error("GPU stream word count exceeds hard limit")
    events=[]
    mask_set,mask_check=initial_mask
    position=0
    while position<len(words):
        command=words[position]
        if type(command)!=int or command<0 or command>0xffffffff:
            _error("GPU command word out of unsigned 32-bit range")
        opcode=command>>24
        count=_packet_size(words,position)
        if count<=0 or count>MAX_GP0_WORDS or position+count>len(words):
            _error(f"truncated GP0 packet at word {position}")
        packet=words[position:position+count]
        if opcode==0xe6:
            if command&0xfffffc:
                _error("GP0(E6) reserved bits nonzero")
            mask_set=command&1
            mask_check=(command>>1)&1
            events.append({"type":"E6","word":command,
                           "set":mask_set,"check":mask_check})
        elif 0x2c<=opcode<=0x2f:
            x,y=_xy(packet[1])
            events.append({
                "type":"FT4","opcode":opcode,"x0":x,"y0":y,
                "u0":packet[2]&255,"v0":(packet[2]>>8)&255,
                "tpage":(packet[4]>>16)&0xffff,
                "semi":(opcode>>1)&1,
                "mask_set":mask_set,"mask_check":mask_check
            })
        elif 0x20<=opcode<=0x3f:
            vertices=4 if opcode&8 else 3
            events.append({"type":"POLYGON","opcode":opcode,
                           "vertices":vertices,"textured":bool(opcode&4),
                           "gouraud":bool(opcode&16),
                           "mask_set":mask_set,"mask_check":mask_check})
        elif 0x40<=opcode<=0x5f:
            events.append({"type":"POLYLINE" if opcode&8 else "LINE",
                           "opcode":opcode,"gouraud":bool(opcode&16),
                           "mask_set":mask_set,"mask_check":mask_check})
        elif 0x60<=opcode<=0x7f:
            size_code=(opcode>>3)&3
            events.append({"type":"RECT","opcode":opcode,
                           "size_code":size_code,
                           "textured":bool(opcode&4),
                           "mask_set":mask_set,"mask_check":mask_check})
        elif 0x80<=opcode<=0xdf:
            events.append({"type":"TRANSFER","opcode":opcode,
                           "payload_words":count-3 if 0xa0<=opcode<=0xbf else 0})
        elif opcode==0x02:
            events.append({"type":"FILL_VRAM"})
        elif opcode in (0xe1,0xe2,0xe3,0xe4,0xe5):
            events.append({"type":f"E{opcode&15}","word":command})
        elif opcode==0x1f:
            events.append({"type":"IRQ1"})
        position+=count
    return (events,(mask_set,mask_check)) if return_state else events
