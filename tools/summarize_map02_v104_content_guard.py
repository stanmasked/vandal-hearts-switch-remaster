#!/usr/bin/env python3
"""Strict MAP02 v104 private native second-read and same-inode tamper audit."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v103_inode_guard import summarize as summarize_v103
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("content_post_sync_rechecks","content_same_inode_change_refused",
       "content_protected_publishes")
EXPECTED=(4,1,2)

def summarize(raw:bytes):
    previous=summarize_v103(raw)
    verified=validate(raw)
    rows=[json.loads(x) for x in raw.decode("ascii").splitlines()]
    suffix=rows[-3:]
    if len(suffix)!=3 or tuple(row["kind"] for row in suffix)!=KINDS:
        raise Refused("missing/misordered v104 second-read content guard suffix")
    if any(row["kind"] in KINDS for row in rows[:-3]):
        raise Refused("duplicate or misplaced content verification events")
    if tuple(row["value"] for row in suffix)!=EXPECTED:
        raise Refused("second read, same-inode corruption or no-clobber publish failed")
    if suffix[0]["seq"]!=previous["final_private_journal_events"]+1 or \
       len(rows)!=previous["final_private_journal_events"]+3:
        raise Refused("original v103 pinned GPU/VRAM journal must stay intact")
    if any(row["frame"]!=0 or row["cycle"]!=0 for row in suffix):
        raise Refused("host private filesystem check invented emulator CPU frame")
    if verified["vblank_edges"]!=4 or verified["events"]!=len(rows):
        raise Refused("original four real emulator VBlank observations are missing")
    return {
        "scope":"pinned_PCSX_post_GPUfreeze_private_file_double_readback",
        "post_fsync_full_file_reads_verified":4,
        "same_inode_changed_bytes_refused":True,
        "successfully_published_new_private_markers":2,
        "pre_post_readback_inode_metadata_checked":True,
        "isolated_native_test_mutation_phases":3,
        "real_power_interruption_tested":False,
        "original_emulator_vblank_edges":4,
        "previous_checkpoint_events":previous["final_private_journal_events"],
        "final_private_journal_events":len(rows),
        "retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try: print(json.dumps(summarize(args.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
if __name__=="__main__":main()
