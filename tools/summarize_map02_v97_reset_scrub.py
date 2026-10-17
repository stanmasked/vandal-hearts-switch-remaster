#!/usr/bin/env python3
"""v97 private native journal lifetime, scrubbed serializer and prefix audit.

Real journal remains the pinned four-VBlank oracle, not a post-reset trace.
Destructive reset checks are isolated C ABI regressions.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v96_boundary import summarize as summarize_v96
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("reset_observer_epoch","reset_serializer_scrubbed_bytes",
       "reset_stable_replays")
BUFFER_SIZE=524288

def summarize(raw:bytes):
    previous=summarize_v96(raw)
    evidence=validate(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    starts=[i for i,e in enumerate(events) if e["kind"]==KINDS[0]]
    if len(starts)!=1:
        raise Refused("missing/duplicate v97 observer epoch checkpoint")
    start=starts[0]
    suffix=events[start:start+3]
    if len(suffix)!=3 or tuple(e["kind"] for e in suffix)!=KINDS:
        raise Refused("missing/misordered v97 stable observer reset-era checkpoint")
    if any(e["kind"] in KINDS for i,e in enumerate(events)
           if not start<=i<start+3):
        raise Refused("duplicate or misplaced reset-era private observations")
    epoch,buffer_bytes,replays=(e["value"] for e in suffix)
    if epoch<1 or buffer_bytes!=BUFFER_SIZE or replays!=2:
        raise Refused("observer lifetime or reusable private JSONL scrub mismatch")
    if suffix[0]["seq"]!=previous["private_events"]+1:
        raise Refused("v97 must follow the full verified v96 GPU journal without resetting it")
    if start+3!=previous["private_events"]+3:
        raise Refused("unexpected extra records on the original pinned host journal")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in suffix):
        raise Refused("host-only reset-era probe forged emulator CPU/VBlank provenance")
    if evidence["events"]!=len(events) or evidence["vblank_edges"]!=4:
        raise Refused("pinned MIPS oracle/tracer lost before private final export")
    return {
        "scope":"pinned_PCSX_live_pre_reset_epoch_and_zeroed_private_serialization_reuse",
        "observer_epoch":epoch,
        "verified_scrubbed_output_buffer_bytes":BUFFER_SIZE,
        "initial_identical_in_memory_replays":2,
        "native_C_reset_erasure_proven_separately":True,
        "live_four_emulator_VBlanks_preserved":True,
        "previous_checkpoint_events":previous["private_events"],
        "final_private_journal_events":start+3,
        "retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try: print(json.dumps(summarize(args.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as exc:
        parser.exit(2,f"REFUSED: {exc}\n")
if __name__=="__main__":main()
