#!/usr/bin/env python3
"""Fully synthetic GP0-DMA/GP1 observed-*style* event journal fixture.

The emission of a sequence-numbered GP1_WRITE record here is simulated;
it is not a hardware/emulator trace. The event contract is intended for
instrumentation adapters to populate from their own captured port writes,
followed by local-only cross-validation. No original-game bytes used.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .make_map02_v63_state_fixture import generate as generate_state
from .audit_map02_v64_event_journal import SCHEMA,seal_events,words_hash
from .verify_map02_v60_ps1_dma import walk_dma

def generate():
    ram,manifest,gp1=generate_state()
    by_frame={e["before_frame"]:e["word"] for e in gp1["events"]}
    records=[]
    tick=100
    for index,head in enumerate(manifest["entry_points"]):
        if index in by_frame:
            records.append({"tick":tick,"kind":"GP1_WRITE",
                            "before_frame":index,"word":by_frame[index]})
            tick+=10
        words,_=walk_dma(ram,manifest["base_address"],head)
        records.append({"tick":tick,"kind":"GP0_DMA2","frame":index,
                        "head":head,"gp0_word_count":len(words),
                        "gp0_sha256":words_hash(words)})
        tick+=10
    return ram,manifest,{
        "schema":SCHEMA,"source_class":"synthetic",
        "ram_sha256":manifest["sha256"],
        "initial_state":"power-on-assumed",
        "events":seal_events(records)
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ram",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--journal",type=Path,required=True)
    a=p.parse_args()
    ram,manifest,journal=generate()
    for f in (a.ram,a.manifest,a.journal):f.parent.mkdir(parents=True,exist_ok=True)
    a.ram.write_bytes(ram)
    a.manifest.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    a.journal.write_text(json.dumps(journal,sort_keys=True,indent=2)+"\n")
    print("SYNTHETIC_V64_ORDERED_JOURNAL frames=4 events=6 GP0_DMA2=4 GP1_WRITE=2")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
