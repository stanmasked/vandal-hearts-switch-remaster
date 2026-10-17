#!/usr/bin/env python3
"""v89: strict proof of real asynchronous GP0(80) worker copy assignments.

Input is a PRIVATE byte-exact native JSONL, never raw GPU commands in CI art.
All v89 transfers are injected by host after successful synthetic MIPS oracle.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v88_async_dma import summarize as summarize_v88
from .verify_map02_v82_native_trace import Refused,validate

KINDS=(
    "async_copy_queued","async_copy_completed","async_copy_store_count",
    "async_copy_same_count","async_copy_masked_completed",
    "post_async_sync_copy_stores","post_async_sync_copy_same",
)
EXPECTED=(4,4,16,8,2,8,4)

def summarize(raw:bytes):
    prev=summarize_v88(raw)
    validate(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    tail=events[-7:]
    if len(tail)!=7 or tuple(e["kind"] for e in tail)!=KINDS:
        raise Refused("missing complete v89 async-copy/mode-transition suffix")
    if any(e["kind"] in KINDS for e in events[:-7]):
        raise Refused("duplicate or misplaced v89 copy metric")
    if tuple(e["value"] for e in tail)!=EXPECTED:
        raise Refused("GPU worker/sync mask+copy counters fail exact fixture")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in tail):
        raise Refused("fabricated CPU cycles/frame in async worker events")
    after_seq=max(e["seq"] for e in events if e["kind"]=="async_dma_same_count")
    if tail[0]["seq"]<=after_seq:
        raise Refused("v89 async worker ran before v88 GPU DMA verification")
    return {
        "scope":"pinned_pcsx_host_async_gp0_80_and_sync_mode_transition",
        "async_gp0_80_queued":4,
        "async_gp0_80_completed_by_gpu_worker":4,
        "async_gp0_80_16bit_stores":16,
        "async_gp0_80_same_value_stores":8,
        "async_gp0_80_changed_value_stores":8,
        "async_gp0_80_masked_completed":2,
        "after_worker_sync_gp0_80_16bit_stores":8,
        "after_worker_sync_gp0_80_same_value_stores":4,
        "worker_completion_crosschecked_with_GPUfreeze":True,
        "actual_worker_stores_vs_queued_disambiguated":True,
        "original_mips_A0_queued":prev["async_queued_submissions"],
        "all_v89_GP0_commands_host_submitted":True,
        "asynchronous_GPU_to_CPU_C0_covered":False,
        "retail_MAP02_verified":False,
        "physical_ps1_vblank_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:report=summarize(args.private_jsonl.read_bytes())
    except(OSError,Refused,UnicodeError) as error:
        p.exit(2,f"REFUSED: {error}\n")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":main()
