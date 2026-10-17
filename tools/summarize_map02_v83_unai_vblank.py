#!/usr/bin/env python3
"""Aggregate privately captured pinned Unai GP0 handler events by VBlank edge.

Output contains NO GPU opcode words, address, pixel color or proprietary data.
"""
import argparse
import json
from pathlib import Path
from .verify_map02_v82_native_trace import validate,Refused

def summarize(raw: bytes):
    proof=validate(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[e for e in events if e["kind"]=="vblank"]
    handled=[e for e in events if e["kind"]=="gp0_unai_handled"]
    if len(edges)!=4 or not handled:
        raise Refused("missing four real VBlank edges or renderer handlers")
    before=sum(e["seq"]<edges[0]["seq"] for e in handled)
    after=sum(e["seq"]>edges[-1]["seq"] for e in handled)
    intervals=[]
    for start,end in zip(edges,edges[1:]):
        intervals.append({
            "from_emulated_frame":start["frame"],
            "to_emulated_frame":end["frame"],
            "unai_handler_events":sum(start["seq"]<e["seq"]<end["seq"] for e in handled)
        })
    assert before+after+sum(x["unai_handler_events"] for x in intervals)==len(handled)
    return {
       "provenance":"pinned_pcsx_unai_synthetic_renderer_handler_observation",
       "emulator_vblank_edges":len(edges),
       "gp0_unai_handled":len(handled),
       "before_first_vblank":before,
       "between_vblanks":intervals,
       "after_last_vblank":after,
       "commands_completed_pixel_change_verified":False,
       "physical_ps1_vblank_verified":False,
       "original_retail_MAP02_verified":False,
       "HD_replacement_approved":False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_trace",type=Path)
    a=p.parse_args()
    try: summary=summarize(a.private_trace.read_bytes())
    except (OSError,Refused,UnicodeError) as e:
        p.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(summary,sort_keys=True))

if __name__=="__main__":
    main()
