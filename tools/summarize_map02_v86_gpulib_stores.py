#!/usr/bin/env python3
"""v86 private aggregate audit: MIPS A0 upload vs post-oracle host 80 copy.

Raw GPU and pixel values are never returned; totals are capped native counters.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v85_native_stores import summarize as summarize_v85
from .verify_map02_v82_native_trace import Refused

KEYS=(
    "gpulib_a0_store_count",
    "gpulib_a0_same_count",
    "gpulib_copy_store_count",
    "gpulib_copy_same_count",
)

def summarize(raw:bytes):
    inherited=summarize_v85(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    starts=[i for i,e in enumerate(rows) if e["kind"]==KEYS[0]]
    if len(starts)!=1:
        raise Refused("missing/duplicate first gpulib aggregate event")
    start=starts[0]
    observed=rows[start:start+4]
    if len(observed)!=4 or tuple(e["kind"] for e in observed)!=KEYS:
        raise Refused("misordered gpulib aggregate observations")
    if any(e["kind"] in KEYS for i,e in enumerate(rows)
           if not start<=i<start+4):
        raise Refused("duplicate/misplaced gpulib aggregate events")
    u,us,c,cs=(e["value"] for e in observed)
    if not (u>us>0 and c==32 and cs==16):
        raise Refused("signed fixture A0 or host copy counts do not match")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in observed):
        raise Refused("gpulib aggregate timestamp assertion")
    if not all(e["seq"]>max(x["seq"] for x in rows if x["kind"]=="vblank")
               for e in rows[-4:]):
        raise Refused("host copy probe must follow all four VBlank edges")
    return {
        "scope":"pinned_pcsx_synthetic_gp0_A0_and_host_GP0_80_after_original_oracle",
        "emulator_vblank_edges":4,
        "mips_a0_16bit_store_assignments":u,
        "mips_a0_same_value_assignments":us,
        "mips_a0_new_value_assignments":u-us,
        "host_gp0_80_copy_16bit_store_assignments":c,
        "host_gp0_80_copy_same_value_assignments":cs,
        "host_gp0_80_copy_new_value_assignments":c-cs,
        "host_gp0_80_submitted_by_interpreted_MIPS":False,
        "host_gp0_80_submitted_after_vblank_4":True,
        "unai_innerloop_16bit_stores":inherited["native_store_attempts"],
        "asynchronous_GPU_paths_covered":False,
        "retail_MAP02_verified":False,
        "HD_replacement_approved":False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try: answer=summarize(args.private_jsonl.read_bytes())
    except (OSError,Refused,UnicodeError) as e:p.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(answer,sort_keys=True))
if __name__=="__main__":main()
