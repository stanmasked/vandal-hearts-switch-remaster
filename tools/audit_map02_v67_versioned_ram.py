#!/usr/bin/env python3
"""v67: verify mutable per-submission PS1 RAM image against GPU port log.

Each GP0 DMA2 event must match a *distinct version-numbered* 2 MiB PS1
RAM capture taken immediately at the pre-submit hook, not an inaccurate
single final RAM snapshot. Only aggregated results may leave this process.
Self-authored logs + snapshot hashes are not independent retail proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .audit_map02_v61_private_capture import local_bytes,local_json
from .audit_map02_v63_gp0_gp1_state import GpuState,interpret_words
from .ingest_map02_v65_gpu_probe import parse_observations
from .verify_map02_v60_ps1_dma import DmaError,walk_dma

SCHEMA="map02-v67-versioned-pre-submit-ram-v1"
RAM_BYTES=2*1024*1024
MAX_FRAMES=64
MAX_TOTAL_WORDS=MAX_FRAMES*65536
FIELDS={"schema","source_class","ram_size","base_address","frame_sha256","entry_points"}
HEX=set("0123456789abcdef")

def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def manifest_for_frames(versions:list[bytes],source_class:str,entry_points:list[int]):
    if (source_class not in ("synthetic","user-supplied-unverified")
            or not 1<=len(versions)<=MAX_FRAMES
            or any(len(ram)!=RAM_BYTES for ram in versions)):
        raise DmaError("bounded PS1 RAM frame versions or source class invalid")
    if (not isinstance(entry_points,list) or len(entry_points)!=len(versions)
            or any(type(h)!=int or h<0 or h>=RAM_BYTES or h%4 for h in entry_points)):
        raise DmaError("DMA head binding for every frame is required")
    return {
        "schema":SCHEMA,"source_class":source_class,
        "ram_size":RAM_BYTES,"base_address":0,
        "entry_points":entry_points,
        "frame_sha256":[digest(ram) for ram in versions]
    }

def check_manifest(versions:list[bytes],manifest:dict):
    if not isinstance(manifest,dict) or set(manifest)!=FIELDS:
        raise DmaError("versioned DMA snapshot manifest field set invalid")
    if (manifest["schema"]!=SCHEMA or
            manifest["source_class"] not in ("synthetic","user-supplied-unverified") or
            type(manifest["ram_size"])!=int or manifest["ram_size"]!=RAM_BYTES or
            type(manifest["base_address"])!=int or manifest["base_address"]!=0):
        raise DmaError("RAM versioned snapshot metadata invalid")
    heads=manifest["entry_points"]
    if (not isinstance(heads,list) or len(heads)!=len(versions)
            or any(type(h)!=int or h<0 or h>=RAM_BYTES or h%4 for h in heads)):
        raise DmaError("missing or invalid bound frame DMA head")
    hashes=manifest["frame_sha256"]
    if (not isinstance(hashes,list) or not 1<=len(hashes)<=MAX_FRAMES
            or len(hashes)!=len(versions)
            or any(type(x)!=str or len(x)!=64 or any(c not in HEX for c in x) for x in hashes)):
        raise DmaError("missing or invalid per-frame SHA256")
    for index,(ram,expected) in enumerate(zip(versions,hashes)):
        if len(ram)!=RAM_BYTES or digest(ram)!=expected:
            raise DmaError("RAM snapshot differs from the frame-bound manifest")

def _validate_stream(versions:list[bytes],manifest:dict,observations:bytes):
    check_manifest(versions,manifest)
    header,events=parse_observations(observations)
    if header["source_class"]!=manifest["source_class"]:
        raise DmaError("RAM versions and observer source class disagree")
    count=len(versions)
    if not count<=len(events)<=count*2:
        raise DmaError("a DMA event is missing or GP1 events exceed frame count")
    state=GpuState()
    last_tick=-1
    frame=0
    pending=False
    gp1_writes=0
    gp1_full=0
    gp1_fifo=0
    word_count=0
    register_updates=0
    draws=0
    for event in events:
        kind=event.get("kind")
        expected=({"kind","tick","frame","head","words"} if kind=="GP0_DMA2"
                  else {"kind","tick","before_frame","word"} if kind=="GP1_WRITE"
                  else None)
        if not isinstance(event,dict) or expected is None or set(event)!=expected:
            raise DmaError("invalid GP0 / GP1 observed record field set")
        tick=event["tick"]
        if type(tick)!=int or tick<=last_tick or tick>10**15:
            raise DmaError("capture tick order invalid")
        last_tick=tick
        if kind=="GP1_WRITE":
            idx=event["before_frame"]
            cmd=event["word"]
            if (type(idx)!=int or idx!=frame or idx>=count
                    or pending or type(cmd)!=int or cmd not in (0,0x01000000)):
                raise DmaError("unsupported GP1 command or non-adjacent GPU reset")
            pending=True
            gp1_writes+=1
            if cmd==0:
                state=GpuState()
                gp1_full+=1
            else:
                gp1_fifo+=1
            continue
        head=event["head"]
        words=event["words"]
        if (type(event["frame"])!=int or event["frame"]!=frame or
            type(head)!=int or head!=manifest["entry_points"][frame] or
            not isinstance(words,list) or not 1<=len(words)<=65536
            or any(type(x)!=int or x<0 or x>0xffffffff for x in words)):
            raise DmaError("invalid DMA2 frame, head or GP0 words")
        snapshot=versions[frame]
        from_ram,_nodes=walk_dma(snapshot,0,head)
        if from_ram!=words:
            raise DmaError("GP0 observation diverges from this frame's RAM version")
        changes,state=interpret_words(words,state)
        register_updates+=sum(e["kind"]=="REGISTER" for e in changes)
        draws+=sum(e["kind"] in ("POLYGON","RECT","LINE","VRAM_TRANSFER") for e in changes)
        word_count+=len(words)
        if word_count>MAX_TOTAL_WORDS:
            raise DmaError("too many observed command words")
        frame+=1
        pending=False
    if frame!=count or pending:
        raise DmaError("incomplete or dangling DMA2 GPU capture")
    return {
        "frames":frame,"gp1_events":gp1_writes,
        "gp1_full_reset_events":gp1_full,
        "gp1_fifo_reset_events":gp1_fifo,
        "observed_gp0_words":word_count,
        "gp0_register_updates":register_updates,
        "drawing_or_transfer_snapshots":draws
    }

def audit(versions:list[bytes],manifest:dict,observations:bytes):
    p=_validate_stream(versions,manifest,observations)
    return {
        "status":("synthetic_versioned_ram_consistent" if
                  manifest["source_class"]=="synthetic" else
                  "unverified_versioned_ram_consistent"),
        "source_class":manifest["source_class"],
        **p,
        "unique_ram_versions":len(set(manifest["frame_sha256"])),
        "multiple_distinct_ram_versions_observed":len(set(manifest["frame_sha256"]))>1,
        "per_dma_ram_snapshot_gp0_words_equal":True,
        "cross_dma_gpu_state_carried_or_gp1_reset_applied":True,
        "full_emulator_runtime_boot_verified":False,
        "gpu_plugin_gp0_fifo_consumption_verified":False,
        "producer_instrumentation_actually_installed":False,
        "gp1_write_proven_to_originate_from_hardware":False,
        "retail_gp0_provenance_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "raw_gpu_payload_exported":False,
    }

def read_snapshots(directory:Path,count:int):
    if not 1<=count<=MAX_FRAMES:
        raise DmaError("invalid versioned capture frame count")
    if directory.is_symlink() or not directory.is_dir():
        raise DmaError("snapshot directory missing or is symlink")
    versions=[]
    for i in range(count):
        path=directory/f"frame-{i:06d}.ram"
        image=local_bytes(path,RAM_BYTES)
        if len(image)!=RAM_BYTES:
            raise DmaError("snapshot must be a full 2 MiB PS1 RAM image")
        versions.append(image)
    return versions

def main():
    p=argparse.ArgumentParser(description="Local frame-versioned GP0/GP1 DMA audit")
    p.add_argument("--snapshot-dir",type=Path,required=True)
    p.add_argument("--probe",type=Path)
    p.add_argument("--manifest",type=Path)
    p.add_argument("--make-manifest",type=Path)
    p.add_argument("--source-class",choices=("synthetic","user-supplied-unverified"),
                   default="user-supplied-unverified")
    p.add_argument("--frames",type=int)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    reports=[]
    try:
        if a.make_manifest:
            if a.manifest or a.probe is None or a.output or a.frames is None:
                raise DmaError("manifest creation requires --probe and --frames")
            versions=read_snapshots(a.snapshot_dir,a.frames)
            header,events=parse_observations(local_bytes(a.probe,8*1024*1024))
            if header["source_class"]!=a.source_class:
                raise DmaError("source class differs from observed header")
            heads=[e["head"] for e in events if e.get("kind")=="GP0_DMA2"]
            if len(heads)!=a.frames:
                raise DmaError("probe frame count differs from observed heads")
            metadata=manifest_for_frames(versions,a.source_class,heads)
            if a.make_manifest.is_symlink() or a.make_manifest.exists():
                raise DmaError("refusing overwrite of RAM version manifest")
            a.make_manifest.parent.mkdir(parents=True,exist_ok=True)
            # Manifests contain private RAM digests. Fail closed on overwrite.
            import os
            fd=os.open(a.make_manifest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w") as file:
                file.write(json.dumps(metadata,sort_keys=True,indent=2)+"\n")
            print(json.dumps({"status":"local_manifest_created",
                              "frames":len(versions),
                              "retail_gp0_provenance_verified":False,
                              "HD_replacement_approved":False}))
            return 0
        if a.probe is None or a.manifest is None or a.frames is not None:
            raise DmaError("audit requires --probe and --manifest")
        metadata=local_json(a.manifest,16384)
        hashes=metadata.get("frame_sha256")
        if not isinstance(hashes,list):
            raise DmaError("frame sha256 list missing")
        versions=read_snapshots(a.snapshot_dir,len(hashes))
        observations=local_bytes(a.probe,8*1024*1024)
        report=audit(versions,metadata,observations)
    except (OSError,DmaError,ValueError,TypeError,OverflowError) as error:
        report={"status":"refused","error_category":type(error).__name__,
                "retail_gp0_provenance_verified":False,
                "HD_replacement_approved":False,
                "raw_gpu_payload_exported":False}
    if a.output:
        sources={p.resolve() for p in (a.manifest,a.probe) if p is not None}
        if a.output.is_symlink() or a.output.resolve() in sources:
            print("Refusing private capture overwrite or symlink",file=sys.stderr)
            return 2
        try:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        except OSError:
            print("unable to save aggregate-only report",file=sys.stderr)
            return 2
    print(json.dumps(report,sort_keys=True))
    return 1 if report["status"]=="refused" else 0

if __name__=="__main__":
    raise SystemExit(main())
