#!/usr/bin/env python3
"""Create an opt-in, fail-closed original-PC native-VRAM WritePixel probe.

Produces a PATCHED COPY of upstream pc_raster.c; never modifies the source in
place. The resulting C build requires a caller-provided witness sink through
VH_MAP02_PIXEL_PROBE. It records native VRAM only; hires remains untouched.
This capture is diagnostic scaffolding, not gameplay or PS1 hardware proof.
"""
import argparse
from pathlib import Path

ANCHOR = '''    if (x < 0 || x >= VRAM_W || y < 0 || y >= VRAM_H) return;
    WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);'''
REPLACE = '''    if (x < 0 || x >= VRAM_W || y < 0 || y >= VRAM_H) return;
#ifdef VH_MAP02_PIXEL_PROBE
    {
        unsigned short before = s_vram[y][x];
        int accurate = AccurateEnabled() ? 1 : 0;
        WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);
        /* The sink must be provided by the opt-in private harness.
         * Never log pixel values into CI or public artifacts. */
        vh_map02_native_writepixel(x, y, before, c, s_vram[y][x],
                                  abr, !!semiTrans, !!textured, accurate);
    }
#else
    WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);
#endif'''
DECL_ANCHOR = 'static void PutPixel(const RenderCtx *rc, int x, int y, unsigned short c, int abr, int semiTrans, int textured) {'
DECL = '''#ifdef VH_MAP02_PIXEL_PROBE
/* Private observer; link fails if caller has not supplied an implementation.
 * Observer must be non-recursive and its output must be bounded. */
extern void vh_map02_native_writepixel(int x, int y, unsigned short before,
        unsigned short front, unsigned short after, int abr, int semi,
        int textured, int accurate);
#endif

'''


def instrument(source):
    if source.count(ANCHOR) != 1 or source.count(DECL_ANCHOR) != 1:
        raise ValueError("upstream PutPixel source changed; refuse ambiguous patch")
    if "VH_MAP02_PIXEL_PROBE" in source:
        raise ValueError("source already instrumented")
    return source.replace(DECL_ANCHOR, DECL + DECL_ANCHOR, 1).replace(ANCHOR, REPLACE, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("upstream_source", type=Path)
    ap.add_argument("patched_copy", type=Path)
    args = ap.parse_args()
    if args.upstream_source.resolve() == args.patched_copy.resolve():
        ap.error("cannot patch original in place")
    try:
        raw = args.upstream_source.read_text(encoding="utf-8")
        result = instrument(raw)
        if args.patched_copy.exists():
            raise ValueError("output exists; refuse overwrite")
        args.patched_copy.write_text(result, encoding="utf-8")
    except (OSError, ValueError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    main()
