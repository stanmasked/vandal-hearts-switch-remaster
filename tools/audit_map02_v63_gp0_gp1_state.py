#!/usr/bin/env python3
"""v63 strictly scoped PS1 GP0(E1..E6) drawing-state interpreter.

Structural GPU state inspection, NOT a GPU renderer or retail capture
authenticator. GPU E1..E6 state persists across DMA lists. Optional,
separately supplied GP1(00) reset evidence changes state; GP1(01) only
clears the command FIFO, not drawing registers. Sidecar event provenance
remains USER-ASSERTED and cannot certify original retail behavior.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

from .decode_map02_v62_gp0 import _packet_size
from .verify_map02_v60_ps1_dma import DmaError, manifest_check, walk_dma

GP1_SCHEMA="map02-v63-gp1-boundary-events-v1"
MAX_GP1_SIZE=16384
GP1_KEYS={"schema","events"}
GP1_EVENT_KEYS={"before_frame","word"}
GP0_REGISTERS=range(0xe1,0xe7)

@dataclass(frozen=True)
class GpuState:
    mode:int=0
    texture_window:int=0
    area_start:int=0
    area_end:int=0
    offset:int=0
    mask_set:int=0
    mask_check:int=0

def _signed_11(value):
    return value-2048 if value&1024 else value

def _register_fields(state:GpuState):
    m=state.mode
    w=state.texture_window
    return {
        "draw_mode":{
            "tpage_x":(m&15)*64,
            "tpage_y":((m>>4)&1)*256,
            "abr":(m>>5)&3,
            "texture_format":(m>>7)&3,
            "dithering":(m>>9)&1,
            "draw_to_display":(m>>10)&1,
        },
        "texture_window":{
            "mask_x":w&31,"mask_y":(w>>5)&31,
            "offset_x":(w>>10)&31,"offset_y":(w>>15)&31
        },
        "drawing_area":{
            "x0":state.area_start&1023,
            "y0":(state.area_start>>10)&511,
            "x1":state.area_end&1023,
            "y1":(state.area_end>>10)&511,
            "inclusive":True,
        },
        "drawing_offset":{
            "x":_signed_11(state.offset&2047),
            "y":_signed_11((state.offset>>11)&2047),
        },
        "mask_set":state.mask_set,
        "mask_check":state.mask_check
    }

def apply_gp0_state(state:GpuState,command:int)->GpuState:
    if type(command)!=int or command<0 or command>0xffffffff:
        raise DmaError("invalid GP0 drawing register word")
    opcode=command>>24
    value=command&0xffffff
    if opcode==0xe1:
        # Strict original retail-style v0 GPU. E1 bits 11-13 are
        # revision-dependent extensions, never infer on v0.
        if value&~0x7ff:raise DmaError("v0 GP0(E1) reserved/revision bits")
        return replace(state,mode=value)
    if opcode==0xe2:
        if value&~0xfffff:raise DmaError("GP0(E2) reserved bits")
        return replace(state,texture_window=value)
    if opcode==0xe3:
        if value&~0x7ffff:raise DmaError("v0 GP0(E3) reserved bits")
        return replace(state,area_start=value)
    if opcode==0xe4:
        if value&~0x7ffff:raise DmaError("v0 GP0(E4) reserved bits")
        return replace(state,area_end=value)
    if opcode==0xe5:
        if value&~0x3fffff:raise DmaError("GP0(E5) reserved bits")
        return replace(state,offset=value)
    if opcode==0xe6:
        if value&~3:raise DmaError("GP0(E6) reserved bits")
        return replace(state,mask_set=value&1,mask_check=(value>>1)&1)
    raise DmaError("not GP0(E1..E6)")

def texture_window_uv(u:int,v:int,state:GpuState)->tuple[int,int]:
    """Documented PS1 E2 mask and offset applied in 8-pixel increments."""
    if not (type(u)==int and type(v)==int and 0<=u<256 and 0<=v<256):
        raise DmaError("UV inputs must be unsigned 8-bit")
    win=state.texture_window
    mx=(win&31)<<3
    my=((win>>5)&31)<<3
    ox=((win>>10)&31)&(win&31)
    oy=((win>>15)&31)&((win>>5)&31)
    return (u&~mx)|(ox<<3),(v&~my)|(oy<<3)

def check_gp1_sidecar(sidecar:dict|None,frame_count:int):
    if sidecar is None:return {}
    if not isinstance(sidecar,dict) or set(sidecar)!=GP1_KEYS or sidecar["schema"]!=GP1_SCHEMA:
        raise DmaError("invalid GP1 reset event sidecar schema")
    events=sidecar["events"]
    if not isinstance(events,list) or len(events)>frame_count:
        raise DmaError("invalid GP1 event count")
    by_frame={}
    for event in events:
        if not isinstance(event,dict) or set(event)!=GP1_EVENT_KEYS:
            raise DmaError("invalid GP1 boundary entry")
        idx=event["before_frame"]
        word=event["word"]
        if type(idx)!=int or not 0<=idx<frame_count or idx in by_frame:
            raise DmaError("invalid or duplicate GP1 frame boundary")
        if type(word)!=int or word not in (0x00000000,0x01000000):
            raise DmaError("unsupported/argument-bearing GP1 reset command")
        by_frame[idx]=word
    if list(by_frame)!=sorted(by_frame):
        raise DmaError("GP1 boundary events must be ascending")
    return by_frame

def _draw_kind(opcode:int)->str:
    if 0x20<=opcode<=0x3f:return "POLYGON"
    if 0x40<=opcode<=0x5f:return "LINE"
    if 0x60<=opcode<=0x7f:return "RECT"
    if 0x80<=opcode<=0xdf:return "VRAM_TRANSFER"
    return ""

def interpret_words(words:list[int],state:GpuState):
    events=[]
    pos=0
    while pos<len(words):
        cmd=words[pos]
        if type(cmd)!=int or not 0<=cmd<=0xffffffff:
            raise DmaError("invalid GPU stream word")
        count=_packet_size(words,pos)
        if pos+count>len(words):
            raise DmaError("truncated GPU packet while decoding registers")
        op=cmd>>24
        if op in GP0_REGISTERS:
            state=apply_gp0_state(state,cmd)
            events.append({"kind":"REGISTER","opcode":op,"state":_register_fields(state)})
        else:
            kind=_draw_kind(op)
            if kind:
                # Snapshot before executing this command. GP0(02) FillVRAM
                # notably does NOT obey E6 destination mask, unlike transfers.
                events.append({"kind":kind,"opcode":op,
                               "state":_register_fields(state),
                               "gp0_word_index":pos})
            elif op==0x02:
                events.append({"kind":"FILL_VRAM","opcode":op,"mask_applies":False})
        pos+=count
    return events,state

def interpret_capture(data:bytes,manifest:dict,sidecar:dict|None=None):
    manifest_check(data,manifest)
    by_frame=check_gp1_sidecar(sidecar,len(manifest["entry_points"]))
    current=GpuState()
    out=[]
    reset_count=fifo_count=reg_count=draw_count=0
    for index,head in enumerate(manifest["entry_points"]):
        boundary=by_frame.get(index)
        if boundary==0:
            current=GpuState()
            reset_count+=1
        elif boundary==0x01000000:
            fifo_count+=1
        before=current
        words,nodes=walk_dma(data,manifest["base_address"],head)
        events,current=interpret_words(words,current)
        reg_count+=sum(e["kind"]=="REGISTER" for e in events)
        draw_count+=sum(e["kind"] in ("POLYGON","LINE","RECT","VRAM_TRANSFER") for e in events)
        out.append({"frame":index,"before":before,"after":current,
                    "boundary":boundary,"events":events,
                    "dma_nodes":len(nodes)})
    return {"frames":out,"gp1_reset_count":reset_count,
            "gp1_fifo_reset_count":fifo_count,"registers":reg_count,
            "draws_and_transfers":draw_count,
            "sidecar_supplied":sidecar is not None}

def audit(data:bytes,manifest:dict,sidecar:dict|None=None):
    result=interpret_capture(data,manifest,sidecar)
    return {
        "status":"synthetic_gp0_gp1_state_verified" if manifest["source_class"]=="synthetic"
               else "unverified_capture_gp0_gp1_structurally_valid",
        "source_class":manifest["source_class"],
        "frames":len(result["frames"]),
        "dma_nodes":sum(x["dma_nodes"] for x in result["frames"]),
        "gp0_e1_to_e6_register_commands":result["registers"],
        "draws_and_transfers_with_state_snapshots":result["draws_and_transfers"],
        "claimed_gp1_full_resets":result["gp1_reset_count"],
        "claimed_gp1_fifo_resets":result["gp1_fifo_reset_count"],
        "gp1_sidecar_supplied":result["sidecar_supplied"],
        "actual_gp1_commands_observed_on_hardware":False,
        "unknown_unobserved_external_gpu_commands_possible":True,
        "retail_gp0_provenance_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "raw_gpu_payload_exported":False
    }

def _read_json_limited(path:Path,max_size:int):
    from .audit_map02_v61_private_capture import local_json
    return local_json(path,max_size)

def main():
    p=argparse.ArgumentParser(description="Local-only GPU register state boundaries; do not upload retail assets")
    p.add_argument("--ram",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--gp1",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        from .audit_map02_v61_private_capture import local_bytes
        data=local_bytes(a.ram,4*1024*1024)
        manifest=_read_json_limited(a.manifest,16384)
        gp1=_read_json_limited(a.gp1,MAX_GP1_SIZE) if a.gp1 else None
        report=audit(data,manifest,gp1)
    except (ValueError,OSError,TypeError,OverflowError) as e:
        report={"status":"refused","error_category":type(e).__name__,
                "HD_replacement_approved":False,
                "retail_gp0_provenance_verified":False,
                "raw_gpu_payload_exported":False}
    if a.output:
        sources=[a.ram,a.manifest,a.gp1]
        if a.output.is_symlink() or a.output.resolve() in {
                x.resolve() for x in sources if x is not None}:
            print("Refusing capture input overwrite or symlink report",file=__import__("sys").stderr)
            return 2
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
    return 1 if report["status"]=="refused" else 0

if __name__=="__main__":raise SystemExit(main())
