#!/usr/bin/env python3
"""v98 native private publisher unique-path recovery and strict host journal."""
import json
import argparse
from pathlib import Path
from .summarize_map02_v97_reset_scrub import summarize as summarize_v97
from .verify_map02_v82_native_trace import validate,Refused

KINDS=("recovery_old_path_refused","recovery_new_path_published",
       "recovery_replay_refused")
VALUES=(1,1,1)

def summarize(raw:bytes):
    prior=summarize_v97(raw)
    report=validate(raw)
    events=[json.loads(l) for l in raw.decode("ascii").splitlines()]
    final=events[-3:]
    if len(final)!=3 or tuple(e["kind"] for e in final)!=KINDS:
        raise Refused("missing/misordered native unique-private-recovery suffix")
    if any(e["kind"] in KINDS for e in events[:-3]):
        raise Refused("duplicate private-recovery evidence")
    if tuple(e["value"] for e in final)!=VALUES:
        raise Refused("old, fresh or duplicate-recovery publisher check failed")
    if final[0]["seq"]!=prior["final_private_journal_events"]+1 or \
       len(events)!=prior["final_private_journal_events"]+3:
        raise Refused("v98 must follow v97 intact without resetting its four-VBlank oracle")
    if any(e["frame"] or e["cycle"] for e in final):
        raise Refused("host-only private publication fabricated emulator clock")
    if report["events"]!=len(events) or report["vblank_edges"]!=4:
        raise Refused("missing original pinned emulator private event proof")
    return {
        "provenance":"pinned_PCSX_host_private_recovery_file_exclusivity_after_GPUfreeze",
        "preexisting_private_file_rejected":True,
        "new_private_filename_published_exclusively":True,
        "duplicate_new_private_filename_rejected":True,
        "prior_private_file_unchanged_byte_exact":True,
        "private_recovery_marker_files_removed_in_host_smoke":True,
        "four_original_emulator_vblank_edges":4,
        "previous_checkpoint_events":prior["final_private_journal_events"],
        "final_private_journal_events":len(events),
        "retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try: print(json.dumps(summarize(args.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,Refused,UnicodeError) as e:p.exit(2,f"REFUSED: {e}\n")
if __name__=="__main__":main()
