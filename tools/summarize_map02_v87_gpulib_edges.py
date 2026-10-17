#!/usr/bin/env python3
"""v87: fail closed on host-controlled overlap, E6-mask, X-wrap GPU cases.

No opcode/pixel data is uploaded. All v87 control commands are submitted
by the TEST HARNESS after the four original synthetic emulator VBlank edges.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v86_gpulib_stores import summarize as summarize_v86
from .verify_map02_v82_native_trace import Refused

EVENT_KINDS=(
    "gpulib_overlap_store_count",
    "gpulib_overlap_same_count",
    "gpulib_mask_upload_store_count",
    "gpulib_mask_upload_same_count",
    "gpulib_wrap_store_count",
    "gpulib_wrap_same_count",
)
EXPECT=(16,8,12,4,8,4)

def summarize(raw:bytes):
    prior=summarize_v86(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    if len(rows)<6 or tuple(e["kind"] for e in rows[-6:])!=EVENT_KINDS:
        raise Refused("missing ordered v87 host-control tail")
    if any(e["kind"] in EVENT_KINDS for e in rows[:-6]):
        raise Refused("duplicate v87 host-control events")
    tail=rows[-6:]
    actual=tuple(e["value"] for e in tail)
    if actual!=EXPECT:
        raise Refused("host overlap/mask/wrap assignment totals differ from readback oracle")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in tail):
        raise Refused("host control asserted original CPU/frame identity")
    edge_seq=max(e["seq"] for e in rows if e["kind"]=="vblank")
    v86_seq=max(e["seq"] for e in rows
                if e["kind"]=="gpulib_copy_same_count")
    if not all(e["seq"]>max(edge_seq,v86_seq) for e in tail):
        raise Refused("v87 host controls preceded VBlank or v86 observation")
    return {
        "provenance":"host_submitted_pinned_pcsx_after_signed_four_vblank_fixture",
        "host_overlap_16bit_stores":16,
        "host_overlap_same_value_stores":8,
        "host_mask_a0_16bit_stores":12,
        "host_mask_a0_same_value_stores":4,
        "host_xwrap_16bit_stores":8,
        "host_xwrap_same_value_stores":4,
        "original_mips_A0_store_count":prior["mips_a0_16bit_store_assignments"],
        "v86_original_host_copy_stores":prior["host_gp0_80_copy_16bit_store_assignments"],
        "all_v87_commands_are_host_submitted":True,
        "all_v87_commands_after_emulator_vblank_4":True,
        "playstation_hardware_mask_equivalence_proven":False,
        "retail_MAP02_verified":False,
        "HD_replacement_approved":False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try: result=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as e:
        p.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
