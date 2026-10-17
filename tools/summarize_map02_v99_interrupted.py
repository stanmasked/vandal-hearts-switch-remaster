#!/usr/bin/env python3
"""Strict v99 audit: interrupted POSIX private stage is not a final journal."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v98_recovery import summarize as summarize_v98
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("interrupted_stage_refused","interrupted_fresh_published",
       "interrupted_stage_preserved")

def summarize(raw:bytes):
    previous=summarize_v98(raw)
    trace=validate(raw)
    events=[json.loads(x) for x in raw.decode("ascii").splitlines()]
    positions=[i for i,e in enumerate(events) if e["kind"]==KINDS[0]]
    if len(positions)!=1:
        raise Refused("missing or duplicate v99 interrupted stage first event")
    start=positions[0]
    tail=events[start:start+3]
    if len(tail)!=3 or tuple(e["kind"] for e in tail)!=KINDS:
        raise Refused("missing/misordered v99 interrupted private stage checkpoint")
    if any(e["kind"] in KINDS for i,e in enumerate(events)
           if not start<=i<start+3):
        raise Refused("duplicate or misplaced v99 interrupted stage observation")
    if tuple(e["value"] for e in tail)!=(1,1,1):
        raise Refused("incomplete .tmp refused/fresh recovery/immutability assertion failed")
    if tail[0]["seq"]!=previous["final_private_journal_events"]+1 or \
       start+3!=previous["final_private_journal_events"]+3:
        raise Refused("v99 resumed without original signed MIPS/v98 GPU oracle")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in tail):
        raise Refused("host private file operation cannot claim emulated CPU/frame")
    if trace["events"]!=len(events) or trace["vblank_edges"]!=4:
        raise Refused("incomplete source v80 four real emulator VBlank observations")
    return {
        "scope":"pinned_PCSX_host_only_interrupted_private_file_recovery",
        "incomplete_stage_refused_for_original_final_path":True,
        "only_distinct_unoccupied_target_accepted":True,
        "existing_staged_data_remained_byte_exact":True,
        "duplicate_recovered_target_refused":True,
        "test_marker_files_privately_cleaned":True,
        "existing_v82_protected_final_export_still_required":True,
        "four_real_emulator_vblank_callbacks":4,
        "earlier_v98_checkpoint_entries":previous["final_private_journal_events"],
        "final_private_journal_events":start+3,
        "authentic_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try: print(json.dumps(summarize(args.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as err:
        parser.exit(2,f"REFUSED: {err}\n")
if __name__=="__main__":main()
