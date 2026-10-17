#!/usr/bin/env python3
"""Independent v90 private strict per-worker GP0 A0/80/E6 ordering verifier.

Only aggregate counters and semantic worker-order fingerprint; never raw
private GPU opcodes, raw pixel samples, copyrighted retail MAP02 assets.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v89_async_copy import summarize as summarize_v89
from .verify_map02_v82_native_trace import Refused,validate

KINDS=(
    "mixed_a0_queued","mixed_a0_completed",
    "mixed_a0_store_count","mixed_a0_same_count",
    "mixed_copy_queued","mixed_copy_completed",
    "mixed_copy_store_count","mixed_copy_same_count",
    "mixed_masked_copies","mixed_worker_steps","mixed_worker_order",
    "mixed_sync_a0_store_count","mixed_sync_copy_store_count",
    "mixed_sync_copy_same_count",
)
LABELS=(1,2,3,4,5,5,6)
EXPECTED=(
    4,4,32,8,3,3,24,0,1,7,27249034,8,16,8
)

def summarize(raw:bytes):
    inherited=summarize_v89(raw)
    validate(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    tail=events[-len(KINDS):]
    if len(tail)!=len(KINDS) or tuple(e["kind"] for e in tail)!=KINDS:
        raise Refused("missing or out-of-order mixed host GPU audit suffix")
    if any(e["kind"] in KINDS for e in events[:-len(KINDS)]):
        raise Refused("duplicate/misplaced mixed GPU audit records")
    got=tuple(e["value"] for e in tail)
    if got!=EXPECTED:
        raise Refused("actual async GP0 A0/copy/mask/sync worker metrics disagree")
    hashvalue=0
    for token in LABELS:
        hashvalue=(hashvalue*17+token)&0xffffffff
    if hashvalue!=got[10]:
        raise Refused("worker order signature does not match semantic phase sequence")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in tail):
        raise Refused("host/worker GPU counters must not assert CPU cycles or VBlank frame")
    if tail[0]["seq"]<=max(e["seq"] for e in events
                            if e["kind"]=="post_async_sync_copy_same"):
        raise Refused("new host controls were logged before verified v89 GPU handoff")
    if len([e for e in events if e["kind"]=="vblank"])!=4:
        raise Refused("original emulator VBlank oracle not present")
    return {
        "provenance":"host_injected_mixed_gpu_commands_after_synthetic_four_VBlank_MIPS_oracle",
        "async_A0_accepted_by_worker_queue":got[0],
        "async_A0_completed_by_worker":got[1],
        "async_A0_native_16bit_stores":got[2],
        "async_A0_same_value_stores":got[3],
        "async_GP0_80_accepted_by_worker_queue":got[4],
        "async_GP0_80_completed_by_worker":got[5],
        "async_GP0_80_native_16bit_stores":got[6],
        "async_GP0_80_same_value_stores":got[7],
        "async_GP0_80_masked_copies":got[8],
        "worker_ordered_semantic_steps":got[9],
        "worker_order_rolling_hash":got[10],
        "after_worker_shutdown_sync_A0_stores":got[11],
        "after_worker_shutdown_sync_copy_stores":got[12],
        "after_worker_shutdown_sync_same_value_copies":got[13],
        "mixed_worker_order_proven_for_synthetic_fixture":True,
        "GPUfreeze_readback_and_stop_required":True,
        "previous_async_GP0_80_completions":inherited["async_gp0_80_completed_by_gpu_worker"],
        "retail_MAP02_verified":False,
        "physical_ps1_vblank_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:result=summarize(args.private_jsonl.read_bytes())
    except (OSError,Refused,UnicodeError) as exc:p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
