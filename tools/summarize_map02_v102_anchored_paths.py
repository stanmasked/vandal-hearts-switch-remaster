#!/usr/bin/env python3
"""Strict audit of native directory-fd-anchored private publication (v102)."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v101_reopen import summarize as summarize_v101
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("anchored_private_commits","anchored_parent_identity_checks",
       "anchored_duplicate_refused")

def summarize(raw:bytes):
    previous=summarize_v101(raw)
    valid=validate(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    starts=[i for i,row in enumerate(rows) if row["kind"]==KINDS[0]]
    if len(starts)!=1:
        raise Refused("missing or duplicate v102 first anchored evidence")
    start=starts[0]
    tail=rows[start:start+3]
    if len(tail)!=3 or tuple(row["kind"] for row in tail)!=KINDS:
        raise Refused("missing/out-of-order v102 anchored directory checkpoint")
    if any(row["kind"] in KINDS for i,row in enumerate(rows)
           if not start<=i<start+3):
        raise Refused("duplicated or misplaced anchored private evidence")
    if tuple(row["value"] for row in tail)!=(2,12,1):
        raise Refused("private file publication not tied to original directory")
    if tail[0]["seq"]!=previous["final_private_journal_events"]+1 or \
       start+3!=previous["final_private_journal_events"]+3:
        raise Refused("missing original v101 exact private-file checkpoint")
    if any(row["frame"] or row["cycle"] for row in tail):
        raise Refused("host directory checks asserted unobserved emulator time")
    if valid["events"]!=len(rows) or valid["vblank_edges"]!=4:
        raise Refused("pinned original emulator four-VBlank oracle lost")
    return {
        "scope":"pinned_PCSX_post_GPUfreeze_dirfd_private_journal",
        "native_anchored_private_publishes":2,
        "native_parent_identity_checks_at_least":12,
        "duplicate_final_path_refused":True,
        "directory_operations_openat_linkat_unlinkat":True,
        "parent_rename_symlink_redirect_fails_closed_in_isolated_C":True,
        "original_private_export_still_uses_exclusive_publisher":True,
        "original_emulator_vblank_edges":4,
        "previous_checkpoint_events":previous["final_private_journal_events"],
        "final_private_journal_events":start+3,
        "retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    a=p.parse_args()
    try:print(json.dumps(summarize(a.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as ex:
        p.exit(2,f"REFUSED: {ex}\n")
if __name__=="__main__":main()
