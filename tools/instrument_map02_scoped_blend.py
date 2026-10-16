#!/usr/bin/env python3
"""Make ONE opt-in native-VRAM-only PutPixel/BlendG1 source instrumentation.

Both original isolated generators require pristine pc_raster.c and cannot be
stacked. This generator binds begin -> actual BlendG1 call -> end within the
same native PutPixel invocation; it never creates a fabricated BlendG1 event.
The private callback implementation and authenticated DrawOTag context are
separate requirements, not provided by this patch.
"""
import argparse
from pathlib import Path

WRITE_SIGNATURE = ("static void WritePixel(unsigned short *px, int x, int y, "
                   "unsigned short c, int abr, int semiTrans, int textured) {")
PUT_SIGNATURE = ("static void PutPixel(const RenderCtx *rc, int x, int y, "
                 "unsigned short c, int abr, int semiTrans, int textured) {")
HIRES = "WritePixel(&s_hires[(size_t)y * W + x], x, y, c, abr, semiTrans, textured);"
NATIVE = "WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);"
NATIVE_ANCHOR = ("    if (x < 0 || x >= VRAM_W || y < 0 || y >= VRAM_H) return;\n"
                 "    " + NATIVE)
BLEND_CALL = "            *px = BlendG1((unsigned)c | 0x8000u, *px, abr, textured);"
MACRO = "VH_MAP02_SCOPED_BLEND_PROBE"

DECLARATIONS = """#ifdef VH_MAP02_SCOPED_BLEND_PROBE
/* Private, nonrecursive, bounded callbacks. Capture only a selected native
 * coordinate; do not write raw game pixels into public build artifacts.
 * The surrounding DrawOTag harness must independently supply frame/ordinal.
 */
extern void vh_map02_probe_begin(int x, int y, unsigned short before,
        unsigned short front, int abr, int semi, int textured, int accurate);
extern void vh_map02_probe_blendg1(int x, int y, unsigned short fg,
        unsigned short bg, unsigned short result, int abr, int textured);
extern void vh_map02_probe_end(int x, int y, unsigned short after);
#endif

"""

BLEND_REPLACEMENT = """#ifdef VH_MAP02_SCOPED_BLEND_PROBE
            if (nativeTarget) {
                unsigned short fg = (unsigned short)((unsigned)c | 0x8000u);
                unsigned short bg = *px;
                unsigned short result = BlendG1(fg, bg, abr, textured);
                *px = result;
                vh_map02_probe_blendg1(x, y, fg, bg, result, abr, textured);
            } else {
                *px = BlendG1((unsigned)c | 0x8000u, *px, abr, textured);
            }
#else
            *px = BlendG1((unsigned)c | 0x8000u, *px, abr, textured);
#endif"""

NATIVE_REPLACEMENT = """    if (x < 0 || x >= VRAM_W || y < 0 || y >= VRAM_H) return;
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    {
        unsigned short before = s_vram[y][x];
        int accurate = AccurateEnabled() ? 1 : 0;
        vh_map02_probe_begin(x, y, before, c, abr,
                             !!semiTrans, !!textured, accurate);
        WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured, 1);
        vh_map02_probe_end(x, y, s_vram[y][x]);
    }
#else
    WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured, 1);
#endif"""


def instrument(source):
    """Patch verified exact source anchors; leave source intact on failure."""
    if not isinstance(source, str):
        raise ValueError("upstream source must be text")
    if any(flag in source for flag in (
            MACRO, "VH_MAP02_PIXEL_PROBE", "VH_MAP02_BLENDG1_PROBE")):
        raise ValueError("source already instrumented; use pristine upstream")
    for anchor in (WRITE_SIGNATURE, PUT_SIGNATURE, HIRES,
                   NATIVE_ANCHOR, BLEND_CALL):
        if source.count(anchor) != 1:
            raise ValueError("missing or ambiguous original source anchor")
    # This API change is always applied (in both preprocessor branches), so
    # all C calls have the same arity regardless of the diagnostic macro.
    new_signature = WRITE_SIGNATURE.replace(
        "int textured) {", "int textured, int nativeTarget) {")
    patched = source.replace(WRITE_SIGNATURE,
                             DECLARATIONS + new_signature + "\n#ifndef " + MACRO + "\n    (void)nativeTarget;\n#endif", 1)
    patched = patched.replace(
        HIRES, HIRES.replace("textured);", "textured, 0);"), 1)
    patched = patched.replace(BLEND_CALL, BLEND_REPLACEMENT, 1)
    patched = patched.replace(NATIVE_ANCHOR, NATIVE_REPLACEMENT, 1)
    return patched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_source", type=Path)
    parser.add_argument("patched_copy", type=Path)
    args = parser.parse_args()
    if args.upstream_source.resolve() == args.patched_copy.resolve():
        parser.error("refuse to overwrite original source")
    try:
        source = args.upstream_source.read_text(encoding="utf-8")
        patched = instrument(source)
        # "x" prevents accidental overwrite (also on races).
        with args.patched_copy.open("x", encoding="utf-8") as handle:
            handle.write(patched)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
