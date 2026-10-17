#!/usr/bin/env python3
"""v101 pinned full private journal: completed final must reopen and resync."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v100_directory_sync import summarize as summarize_v100
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("reopened_private_commits","reopened_private_parent_syncs",
       "reopened_bad_bytes_refused")

def summarize(raw:bytes):
    prev=summarize_v100(raw)
    trace=validate(raw)
    events=[json.loads(e) for e in raw.decode("ascii").splitlines()]
    starts=[i for i,e in enumerate(events) if e["kind"]==KINDS[0]]
    if len(starts)!=1:
        raise Refused("missing or duplicate first v101 private reopen event")
    start=starts[0]
    tail=events[start:start+3]
    if len(tail)!=3 or tuple(e["kind"] for e in tail)!=KINDS:
        raise Refused("missing/misordered v101 reopened private-file checkpoint")
    if any(e["kind"] in KINDS for i,e in enumerate(events)
           if not start<=i<start+3):
        raise Refused("duplicate or misplaced v101 reopened-file observation")
    if tuple(e["value"] for e in tail)!=(4,4,1):
        raise Refused("missing reread, parent resync or wrong-byte refusal")
    if tail[0]["seq"]!=prev["final_private_journal_events"]+1 or \
       start+3!=prev["final_private_journal_events"]+3:
        raise Refused("missing native v100 directory durability checkpoint")
    if any(e["frame"]!=0 or e["cycle"]!=0 for e in tail):
        raise Refused("host POSIX fsync cannot claim emulator CPU/VBlank time")
    if trace["events"]!=len(events) or trace["vblank_edges"]!=4:
        raise Refused("four pinned emulator VBlank callbacks not preserved")
    return {
        "scope":"pinned_PCSX_host_reopened_committed_private_file",
        "successful_reopened_file_byte_checks":4,
        "successful_reopened_parent_directory_fsyncs":4,
        "wrong_private_content_refused":True,
        "original_exclusive_final_publisher_verifies_before_success":True,
        "ambiguous_leftover_tmp_not_considered_committed":True,
        "recovery_requires_fresh_filename_after_failure":True,
        "fault_injection_isolated_native_C_only":True,
        "power_loss_physically_tested":False,
        "previous_checkpoint_events":prev["final_private_journal_events"],
        "final_private_journal_events":start+3,
        "original_emulator_vblank_edges":4,
        "real_retail_MAP02_verified":False,
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
