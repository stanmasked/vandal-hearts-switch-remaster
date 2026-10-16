#!/usr/bin/env python3
"""v58: guard-patch OT-native GP0(E6) state primitive into v57's disposable PC-port.

Explicitly synthetic PC-port DR_MASK primitive; NOT PlayStation DMA/GP0 packet decoding.
Must run AFTER tools/apply_map02_gpu_mask_v57.py and on pinned upstream.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from .apply_map02_gpu_mask_v57 import once


def modify(root: Path, apply: bool) -> list[str]:
    paths = [
        root/"platform/pc/include/PsyQ/libgpu.h",
        root/"platform/pc/src/libgpu.c",
        root/"platform/pc/src/pc_gpu_trace.c",
    ]
    for p in paths:
        if not p.is_file():
            raise ValueError(f"missing original source: {p}")
    original={p:p.read_text() for p in paths}
    out=dict(original)

    p=paths[0]
    s=out[p]
    s=once(s,
        "} DR_MODE; /* Drawing Mode */",
        """} DR_MODE; /* Drawing Mode */

/* PC-port-only OT wrapper for a literal GP0(E6) word; never reinterpret a
 * retail PS1 DMA packet as this synthetic extension without a decoder. */
typedef struct {
    u32 tag;
    u_char r0, g0, b0, code;
    unsigned int command;
} DR_MASK;
""",p.name)
    s=once(s,
        "#define PC_GPU_PRIM_DR_MODE  5",
        "#define PC_GPU_PRIM_DR_MODE  5\n#define PC_GPU_PRIM_DR_MASK  6 /* synthetic PC-port OT state packet */",
        p.name)
    s=once(s,
        "void SetDrawMode(DR_MODE *p, int dfe, int dtd, int tpage, RECT *tw);",
        "void SetDrawMode(DR_MODE *p, int dfe, int dtd, int tpage, RECT *tw);\n"
        "void PC_SetDrawMaskPacket(DR_MASK *p, unsigned command);",
        p.name)
    out[p]=s

    p=paths[1]
    s=out[p]
    s=once(s,
        "void SetDrawMode(DR_MODE *p, int dfe, int dtd, int tpage, RECT *tw) {",
        """/* Constructs a PC-port-specific OT packet that carries one literal E6 word.
 * Reserved bits are not sanitized: DrawOTag must reject invalid commands. */
void PC_SetDrawMaskPacket(DR_MASK *p, unsigned command) {
    memset(p, 0, sizeof(*p));
    p->command = command;
    setcode(p, PC_GPU_PRIM_DR_MASK);
}

void SetDrawMode(DR_MODE *p, int dfe, int dtd, int tpage, RECT *tw) {""",
        p.name)
    s=once(s,
        "            case PC_GPU_PRIM_DR_MODE: {",
        """            case PC_GPU_PRIM_DR_MASK: {
                DR_MASK *m = (DR_MASK *)cur;
                /* OT order: snapshot state at each subsequent primitive.
                 * Invalid E6 is ignored, never allowed to alter mask state. */
                (void)PC_GpuGp0MaskE6(m->command);
                break;
            }
            case PC_GPU_PRIM_DR_MODE: {""",
        p.name)
    out[p]=s

    p=paths[2]
    s=out[p]
    s=once(s,
        "    case PC_GPU_PRIM_DR_MODE:  return (u32)sizeof(DR_MODE);",
        "    case PC_GPU_PRIM_DR_MODE:  return (u32)sizeof(DR_MODE);\n"
        "    case PC_GPU_PRIM_DR_MASK:  return (u32)sizeof(DR_MASK);",
        p.name)
    out[p]=s

    if apply:
        for p in paths:
            p.write_text(out[p])
    return [f"{p.relative_to(root)}: {len(out[p])-len(original[p]):+d} bytes" for p in paths]


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("pcport",type=Path)
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check",action="store_true")
    group.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    try:
        changes=modify(args.pcport,args.apply)
    except (ValueError,OSError) as e:
        ap.error(str(e))
    print(("PATCHED" if args.apply else "PATCH-READY")+
          " v58 synthetic OT-order GP0(E6): "+"; ".join(changes))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
