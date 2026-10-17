#!/usr/bin/env python3
"""v103 signed MAP02 private proof: intermediate symlink and inode guard."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v102_anchored_paths import summarize as summarize_v102
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("safe_parent_component_walks","safe_final_inode_verified",
       "safe_parent_symlink_refused")

def summarize(raw:bytes):
    previous=summarize_v102(raw)
    validated=validate(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    tail=rows[-3:]
    if len(tail)!=3 or tuple(row["kind"] for row in tail)!=KINDS:
        raise Refused("missing/misordered v103 safely resolved file identity suffix")
    if any(row["kind"] in KINDS for row in rows[:-3]):
        raise Refused("duplicate or interleaved v103 file guard evidence")
    if tuple(row["value"] for row in tail)!=(12,4,1):
        raise Refused("v103 component walk/verified inodes/symlink refusal mismatch")
    if tail[0]["seq"]!=previous["final_private_journal_events"]+1 or \
       len(rows)!=previous["final_private_journal_events"]+3:
        raise Refused("v103 does not preserve pinned v102 MIPS/GPU checkpoint")
    if any(row["cycle"] or row["frame"] for row in tail):
        raise Refused("host path checks cannot claim real emulated VBlank time")
    if validated["events"]!=len(rows) or validated["vblank_edges"]!=4:
        raise Refused("pinned emulator VBlank observations missing")
    return {
        "provenance":"pinned_PCSX_original_GPUfreeze_then_host_private_file_inode_guard",
        "real_parent_path_component_checks_at_least":12,
        "successful_original_committed_file_verifications":4,
        "intermediate_symlink_rejected_inside_native_emulator":True,
        "identical_byte_inode_replacement_refused_in_isolated_native_C":True,
        "openat_directory_components_nofollow":True,
        "only_owned_private_test_markers_removed":True,
        "original_four_emulator_vblanks":4,
        "previous_checkpoint_events":previous["final_private_journal_events"],
        "final_private_journal_events":len(rows),
        "real_retail_MAP02_verified":False,
        "physical_ps1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:print(json.dumps(summarize(args.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
if __name__=="__main__":main()
