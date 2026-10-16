#!/usr/bin/env python3
"""V41 diagnostic-only patch on top of v39/v40, in a disposable pinned checkout.

Make the frame identity immutable, carried by RenderCtx for both native and
deferred hires paths. Without this, OT tokens recycled across frames make
sample/primitive correlation ambiguous. No rasterized pixel is changed.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

PIN = "14552fffa0e0b47e02b57592e274fc6e7a649923"
HEADER = "platform/pc/src/pc_gpu_internal.h"
GPU = "platform/pc/src/libgpu.c"
RASTER = "platform/pc/src/pc_raster.c"


def once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchored location, found {count}")
    return source.replace(old, new, 1)


def patch_header(src: str) -> str:
    if "v41Frame" in src:
        raise ValueError("v41 frame already present")
    return once(src,
                "    unsigned int v40Token, v40Gfx, v40Route;",
                "    unsigned int v40Token, v40Gfx, v40Route;\n"
                "    unsigned int v41Frame; /* copied per-primitive to every hi-res worker */",
                "deferred render context")


def patch_gpu(src: str) -> str:
    if "v41Frame" in src:
        raise ValueError("v41 frame already present")
    if "rcn.v40Token = rcn.v40Gfx = rcn.v40Route = 0;" not in src:
        raise ValueError("v40 native context initialization missing")
    return once(src,
                "            rcn.v40Token = rcn.v40Gfx = rcn.v40Route = 0;",
                "            rcn.v40Token = rcn.v40Gfx = rcn.v40Route = 0;\n"
                "            rcn.v41Frame = s_drawFrame;",
                "snapshot original DrawOTag frame before rch = rcn")


def patch_raster(src: str) -> str:
    if "v41Frame" in src:
        raise ValueError("v41 frame already present")
    if "[v39-terrain-dda] token=%u" not in src or "[v40-terrain-hires] token=%u" not in src:
        raise ValueError("missing v39/v40 DDA observer; apply both first")
    src = once(src,
               "[v39-terrain-dda] token=%u",
               "[v39-terrain-dda] f=%u token=%u",
               "native DDA frame field")
    src = once(src,
               "VH_Map02V39Token, VH_Map02V39Gfx, VH_Map02V39Route,",
               "cx->rc->v41Frame, VH_Map02V39Token, VH_Map02V39Gfx, VH_Map02V39Route,",
               "native DDA argument list")
    src = once(src,
               "[v40-terrain-hires] token=%u",
               "[v40-terrain-hires] f=%u token=%u",
               "worker DDA frame field")
    src = once(src,
               "cx->rc->v40Token, cx->rc->v40Gfx, cx->rc->v40Route,",
               "cx->rc->v41Frame, cx->rc->v40Token, cx->rc->v40Gfx, cx->rc->v40Route,",
               "worker DDA argument list")
    if "hp->rc = *rch;" not in src or "RenderCtx rc = hp->rc;" not in src:
        raise ValueError("per-primitive hi-res context contract missing")
    return src


def apply(root: Path) -> None:
    rev = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if rev != PIN:
        raise ValueError(f"expected pinned upstream {PIN}; found {rev}")
    transform = {HEADER: patch_header, GPU: patch_gpu, RASTER: patch_raster}
    changes = {
        path: patch((root / path).read_text(encoding="utf-8"))
        for path, patch in transform.items()
    }
    # All three transformations verified before any mutations.
    for path, changed in changes.items():
        (root / path).write_text(changed, encoding="utf-8")
    print("v41 installed: frame-tagged native/hires DDA, pixel path unchanged")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--apply", action="store_true",
                        help="required: alters only the supplied disposable checkout")
    args = parser.parse_args()
    if not args.apply:
        parser.error("refusing to edit without --apply")
    apply(args.upstream.resolve(strict=True))


if __name__ == "__main__":
    main()
