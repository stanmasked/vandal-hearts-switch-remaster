#!/usr/bin/env python3
"""v49: read-only ORIGINAL source VRAM word+CLUT snapshots before PutPixel.

Only tagged map-11 primitives from v48 are observed. Captures pre-write
data independently of SampleTexture, so the Python verifier can recompute
4/8/15bit address and CLUT index, including texture-window transformation.
"""
from pathlib import Path
import argparse
import subprocess

PIN="14552fffa0e0b47e02b57592e274fc6e7a649923"
SOURCE="platform/pc/src/pc_raster.c"
BLOCK='''            /* Independent pre-PutPixel source VRAM evidence.  Never alter sampling. */
            if (v48_capture && getenv("VH_MAP02_V49_TRACE") != NULL) {
                int v49_u = (su & ~(cx->rc->twMaskX * 8)) |
                            ((cx->rc->twOffX & cx->rc->twMaskX) * 8);
                int v49_v = (sv & ~(cx->rc->twMaskY * 8)) |
                            ((cx->rc->twOffY & cx->rc->twMaskY) * 8);
                int v49_tp = (cx->tpage >> 7) & 3;
                int v49_ppw = v49_tp == 0 ? 4 : (v49_tp == 1 ? 2 : 1);
                int v49_tx = (cx->tpage & 15) * 64 + v49_u / v49_ppw;
                int v49_ty = ((cx->tpage >> 4) & 1) * 256 + v49_v;
                int v49_cx = (cx->clut & 63) * 16;
                int v49_cy = (cx->clut >> 6) & 511;
                if (v49_tx >= 0 && v49_tx < VRAM_W &&
                    v49_ty >= 0 && v49_ty < VRAM_H) {
                    unsigned short v49_word = s_vram[v49_ty][v49_tx];
                    int v49_index = v49_tp == 0
                        ? (v49_word >> ((v49_u & 3) * 4)) & 15
                        : (v49_tp == 1
                            ? (v49_word >> ((v49_u & 1) * 8)) & 255
                            : -1);
                    unsigned short v49_palette = 0;
                    int v49_ok = v49_index < 0 ||
                        (v49_cy >= 0 && v49_cy < VRAM_H &&
                         v49_cx + v49_index >= 0 &&
                         v49_cx + v49_index < VRAM_W);
                    if (v49_ok) {
                        unsigned int v49_tok = cx->rc->target
                          ? cx->rc->v40Token : VH_Map02V39Token;
                        unsigned int v49_gfx = cx->rc->target
                          ? cx->rc->v40Gfx : VH_Map02V39Gfx;
                        unsigned int v49_route = cx->rc->target
                          ? cx->rc->v40Route : VH_Map02V39Route;
                        if (v49_index >= 0)
                            v49_palette = s_vram[v49_cy][v49_cx + v49_index];
                        fprintf(stderr,
                          "[v49-terrain-vram] f=%u token=%u gfx=%u route=%u target=%d x=%d y=%d u=%d v=%d tpage=%d clut=%d maskx=%d masky=%d offx=%d offy=%d word=%u index=%d palette=%u raw=%u\\n",
                          cx->rc->v41Frame, v49_tok, v49_gfx, v49_route,
                          cx->rc->target, current_x, y, su, sv,
                          cx->tpage, cx->clut,
                          cx->rc->twMaskX, cx->rc->twMaskY,
                          cx->rc->twOffX, cx->rc->twOffY,
                          (unsigned)v49_word, v49_index,
                          (unsigned)v49_palette, (unsigned)texel);
                    }
                }
            }
'''
def patch(src):
    if "[v49-terrain-vram]" in src: raise ValueError("v49 already installed")
    start=src.find("static void dda_span(")
    end=src.find("static void dda_part(",start)
    if start<0 or end<start or "[v48-terrain-pixel]" not in src[start:end]:
        raise ValueError("v48 must be installed on the real dda_span first")
    part=src[start:end]
    marker="            if (draw) {                                      /* 0000h = transparent (skip, still step) */"
    if part.count(marker)!=1: raise ValueError("original draw guard changed; abort")
    part=part.replace(marker,BLOCK+marker,1)
    return src[:start]+part+src[end:]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("upstream",type=Path)
    p.add_argument("--apply",action="store_true")
    a=p.parse_args()
    if not a.apply: p.error("requires --apply for disposable pinned upstream checkout")
    root=a.upstream.resolve(strict=True)
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PIN: raise ValueError("expected pinned upstream "+PIN+" got "+sha)
    file=root/SOURCE
    file.write_text(patch(file.read_text(encoding="utf-8")),encoding="utf-8")
    print("v49 read-only source VRAM/CLUT probe installed before original PutPixel")

if __name__=="__main__":
    main()
