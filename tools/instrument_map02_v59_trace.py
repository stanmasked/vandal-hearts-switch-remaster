#!/usr/bin/env python3
"""v59: instrument *real* original trace replay with opt-in per-frame hashes.

Exact-anchor edit on v58 disposable PC-port ONLY. Does not change VHT1 trace
bytes, recording format, normal replay signature or game code in upstream.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_gpu_mask_v57 import once

def modify(root: Path, apply: bool):
    p=root/"platform/pc/src/pc_gpu_trace.c"
    if not p.is_file():raise ValueError(f"original GPU trace source missing: {p}")
    orig=p.read_text()
    s=once(orig,
        "            fh = TrcVramHash();\n"
        "            if (hashHires) { unsigned long long hh = TrcHiresHash(); combined ^= hh; combined *= 1099511628211ull; }\n"
        "            combined ^= fh; combined *= 1099511628211ull;",
        "            fh = TrcVramHash();\n"
        "            {\n"
        "                int v59 = getenv(\"VH_MAP02_V59_TRACE_FRAMES\") != NULL;\n"
        "                unsigned long long hh = 0;\n"
        "                if (hashHires || v59) hh = TrcHiresHash();\n"
        "                if (hashHires) { combined ^= hh; combined *= 1099511628211ull; }\n"
        "                if (v59) printf(\"V59FRAME phase=replay frame=%u nativehash=%016llx hihash=%016llx\\n\",\n"
        "                                frame, fh, hh);\n"
        "            }\n"
        "            combined ^= fh; combined *= 1099511628211ull;",
        "pc_gpu_trace.c")
    if apply:p.write_text(s)
    return f"{p.relative_to(root)}: {len(s)-len(orig):+d} bytes"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("pcport",type=Path)
    mx=ap.add_mutually_exclusive_group(required=True)
    mx.add_argument("--check",action="store_true")
    mx.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    try: result=modify(args.pcport,args.apply)
    except (OSError,ValueError) as e:ap.error(str(e))
    print(("PATCHED" if args.apply else "PATCH-READY")+" v59 original trace frame observer: "+result)
    return 0

if __name__=="__main__":raise SystemExit(main())
