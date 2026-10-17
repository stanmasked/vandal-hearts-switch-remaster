#!/usr/bin/env python3
"""v95 fail-closed audit of eight original native cached journal roundtrips."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v94_cached_snapshot import summarize as summarize_v94
from .verify_map02_v82_native_trace import Refused,validate

ROUND_KINDS=tuple(f"append_round_{i}" for i in range(1,9))
TOTAL_KINDS=("append_prefix_checks","append_memory_exports",
             "append_exact_rebuilds","append_stale_refusals",
             "append_stable_reads")
KINDS=ROUND_KINDS+TOTAL_KINDS
EXPECTED=tuple(range(1,9))+(8,16,8,8,8)

def summarize(raw:bytes):
    preceding=summarize_v94(raw)
    proof=validate(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    tail=rows[-len(KINDS):]
    if len(tail)!=len(KINDS) or tuple(row["kind"] for row in tail)!=KINDS:
        raise Refused("missing, duplicated or misordered v95 incremental serialization suffix")
    if any(row["kind"] in KINDS for row in rows[:-len(KINDS)]):
        raise Refused("duplicated or misplaced v95 roundtrip counter")
    if tuple(row["value"] for row in tail)!=EXPECTED:
        raise Refused("native repeated serialization/snapshot counts disagree")
    if any(row["frame"]!=0 or row["cycle"]!=0 for row in tail):
        raise Refused("host-only cache operations fabricated MIPS/VBlank provenance")
    if tail[0]["seq"]!=preceding["final_private_journal_events"]+1:
        raise Refused("v95 rounds must start immediately after v94 snapshot check")
    if len(rows)!=preceding["final_private_journal_events"]+len(KINDS):
        raise Refused("unexpected records inserted during eight exclusive memory exports")
    if proof["vblank_edges"]!=4 or not preceding["native_stale_view_invalidation_observed"]:
        raise Refused("previous pinned emulator oracle or v94 snapshot proof invalid")
    return {
        "provenance":"host_only_pinned_PCSX_post_GPUfreeze_serialization_replay",
        "incremental_append_rounds":8,
        "verified_byte_exact_JSONL_prefixes":8,
        "private_in_memory_JSONL_serializations":16,
        "native_exact_single_rebuilds":8,
        "native_stale_view_refusals":8,
        "native_cached_pointer_stable_reads":8,
        "v94_checkpoint_private_events":preceding["final_private_journal_events"],
        "final_private_journal_events":len(rows),
        "first_oracle_emulator_vblank_edges":proof["vblank_edges"],
        "real_private_file_published_exclusively_once":True,
        "retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    a=p.parse_args()
    try: result=summarize(a.private_jsonl.read_bytes())
    except (OSError,Refused,UnicodeError) as e:
        p.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
