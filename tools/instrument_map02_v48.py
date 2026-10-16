#!/usr/bin/env python3
"""V48 read-only per-pixel original PS1 texel/output evidence (v39-v47).

Install AFTER v47 in disposable pinned upstream. Frame + OT token stays
thread-local in deferred hires RenderCtx. Never change PutPixel or STP logic.
"""
from pathlib import Path
import argparse
import subprocess

PIN="14552fffa0e0b47e02b57592e274fc6e7a649923"
SOURCE="platform/pc/src/pc_raster.c"

def exactly(src,old,new,label):
    n=src.count(old)
    if n!=1: raise ValueError(f"{label}: expected one source anchor, saw {n}")
    return src.replace(old,new,1)

def patch_raster(src):
    if "[v48-terrain-pixel]" in src:
        raise ValueError("v48 already installed")
    if "[v40-terrain-hires]" not in src or "[v39-terrain-dda]" not in src:
        raise ValueError("apply native and deferred terrain diagnostic observers first")
    a=src.index("static void dda_span(")
    b=src.index("static void dda_part(",a)
    part=src[a:b]
    part=exactly(part,
        "            unsigned short texel;",
        "            unsigned short texel;\n"
        "            int v48_capture = 0;\n"
        "            unsigned short v48_before = 0, v48_front = 0;\n",
        "per-texel trace temporaries")
    original="            if (draw) {                                      /* 0000h = transparent (skip, still step) */"
    added=(
        "            /* Read-only, bounded probe: no reliance on mutable worker-global token. */\n"
        "            if (!cx->hdPx &&\n"
        "                ((cx->rc->target && cx->rc->v40Token &&\n"
        "                  (current_x & 63) == 0 && (y & 63) == 0) ||\n"
        "                 (!cx->rc->target && VH_Map02V39Active &&\n"
        "                  (current_x & 31) == 0 && (y & 31) == 0)) &&\n"
        "                getenv(\"VH_MAP02_V48_TRACE\") != NULL) {\n"
        "                if (cx->rc->target) {\n"
        "                    int W = VRAM_W * cx->rc->scale, H = VRAM_H * cx->rc->scale;\n"
        "                    if (current_x >= 0 && current_x < W && y >= 0 && y < H) {\n"
        "                        v48_capture = 1;\n"
        "                        v48_before = s_hires[(size_t)y * W + current_x];\n"
        "                    }\n"
        "                } else if (current_x >= 0 && current_x < VRAM_W &&\n"
        "                           y >= 0 && y < VRAM_H) {\n"
        "                    v48_capture = 1;\n"
        "                    v48_before = s_vram[y][current_x];\n"
        "                }\n"
        "            }\n"
        + original
    )
    part=exactly(part,original,added,"capture before original PutPixel")
    call="                PutPixel(cx->rc, current_x, y,\n"
    part=exactly(part,call,
        "                if (v48_capture)\n"
        "                    v48_front = (AccurateEnabled() && cx->rc->dither)\n"
        "                        ? PackColorG1Front(tr, tg, tb, current_x, y)\n"
        "                        : PackColor(tr, tg, tb);\n"
        +call,"reference front color for original PutPixel")
    term=(
        "            }\n"
        "        } else {\n"
        "            PutPixel(cx->rc, current_x, y,"
    )
    # Full record is emitted AFTER original PutPixel, including transparent
    # texel skips. The output is a snapshot, not an additional paint operation.
    output=(
        "            }\n"
        "            if (v48_capture) {\n"
        "                unsigned short v48_after = cx->rc->target\n"
        "                    ? s_hires[(size_t)y * (VRAM_W * cx->rc->scale) + current_x]\n"
        "                    : s_vram[y][current_x];\n"
        "                unsigned int frame = cx->rc->v41Frame;\n"
        "                unsigned int tok = cx->rc->target ? cx->rc->v40Token : VH_Map02V39Token;\n"
        "                unsigned int gfx = cx->rc->target ? cx->rc->v40Gfx : VH_Map02V39Gfx;\n"
        "                unsigned int route = cx->rc->target ? cx->rc->v40Route : VH_Map02V39Route;\n"
        "                fprintf(stderr,\n"
        "                  \"[v48-terrain-pixel] f=%u token=%u gfx=%u route=%u target=%d x=%d y=%d u=%d v=%d raw=%u draw=%d front=%u before=%u after=%u semi=%d abr=%d dither=%d mr=%d mg=%d mb=%d scale=%d\\n\",\n"
        "                  frame, tok, gfx, route, cx->rc->target, current_x, y,\n"
        "                  su, sv, (unsigned)texel, draw, (unsigned)v48_front,\n"
        "                  (unsigned)v48_before, (unsigned)v48_after,\n"
        "                  cx->semiTrans, cx->abr,\n"
        "                  (AccurateEnabled() && cx->rc->dither) ? 1 : 0,\n"
        "                  cx->r, cx->g, cx->bcol, cx->rc->scale);\n"
        "            }\n"
        "        } else {\n"
        "            PutPixel(cx->rc, current_x, y,"
    )
    part=exactly(part,term,output,"capture after original GPU pixel write")
    return src[:a]+part+src[b:]

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PIN: raise ValueError(f"require exact public upstream {PIN}, got {sha}")
    path=root/SOURCE
    new=patch_raster(path.read_text(encoding="utf-8"))
    path.write_text(new,encoding="utf-8")
    print("V48 pixel probe installed: raw BGR555 → modulation → front → original PutPixel → after")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("upstream",type=Path)
    p.add_argument("--apply",action="store_true")
    a=p.parse_args()
    if not a.apply: p.error("only disposable checked-out files with --apply")
    apply(a.upstream.resolve(strict=True))

if __name__=="__main__":
    main()
