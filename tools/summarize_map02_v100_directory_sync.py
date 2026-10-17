#!/usr/bin/env python3
"""v100: strict pin-only private journal directory durability audit."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v99_interrupted import summarize as summarize_v99
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("durability_post_link_directory_sync",
       "durability_post_unlink_directory_sync",
       "durability_replay_refused")

def summarize(raw:bytes):
    prev=summarize_v99(raw)
    verified=validate(raw)
    events=[json.loads(x) for x in raw.decode("ascii").splitlines()]
    starts=[i for i,e in enumerate(events) if e["kind"]==KINDS[0]]
    if len(starts)!=1:
        raise Refused("missing/duplicate v100 initial directory-fsync event")
    start=starts[0]
    tail=events[start:start+3]
    if len(tail)!=3 or tuple(e["kind"] for e in tail)!=KINDS:
        raise Refused("missing/misordered v100 native directory-fsync checkpoint")
    if any(e["kind"] in KINDS for i,e in enumerate(events)
           if not start<=i<start+3):
        raise Refused("duplicate or misplaced v100 durable private export")
    if tuple(e["value"] for e in tail)!=(2,2,1):
        raise Refused("missing post-link sync, post-unlink sync, or replay refusal")
    if tail[0]["seq"]!=prev["final_private_journal_events"]+1 or \
       start+3!=prev["final_private_journal_events"]+3:
        raise Refused("v100 did not preserve complete v99 native event sequence")
    if any(e["cycle"] or e["frame"] for e in tail):
        raise Refused("host directory fsync cannot claim emulated CPU/VBlank clock")
    if verified["events"]!=len(events) or verified["vblank_edges"]!=4:
        raise Refused("lost pinned MIPS oracle or private exporter events")
    return {
        "scope":"pinned_PCSX_host_native_posix_private_directory_fsync",
        "successful_post_hardlink_parent_directory_syncs":2,
        "successful_post_stage_unlink_parent_directory_syncs":2,
        "existing_final_filename_refused":True,
        "old_private_marker_byte_exact":True,
        "fault_injection_compiled_in_isolated_C_only":True,
        "real_power_loss_simulated":False,
        "predecessor_private_events":prev["final_private_journal_events"],
        "final_private_journal_events":start+3,
        "original_emulator_vblank_edges":4,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    a=p.parse_args()
    try: print(json.dumps(summarize(a.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as ex:
        p.exit(2,f"REFUSED: {ex}\n")
if __name__=="__main__":main()
