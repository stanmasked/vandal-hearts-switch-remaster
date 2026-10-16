#!/usr/bin/env python3
"""v61 local-only privacy-preserving preflight of user-owned PS1 GPU DMA2 RAM.

No network; no upload, no collection. Reads a bounded raw RAM file and v60
manifest directly on the user's machine, and emits ONLY sanitized aggregate
counts / scope gates, never GP0 payloads, addresses, paths or full polygons.
No user-provided attestation can turn a parsed dump into verified retail data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys

from .verify_map02_v60_ps1_dma import DmaError, decode, MAX_RAM

MAX_MANIFEST=16384
MAX_CONTEXT=8192
CONTEXT_SCHEMA="map02-v61-local-capture-context-v1"
METHODS={"unknown","emulator-debugger","hardware-probe","reconstructed"}
SCOPES={"unknown","MAP02"}
RESET_STATUSES={"unknown","no-reset-observed"}
CTX_KEYS={"schema","method","scope","frame_indices","reset_status"}
MAX_REPORT=65536

def reject_duplicate_keys(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise DmaError("duplicate JSON key")
        result[key]=value
    return result

def local_bytes(path:Path, max_size:int)->bytes:
    # Reject symlinks/special files before reading, and avoid CLI auto-upload.
    try:
        info=path.lstat()
    except OSError as e:
        raise DmaError("local capture file not accessible") from e
    if not stat.S_ISREG(info.st_mode) or info.st_size<=0 or info.st_size>max_size:
        raise DmaError("local capture file must be a bounded ordinary file")
    try:
        data=path.read_bytes()
    except OSError as e:
        raise DmaError("local capture file could not be read") from e
    if len(data)!=info.st_size:
        raise DmaError("capture changed while reading")
    return data

def local_json(path:Path,max_size:int)->dict:
    raw=local_bytes(path,max_size)
    try:
        obj=json.loads(raw.decode("utf-8"),object_pairs_hook=reject_duplicate_keys)
    except (ValueError,UnicodeError) as e:
        raise DmaError("invalid capture JSON") from e
    if not isinstance(obj,dict):
        raise DmaError("capture JSON must be an object")
    return obj

def check_context(context:dict,frames:int):
    if not isinstance(context,dict) or set(context)!=CTX_KEYS:
        raise DmaError("capture context has missing or extra fields")
    if context["schema"]!=CONTEXT_SCHEMA:
        raise DmaError("capture context schema mismatch")
    if type(context["method"])!=str or context["method"] not in METHODS:
        raise DmaError("capture method not recognized")
    if type(context["scope"])!=str or context["scope"] not in SCOPES:
        raise DmaError("MAP02 context not recognized")
    if type(context["reset_status"])!=str or context["reset_status"] not in RESET_STATUSES:
        raise DmaError("inter-frame GPU reset context not recognized")
    ids=context["frame_indices"]
    if (not isinstance(ids,list) or len(ids)!=frames or
        any(type(i)!=int or i<0 or i>1000000 for i in ids) or
        any(b<=a for a,b in zip(ids,ids[1:]))):
        raise DmaError("frame indices must be strictly increasing and match DMA heads")
    return True

def brief_semantics(frame):
    """No per-pixel/raster dump returned: used for comparison inside process."""
    return tuple(
        (e["type"],e.get("word"),e.get("opcode"),e.get("x0"),
         e.get("y0"),e.get("u0"),e.get("v0"),e.get("tpage"),
         e.get("semi"),e.get("mask_set"),e.get("mask_check"))
        for e in frame["events"])

def audit_private(ram:bytes,manifest:dict,context:dict|None=None,
                  comparison:tuple[bytes,dict]|None=None):
    decoded=decode(ram,manifest)
    frames=decoded["frames"]
    if context is not None:check_context(context,len(frames))
    if decoded["source_class"]=="synthetic":
        status="synthetic_private_preflight_only"
    else:
        status="unverified_private_capture_structurally_valid"
    # Real-world reset signals are not part of a DMA2 OT RAM trace; the carried
    # E6 mask state is conditional on no missing GP1 reset/intervening GP0.
    mask_before_quad=0
    quad_count=0
    unsupported=0
    transitions=0
    between_frames=0
    running=(0,0)
    for i,frame in enumerate(frames):
        if i and running!=(0,0):
            between_frames+=1
        for e in frame["events"]:
            if e["type"]=="E6":transitions+=1
            elif e["type"]=="FT4":
                quad_count+=1
                if e["mask_set"] or e["mask_check"]:
                    mask_before_quad+=1
        running=tuple(frame["mask_state_at_end"])
    report={
        "status":status,
        "input_sha256":hashlib.sha256(ram).hexdigest(),
        "source_class":decoded["source_class"],
        "frames":len(frames),
        "dma_nodes":decoded["total_nodes"],
        "gp0_e6_commands":decoded["mask_commands"],
        "gp0_ft4_commands":quad_count,
        "ft4_commands_with_mask_active":mask_before_quad,
        "e6_state_transition_events":transitions,
        "frame_boundaries_with_nondefault_previous_mask":between_frames,
        "capture_context_supplied":context is not None,
        "capture_context_complete":context is not None,
        "game_scope_claimed_MAP02":bool(context is not None and context["scope"]=="MAP02"),
        "inter_frame_gpu_reset_unverified":True,
        "comparison_performed":False,
        "independent_capture_proven":False,
        "retail_gp0_provenance_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "raw_gpu_payload_exported":False
    }
    if comparison is not None:
        other_ram,other_manifest=comparison
        other=decode(other_ram,other_manifest)
        if len(frames)!=len(other["frames"]):
            raise DmaError("comparison capture has different frame count")
        for a,b in zip(frames,other["frames"]):
            if brief_semantics(a)!=brief_semantics(b):
                raise DmaError("comparison capture has different GP0 semantic sequence")
        report["comparison_performed"]=True
        report["comparison_semantic_order_equal"]=True
        report["comparison_identical_RAM_bytes"]=ram==other_ram
        # A matching capture is *not* independent capture provenance proof.
        report["independent_capture_proven"]=False
    return report

def main():
    p=argparse.ArgumentParser(description="Private local-only PS1 DMA2/GP0 preflight; never uploads inputs")
    p.add_argument("--ram",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--context",type=Path)
    p.add_argument("--compare-ram",type=Path)
    p.add_argument("--compare-manifest",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    report=None
    try:
        if (a.compare_ram is None)!=(a.compare_manifest is None):
            raise DmaError("comparison RAM and manifest must be supplied together")
        ram=local_bytes(a.ram,MAX_RAM)
        manifest=local_json(a.manifest,MAX_MANIFEST)
        context=local_json(a.context,MAX_CONTEXT) if a.context else None
        secondary=((local_bytes(a.compare_ram,MAX_RAM),
                    local_json(a.compare_manifest,MAX_MANIFEST))
                   if a.compare_ram is not None else None)
        report=audit_private(ram,manifest,context,secondary)
    except (DmaError,OSError,ValueError,OverflowError) as err:
        # No untrusted input details, filesystem path, GP0 words or pixel
        # samples leak into a CI or voluntarily shared summary.
        report={
            "status":"refused",
            "error_category":type(err).__name__,
            "private_capture_verified":False,
            "retail_gp0_provenance_verified":False,
            "HD_replacement_approved":False,
            "raw_gpu_payload_exported":False
        }
    result=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if a.output:
        # Refuse symlinked target and writing over any of the input paths.
        sources=[x.resolve() for x in (a.ram,a.manifest,a.context,
                   a.compare_ram,a.compare_manifest) if x is not None]
        if a.output.resolve() in sources or a.output.is_symlink():
            print("Refusing to overwrite capture input or a symlink output",file=sys.stderr)
            return 2
        try:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(result)
        except OSError:
            print("Cannot write sanitized report",file=sys.stderr)
            return 2
    print(result,end="")
    return 0 if report["status"]!="refused" else 1

if __name__=="__main__":
    raise SystemExit(main())
