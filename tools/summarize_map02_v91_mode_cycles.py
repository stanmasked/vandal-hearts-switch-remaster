#!/usr/bin/env python3
"""Audit two independent host-only GPU thread enable/stop cycles.

Proves that each async GP0(80) command really ran in the worker, GPUfreeze
drained it, and both synchronous handoffs preserve prior VRAM. A0 may
legitimately take the original synchronous fallback even with threading ON;
only accepted A0 transfers count as worker operations.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v90_mixed_order import summarize as summarize_v90
from .verify_map02_v82_native_trace import Refused,validate

FIELDS=("a0_queued","a0_done","a0_stores",
        "copy_queued","copy_done","copy_stores","copy_same",
        "masked_copy","sync_a0","sync_copy","sync_same")
KINDS=tuple(f"cycle{round}_{field}" for round in (1,2) for field in FIELDS)

def summarize(raw: bytes):
    prior=summarize_v90(raw)
    validate(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    positions=[i for i,e in enumerate(events) if e["kind"]==KINDS[0]]
    if len(positions)!=1:
        raise Refused("missing/duplicate first cycle metric")
    start=positions[0]
    tail=events[start:start+22]
    if len(tail)!=22 or tuple(x["kind"] for x in tail)!=KINDS:
        raise Refused("missing/misordered two independent GPU mode cycle observations")
    if any(e["kind"] in KINDS for i,e in enumerate(events)
           if not start<=i<start+22):
        raise Refused("duplicate or misplaced cycle metric")
    v90_last=max(x["seq"] for x in events if x["kind"]=="mixed_sync_copy_same_count")
    if tail[0]["seq"]<=v90_last:
        raise Refused("mode transitions must follow proven v90 worker order")
    reports=[]
    for round in range(2):
        seq=tail[11*round:11*(round+1)]
        q,d,stores,cq,cd,cs,css,mask,sa,sc,ss=(x["value"] for x in seq)
        if not(0<=q<=2 and q==d and stores==8*q and
               cq==cd==2 and cs==16 and css==0 and mask==1 and
               sa==8 and sc==16 and ss==8):
            raise Refused("actual worker copy or sync-mode assignment mismatch "
                          f"in cycle {round+1}")
        if any(x["cycle"]!=0 or x["frame"]!=0 for x in seq):
            raise Refused("forged CPU cycle or emulated VBlank frame in host observations")
        reports.append({
            "cycle":round+1,
            "worker_A0_accepted":q,
            "worker_A0_completed":d,
            "worker_A0_16bit_stores":stores,
            "worker_GP0_80_accepted":cq,
            "worker_GP0_80_completed":cd,
            "worker_GP0_80_16bit_stores":cs,
            "worker_GP0_80_same_value_stores":css,
            "worker_masked_GP0_80_copies":mask,
            "after_worker_shutdown_sync_A0_stores":sa,
            "after_worker_shutdown_sync_copy_stores":sc,
            "after_worker_shutdown_sync_copy_same":ss,
        })
    return {
        "scope":"two_host_submitted_async_to_sync_mode_cycles_after_four_emulator_vblanks",
        "mode_cycles":reports,
        "all_actual_worker_copies_completed":True,
        "worker_A0_synchronous_fallback_explicitly_permitted":True,
        "both_cycles_verified_by_real_GPUfreeze_readback":True,
        "first_cycle_VRAM_preserved_after_second_callback_transition":True,
        "four_original_emulator_vblank_edges":4,
        "prior_worker_completion_order_verified":prior["mixed_worker_order_proven_for_synthetic_fixture"],
        "original_retail_MAP02_verified":False,
        "physical_ps1_vblank_verified":False,
        "HD_replacement_approved":False
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try: report=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as ex:
        parser.exit(2,f"REFUSED: {ex}\n")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":main()
