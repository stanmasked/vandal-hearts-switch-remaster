#!/usr/bin/env python3
"""Add fail-closed in-memory v81 JSONL formatter to a pinned v80 checkout.

No runtime export file or original gameplay capture is produced by this patch.
"""
from pathlib import Path
import shutil
from .apply_map02_v80_pcsx_rearmed import apply as apply_v80
from .apply_map02_v69_pcsx_rearmed import once

def apply(root: Path):
    proof=apply_v80(root)
    base=root.resolve()
    make=base/"Makefile"
    old=make.read_text()
    updated=once(old,
        'OBJS += libpcsxcore/vh80_native_timeline.o\n',
        'OBJS += libpcsxcore/vh80_native_timeline.o\n'
        'OBJS += libpcsxcore/vh81_event_jsonl.o\n',
        "native v81 JSONL object")
    local=Path(__file__).resolve().parent
    additions={
       base/"libpcsxcore/vh81_event_jsonl.c":local/"map02_v81_event_jsonl.c",
       base/"libpcsxcore/vh81_event_jsonl.h":local/"map02_v81_event_jsonl.h",
    }
    if any(target.exists() for target in additions):
        raise ValueError("refusing existing v81 upstream files")
    if any(not src.is_file() for src in additions.values()):
        raise ValueError("missing v81 source")
    make.write_text(updated)
    for target,src in additions.items():shutil.copyfile(src,target)
    return dict(proof, native_jsonl_formatter_source_installed=True,
        live_v81_export_verified=False, native_gp0_consumption_verified=False,
        native_vram_write_trace_verified=False,
        original_retail_MAP02_verified=False, HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
