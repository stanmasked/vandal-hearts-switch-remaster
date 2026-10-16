#!/usr/bin/env python3
"""v68 ordered direct-GP0 MMIO + GPU-DMA2 + GP1 local capture audit.

Direct GP0 words can be portions of a larger packet, so an apparent
0xE6 data word cannot be interpreted without full packet boundaries.
Direct words are buffered until the next DMA submission or GP1 reset.
Unsupported discontinuities fail closed. No packet is treated as
proof of actual GPU-plugin FIFO consumption or authentic retail.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .audit_map02_v61_private_capture import local_bytes,local_json
from .audit_map02_v63_gp0_gp1_state import GpuState,interpret_words
from .audit_map02_v67_versioned_ram import check_manifest,read_snapshots,RAM_BYTES,MAX_FRAMES
from .ingest_map02_v65_gpu_probe import parse_observations
from .verify_map02_v60_ps1_dma import DmaError,walk_dma

MAX_MMIO=4096

def audit(versions:list[bytes],manifest:dict,log:bytes):
    check_manifest(versions,manifest)
    header,events=parse_observations(log)
    if header["source_class"]!=manifest["source_class"]:
        raise DmaError("source classification mismatch")
    frames=len(versions)
    if not frames<=len(events)<=frames*2+MAX_MMIO:
        raise DmaError("mixed GPU event count out of bounds")
    frame=0
    tick=-1
    direct=[]
    observed_mmio=0
    dma_words=0
    dma_commands=0
    gp1_full=gp1_fifo=0
    state=GpuState()
    state_events=0
    aggregate_draws=0
    gp1_pending=False
    for event in events:
        if not isinstance(event,dict):
            raise DmaError("invalid observed GPU event")
        kind=event.get("kind")
        if kind=="GP0_MMIO":
            keys={"kind","tick","frame","word"}
        elif kind=="GP0_DMA2":
            keys={"kind","tick","frame","head","words"}
        elif kind=="GP1_WRITE":
            keys={"kind","tick","before_frame","word"}
        else:
            raise DmaError("unrecognized event port or type")
        if set(event)!=keys or type(event["tick"])!=int or event["tick"]<=tick or event["tick"]>10**15:
            raise DmaError("invalid event schema or nonmonotonic clock")
        tick=event["tick"]
        if kind=="GP0_MMIO":
            if gp1_pending:
                # A GP0 MMIO after a recorded GP1 reset is permitted:
                # this is still the next DMA frame's GP0 stream.
                pass
            if (type(event["frame"])!=int or event["frame"]!=frame or frame>=frames
                    or type(event["word"])!=int or not 0<=event["word"]<=0xffffffff
                    or len(direct)>=MAX_MMIO):
                raise DmaError("invalid directly written GP0 command data")
            direct.append(event["word"])
            observed_mmio+=1
            continue
        if kind=="GP1_WRITE":
            if (type(event["before_frame"])!=int or event["before_frame"]!=frame
                    or frame>=frames or gp1_pending
                    or type(event["word"])!=int or event["word"] not in (0,0x01000000)):
                raise DmaError("unsupported GP1 port operation or event ordering")
            if direct:
                parsed,state=interpret_words(direct,state)
                state_events+=sum(x["kind"]=="REGISTER" for x in parsed)
                aggregate_draws+=sum(x["kind"] in ("POLYGON","RECT","LINE","VRAM_TRANSFER") for x in parsed)
                direct=[]
            if event["word"]==0:
                gp1_full+=1
                state=GpuState()
            else:
                gp1_fifo+=1
            gp1_pending=True
            continue
        if (type(event["frame"])!=int or event["frame"]!=frame or frame>=frames
                or type(event["head"])!=int or event["head"]!=manifest["entry_points"][frame]):
            raise DmaError("GP0 DMA submission differs from the bound frame/head")
        words=event["words"]
        if (not isinstance(words,list) or not 1<=len(words)<=65536 or
                any(type(w)!=int or not 0<=w<=0xffffffff for w in words)):
            raise DmaError("invalid GP0 DMA payload")
        actual,_=walk_dma(versions[frame],0,event["head"])
        if actual!=words:
            raise DmaError("per-frame DMA words differ from immutable captured RAM")
        packet_stream=direct+words
        parsed,state=interpret_words(packet_stream,state)
        state_events+=sum(x["kind"]=="REGISTER" for x in parsed)
        aggregate_draws+=sum(x["kind"] in ("POLYGON","RECT","LINE","VRAM_TRANSFER") for x in parsed)
        direct=[]
        dma_words+=len(words)
        dma_commands+=1
        frame+=1
        gp1_pending=False
    if frame!=frames or direct or gp1_pending:
        raise DmaError("incomplete GPU capture or unflushed direct MMIO words")
    return {
        "status":"synthetic_mixed_gpu_port_consistent" if manifest["source_class"]=="synthetic"
                 else "unverified_mixed_gpu_port_consistent",
        "frames":frame,
        "direct_gp0_mmio_words":observed_mmio,
        "gp0_dma2_submissions":dma_commands,
        "dma_gp0_words":dma_words,
        "total_gp0_input_words":observed_mmio+dma_words,
        "gp1_full_reset_events":gp1_full,
        "gp1_fifo_reset_events":gp1_fifo,
        "gpu_drawing_register_events":state_events,
        "drawing_or_transfer_packets":aggregate_draws,
        "direct_plus_dma_gp0_packets_bounded":True,
        "per_dma_ram_snapshot_gp0_words_equal":True,
        "emulator_help_executed_in_this_audit":False,
        "real_game_boot_verified":False,
        "gpu_plugin_fifo_consumption_verified":False,
        "independent_capture_provenance_verified":False,
        "retail_gp0_provenance_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "raw_gpu_payload_exported":False,
    }

def main():
    p=argparse.ArgumentParser(description="Private mixed direct-GP0/DMA2/GP1 offline audit")
    p.add_argument("--snapshot-dir",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--probe",type=Path,required=True)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    try:
        manifest=local_json(args.manifest,16384)
        heads=manifest.get("entry_points")
        if not isinstance(heads,list) or not 1<=len(heads)<=MAX_FRAMES:
            raise DmaError("RAM snapshots must have bound GPU DMA heads")
        versions=read_snapshots(args.snapshot_dir,len(heads))
        source=local_bytes(args.probe,8*1024*1024)
        result=audit(versions,manifest,source)
    except (DmaError,OSError,TypeError,ValueError,OverflowError) as exc:
        result={
            "status":"refused","error_category":type(exc).__name__,
            "retail_gp0_provenance_verified":False,
            "HD_replacement_approved":False,
            "raw_gpu_payload_exported":False,
        }
    if args.output is not None:
        if args.output.is_symlink() or args.output.resolve() in {
            args.manifest.resolve(),args.probe.resolve()
        }:
            print("Refusing capture overwrite or symlink report",file=sys.stderr)
            return 2
        try:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        except OSError:
            print("Cannot save sanitized audit",file=sys.stderr)
            return 2
    print(json.dumps(result,sort_keys=True))
    return 1 if result["status"]=="refused" else 0

if __name__=="__main__":
    raise SystemExit(main())
