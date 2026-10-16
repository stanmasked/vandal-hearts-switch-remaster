#!/usr/bin/env python3
"""Generate an opt-in native-only BlendG1 entry/exit observer in a source copy.

This modifies the actual BlendG1 CALL inside WritePixel, not a reconstructed
blend. It threads the native-target boolean from PutPixel into WritePixel to
exclude the supersampled path, without global state or nonportable pointer
comparisons. The observer implementation is supplied by a private harness.
"""
import argparse
from pathlib import Path

SIGNATURE = "static void WritePixel(unsigned short *px, int x, int y, unsigned short c, int abr, int semiTrans, int textured) {"
HIRES = "WritePixel(&s_hires[(size_t)y * W + x], x, y, c, abr, semiTrans, textured);"
NATIVE = "WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);"
CALL = "            *px = BlendG1((unsigned)c | 0x8000u, *px, abr, textured);"
DECLARATION = """#ifdef VH_MAP02_BLENDG1_PROBE
/* Private, bounded observer. The harness must bind frame/primitive/step;
 * do not construct its events from a PutPixel log. */
extern void vh_map02_blendg1_call(int x, int y, unsigned short fg,
        unsigned short bg, unsigned short result, int abr, int textured);
#endif

"""
REPLACEMENT = """#ifdef VH_MAP02_BLENDG1_PROBE
            if (nativeTarget) {
                unsigned short fg = (unsigned short)((unsigned)c | 0x8000u);
                unsigned short bg = *px;
                unsigned short result = BlendG1(fg, bg, abr, textured);
                *px = result;
                vh_map02_blendg1_call(x, y, fg, bg, result, abr, textured);
            } else {
                *px = BlendG1((unsigned)c | 0x8000u, *px, abr, textured);
            }
#else
            *px = BlendG1((unsigned)c | 0x8000u, *px, abr, textured);
#endif"""


def instrument(source):
    if "VH_MAP02_BLENDG1_PROBE" in source or "VH_MAP02_PIXEL_PROBE" in source:
        raise ValueError("probe already present; use pristine upstream source")
    for anchor, count in ((SIGNATURE, 1), (HIRES, 1), (NATIVE, 1), (CALL, 1)):
        if source.count(anchor) != count:
            raise ValueError("missing or ambiguous upstream BlendG1 anchor")
    source = source.replace(SIGNATURE,
        DECLARATION + SIGNATURE.replace("int textured) {", "int textured, int nativeTarget) {"), 1)
    source = source.replace(HIRES, HIRES.replace("textured);", "textured, 0);"), 1)
    source = source.replace(NATIVE, NATIVE.replace("textured);", "textured, 1);"), 1)
    source = source.replace(CALL, REPLACEMENT, 1)
    return source


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("upstream_source", type=Path)
    p.add_argument("patched_copy", type=Path)
    a = p.parse_args()
    if a.upstream_source.resolve() == a.patched_copy.resolve():
        p.error("refuse in-place modification")
    try:
        source = a.upstream_source.read_text(encoding="utf-8")
        result = instrument(source)
        if a.patched_copy.exists():
            raise ValueError("refuse overwrite")
        a.patched_copy.write_text(result, encoding="utf-8")
    except (OSError, ValueError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
