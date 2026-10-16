#!/usr/bin/env python3
"""Instrument the pinned PC-port's deferred hi-res list with immutable terrain tags.

Run only AFTER the v39 tagged-OT instrumenter in a disposable checkout.
No pixels are replaced. No shared mutable "current primitive" is read by
raster threads: provenance is a field of the RenderCtx snapshot carried by
HiresPrim, then copied independently for each worker band.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

PIN = "14552fffa0e0b47e02b57592e274fc6e7a649923"
HEADER = "platform/pc/src/pc_gpu_internal.h"
GPU = "platform/pc/src/libgpu.c"
RASTER = "platform/pc/src/pc_raster.c"


def once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected one source anchor, got {n}")
    return src.replace(old, new, 1)


def modify_header(src: str) -> str:
    if "v40Token" in src:
        raise ValueError("v40 already installed in RenderCtx")
    anchor = "    int scale;                        /* geometry x scale when target==1 (else effectively 1) */"
    return once(src, anchor, anchor + "\n"
                "    /* Immutable per-FT4 terrain provenance: copied into HiresPrim and worker bands. */\n"
                "    unsigned int v40Token, v40Gfx, v40Route;",
                "RenderCtx hi-res provenance fields")


def modify_gpu(src: str) -> str:
    if "v40Token" in src:
        raise ValueError("v40 already installed in GPU dispatcher")
    if "VH_Map02V39Active = 1;" not in src:
        raise ValueError("apply v39 OT provenance first")
    src = once(src,
               "            rcn.target = 0; rcn.scale = 1;",
               "            rcn.target = 0; rcn.scale = 1;\n"
               "            rcn.v40Token = rcn.v40Gfx = rcn.v40Route = 0;",
               "initialize every primitive")
    src = once(src,
               "                    VH_Map02V39Active = 1;",
               "                    VH_Map02V39Active = 1;\n"
               "                    /* Snapshot tag into this FT4's deferred hi-res context. */\n"
               "                    rch.v40Token = nextTok;\n"
               "                    rch.v40Gfx = v39Tag.gfx;\n"
               "                    rch.v40Route = v39Tag.route;",
               "tag only verified terrain FT4")
    if src.count("rch = rcn; rch.target = 1; rch.scale = hiScale;") != 1:
        raise ValueError("GPU RenderCtx native-to-hires copy changed")
    if src.count("HiresAppendQuad(&rch, a, b, c, d, q->r0, q->g0, q->b0, 1,") != 1:
        raise ValueError("deferred textured-quad path changed")
    return src


def modify_raster(src: str) -> str:
    if "v40Token" in src:
        raise ValueError("v40 already installed in deferred rasterizer")
    if "VH_Map02V39Active" not in src:
        raise ValueError("apply v39 observer first")
    for anchor, expected in (
        ("hp->rc = *rch;", 2),  # both quad and rect snapshot their own context
        ("RenderCtx rc = hp->rc;", 1),
        ("HiresRasterizeBand(s_hpool.band[id].clipY, s_hpool.band[id].clipH);", 1),
    ):
        if src.count(anchor) != expected:
            raise ValueError(f"hires immutable snapshot contract changed: {anchor}")
    anchor = "            if (draw) {                                      /* 0000h = transparent (skip, still step) */"
    new = (
        "            /* V40: worker-safe hi-res observation from *per-primitive* RenderCtx. */\n"
        "            if (cx->rc->target && cx->rc->v40Token && !cx->hdPx &&\n"
        "                (current_x & 63) == 0 && (y & 63) == 0)\n"
        "                fprintf(stderr,\n"
        "                    \"[v40-terrain-hires] token=%u gfx=%u route=%u x=%d y=%d u=%d v=%d raw=%u draw=%d semi=%d abr=%d scale=%d\\n\",\n"
        "                    cx->rc->v40Token, cx->rc->v40Gfx, cx->rc->v40Route,\n"
        "                    current_x, y, su, sv, draw ? (unsigned)texel : 0u,\n"
        "                    draw, cx->semiTrans, cx->abr, cx->rc->scale);\n"
    )
    return once(src, anchor, new + anchor, "actual DDA hi-res texel selection")


def run(root: Path) -> None:
    rev = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if rev != PIN:
        raise ValueError("expected upstream commit " + PIN)
    paths = {HEADER: modify_header, GPU: modify_gpu, RASTER: modify_raster}
    # Construct all changes before any writes, so a mismatch leaves tree intact.
    transformed = {}
    for path, func in paths.items():
        transformed[path] = func((root / path).read_text(encoding="utf-8"))
    for path, content in transformed.items():
        (root / path).write_text(content, encoding="utf-8")
    print("V40 installed in disposable upstream checkout: RenderCtx -> HiresPrim -> DDA")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("upstream", type=Path)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if not args.apply:
        p.error("refusing to modify sources without --apply")
    run(args.upstream.resolve(strict=True))


if __name__ == "__main__":
    main()
