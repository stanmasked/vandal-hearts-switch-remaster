#!/usr/bin/env python3
"""v57: bounded GP0(E6) mask-path patch for a DISPOSABLE pinned PC-port checkout.

This changes the executed original PC GPU path, NOT the public upstream repository.
No retail files or HD asset replacement are involved. Fails closed on anchor drift.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def once(source: str, old: str, new: str, path: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{path}: expected exactly one original anchor, found {count}: {old[:70]!r}")
    return source.replace(old, new, 1)


def modify(root: Path, apply: bool) -> list[str]:
    src = root / "platform/pc/src"
    paths = [src / name for name in ("pc_gpu_internal.h", "libgpu.c", "pc_raster.c")]
    for path in paths:
        if not path.is_file():
            raise ValueError(f"missing pinned original source: {path}")
    original = {p: p.read_text() for p in paths}
    out = dict(original)

    p = paths[0]
    s = out[p]
    s = once(s,
        "int PC_GpuGetInternalScale(void);",
        "int PC_GpuGetInternalScale(void);\n"
        "/* GP0(E6): set bit15 on writes / skip pixels whose destination bit15 is set.\n"
        " * Driver seam accepts an E6 command between DrawOTag calls; no packet decoder is implied. */\n"
        "int PC_GpuGp0MaskE6(unsigned command);",
        p.name)
    s = once(s,
        "    int dither;                       /* dither-enable (GP0 E1h.9) */",
        "    int dither;                       /* dither-enable (GP0 E1h.9) */\n"
        "    int maskSet, maskCheck;          /* GP0(E6), snapped before deferred HD dispatch */",
        p.name)
    out[p] = s

    p = paths[1]
    s = out[p]
    s = once(s,
        "static int s_drawModeAbr = 0;",
        "static int s_drawMaskSet = 0, s_drawMaskCheck = 0; /* GP0(E6), persistent GPU state */\n"
        "static int s_drawModeAbr = 0;",
        p.name)
    s = once(s,
        "DRAWENV *PutDrawEnv(DRAWENV *env) {",
        "/* Decode the real GP0(E6) payload, reject other commands and reserved bits.\n"
        " * The PC-port lacks a raw GP0 packet stream: callers must explicitly feed E6. */\n"
        "int PC_GpuGp0MaskE6(unsigned command) {\n"
        "    if ((command & ~3u) != 0xe6000000u) return 0;\n"
        "    s_drawMaskSet = (int)(command & 1u);\n"
        "    s_drawMaskCheck = (int)((command >> 1) & 1u);\n"
        "    return 1;\n"
        "}\n\n"
        "DRAWENV *PutDrawEnv(DRAWENV *env) {",
        p.name)
    s = once(s,
        "            rcn.dither = s_drawModeDither;",
        "            rcn.dither = s_drawModeDither;\n"
        "            rcn.maskSet = s_drawMaskSet; rcn.maskCheck = s_drawMaskCheck;",
        p.name)
    out[p] = s

    p = paths[2]
    s = out[p]
    start = "static void WritePixel(unsigned short *px, int x, int y, unsigned short c, int abr, int semiTrans, int textured) {"
    stop = "\nstatic void PutPixel(const RenderCtx *rc,"
    if s.count(start) != 1 or s.count(stop) != 1:
        raise ValueError("pc_raster.c: original WritePixel/PutPixel boundary drift")
    first = s.index(start)
    last = s.index(stop, first)
    replacement = """static void WritePixel(const RenderCtx *rc, unsigned short *px, int x, int y,
                       unsigned short c, int abr, int semiTrans, int textured) {
    unsigned short result = c;
    /* GP0(E6).1: destination test happens BEFORE semi-transparency blending. */
    if (rc->maskCheck && (*px & 0x8000u)) return;
    if (semiTrans) {
        if (AccurateEnabled()) {
            result = BlendG1((unsigned)c | 0x8000u, *px, abr, textured);
        } else {
            int r, g, b, br, bg, bb;
            UnpackColor(c, &r, &g, &b);
            UnpackColor(*px, &br, &bg, &bb);
            switch (abr) {
            case 0: r = (br + r) / 2; g = (bg + g) / 2; b = (bb + b) / 2; break;
            case 1: r = br + r; g = bg + g; b = bb + b; break;
            case 2: r = br - r; g = bg - g; b = bb - b; break;
            case 3: r = br + r / 4; g = bg + g / 4; b = bb + b / 4; break;
            }
            result = PackColorDither(r, g, b, x, y);
        }
    }
    /* GP0(E6).0: force bit15 even after a blend, without changing source STP. */
    *px = (unsigned short)(result | (rc->maskSet ? 0x8000u : 0u));
}
"""
    s = s[:first] + replacement + s[last:]
    s = once(s,
        "WritePixel(&s_hires[(size_t)y * W + x], x, y, c, abr, semiTrans, textured);",
        "WritePixel(rc, &s_hires[(size_t)y * W + x], x, y, c, abr, semiTrans, textured);",
        p.name)
    s = once(s,
        "WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);",
        "WritePixel(rc, &s_vram[y][x], x, y, c, abr, semiTrans, textured);",
        p.name)
    out[p] = s

    if apply:
        for p in paths:
            p.write_text(out[p])
    return [f"{p.relative_to(root)}: {len(out[p]) - len(original[p]):+d} bytes" for p in paths]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcport", type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    try:
        changes = modify(args.pcport, args.apply)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    print(("PATCHED" if args.apply else "PATCH-READY") + " v57 pinned GPU GP0(E6): " + "; ".join(changes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
