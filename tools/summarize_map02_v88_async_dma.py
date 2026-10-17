#!/usr/bin/env python3
"""v88: accept only matched real asynchronous DMA queue and worker counters.

The original MIPS 4-VBlank fixture stays independent; the extra
asynchronous A0 transfers are explicitly host-submitted post-oracle.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v87_gpulib_edges import summarize as summarize_v87
from .verify_map02_v82_native_trace import Refused

KINDS=("async_dma_queued","async_dma_completed",
       "async_dma_store_count","async_dma_same_count")

def summarize(raw:bytes):
    prior=summarize_v87(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    positions=[i for i,e in enumerate(rows) if e["kind"]==KINDS[0]]
    if len(positions)!=1:
        raise Refused("missing/duplicate asynchronous GPU metric block")
    start=positions[0]
    group=rows[start:start+4]
    if len(group)!=4 or tuple(e["kind"] for e in group)!=KINDS:
        raise Refused("missing or misordered post-sync async worker aggregates")
    if any(e["kind"] in KINDS for i,e in enumerate(rows)
           if not start<=i<start+4):
        raise Refused("duplicate asynchronous GPU metric events")
    queued,completed,stores,same=[e["value"] for e in group]
    if not (0<queued<=32 and completed==queued and
            stores==8*completed and 0<same<stores):
        raise Refused("queued DMA not matched by actual worker 16-bit stores")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in group):
        raise Refused("fabricated async worker CPU cycle or frame")
    if min(e["seq"] for e in group)<=max(e["seq"] for e in rows if
            e["kind"]=="gpulib_wrap_same_count"):
        raise Refused("asynchronous GPU control preceded original sync edge cases")
    return {
        "provenance":"host_submitted_async_gp0_A0_after_four_mips_vblank_oracle",
        "async_queued_submissions":queued,
        "async_worker_completed_transfers":completed,
        "async_worker_16bit_assignments":stores,
        "async_worker_same_value_assignments":same,
        "async_worker_new_value_assignments":stores-same,
        "worker_completion_verified_by_gpu_freeze":True,
        "async_GP0_80_copy_path_covered":False,
        "full_async_pipeline_coverage":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
        "v87_host_mask_verified_in_emulator":prior["host_mask_a0_16bit_stores"]==12,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    a=p.parse_args()
    try: result=summarize(a.private_jsonl.read_bytes())
    except (OSError,Refused,UnicodeError) as error:
        p.exit(2,f"REFUSED: {error}\n")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
