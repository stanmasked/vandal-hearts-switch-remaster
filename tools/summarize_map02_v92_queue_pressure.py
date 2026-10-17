#!/usr/bin/env python3
"""v92 strict private audit of real async try_dma queue use and native writes.

One pinned host-only pressure scene = 16 CPU->VRAM A0 uploads, each 8192
16-bit stores. It distinguishes queue acceptance from synchronous fallback,
requires all native worker/sync stores, and a zero-word post-freeze queue.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v91_mode_cycles import summarize as summarize_v91
from .verify_map02_v82_native_trace import Refused,validate

KINDS=(
    "pressure_tried","pressure_accepted","pressure_idle_fallback",
    "pressure_full_fallback","pressure_peak_words",
    "pressure_worker_completed","pressure_worker_stores",
    "pressure_sync_stores","pressure_pending_words",
    "pressure_worker_same","pressure_sync_same",
)
WORD_CAPACITY=32768
PIXELS_PER_UPLOAD=8192
NUM_UPLOADS=16

def summarize(raw:bytes):
    earlier=summarize_v91(raw)
    validate(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    starts=[i for i,e in enumerate(events) if e["kind"]==KINDS[0]]
    if len(starts)!=1:
        raise Refused("missing/duplicate queue-pressure first event")
    start=starts[0]
    tail=events[start:start+len(KINDS)]
    if len(tail)!=len(KINDS) or tuple(e["kind"] for e in tail)!=KINDS:
        raise Refused("missing or reordered post-drain native DMA queue metrics")
    if any(e["kind"] in KINDS for i,e in enumerate(events)
           if not start<=i<start+len(KINDS)):
        raise Refused("duplicate or misplaced A0 queue-pressure aggregate")
    tried,accepted,idle,full,peak,done,worker,sync,pending,ws,ss=(
        e["value"] for e in tail)
    if tried!=NUM_UPLOADS or not 1<=accepted<=NUM_UPLOADS:
        raise Refused("missing real native GPU async DMA admission attempt")
    if idle+full+accepted!=NUM_UPLOADS:
        raise Refused("idle/full/success accounting excludes a DMA submission")
    if not 4099<=peak<=WORD_CAPACITY:
        raise Refused("native ring peak lies outside accepted 4099-word packet bounds")
    if pending!=0 or done!=accepted:
        raise Refused("some GPU DMA worker commands remain uncompleted after GPUfreeze")
    if worker!=PIXELS_PER_UPLOAD*done:
        raise Refused("worker did not actually write every accepted 16-bit pixel")
    if sync!=PIXELS_PER_UPLOAD*(NUM_UPLOADS-accepted):
        raise Refused("native synchronous fallback writes not fully accounted")
    if ws>worker or ss>sync or ws+ss!=PIXELS_PER_UPLOAD*(NUM_UPLOADS-1):
        raise Refused("same/new destination values do not match repeated upload scene")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in tail):
        raise Refused("host-only queue metrics forged MIPS cycle or VBlank frame")
    prev=max(e["seq"] for e in events if e["kind"]=="cycle2_sync_same")
    if tail[0]["seq"]<=prev:
        raise Refused("host pressure probe logged before both mode cycles")
    if not earlier["first_cycle_VRAM_preserved_after_second_callback_transition"]:
        raise Refused("predecessor GPU cycle readback failed")
    return {
        "scope":"actual_pinned_gpulib_host_GP0_A0_DMA_pressure_after_four_MIPS_emulator_VBlanks",
        "host_A0_uploads":tried,
        "async_queue_accepted":accepted,
        "native_idle_to_sync_fallback":idle,
        "native_full_to_sync_fallback":full,
        "gpu_ring_capacity_words":WORD_CAPACITY,
        "observed_native_ring_peak_words":peak,
        "post_GPUfreeze_pending_queue_words":pending,
        "real_worker_completions":done,
        "actual_worker_16bit_store_assignments":worker,
        "actual_sync_fallback_16bit_store_assignments":sync,
        "actual_worker_same_value_assignments":ws,
        "actual_sync_same_value_assignments":ss,
        "all_host_16bit_assignments_verified":worker+sync==NUM_UPLOADS*PIXELS_PER_UPLOAD,
        "native_GPUfreeze_VRAM_readback_required":True,
        "forced_full_queue_condition_proven":full>0,
        "actual_gpu_ring_overrun_proven":False,
        "full_retail_MAP02_verified":False,
        "physical_PS1_equivalence_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("private_jsonl",type=Path)
    args=ap.parse_args()
    try: r=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as ex:
        ap.exit(2,f"REFUSED: {ex}\n")
    print(json.dumps(r,sort_keys=True))
if __name__=="__main__":main()
