#!/usr/bin/env python3
"""Generate opt-in DrawOTag frame/primitive provenance hooks in copied libgpu.c.

Pairs with instrument_map02_scoped_blend.py on pristine upstream pc_raster.c.
The frame and DRAW-only ordinal come from the actual synchronous OT walker.
A private sink records only one explicitly selected frame and XY coordinate.
No original game resources or captures are bundled.
"""
import argparse
from pathlib import Path

MACRO = "VH_MAP02_SCOPED_BLEND_PROBE"
ENTRY = "void DrawOTag(unsigned int *p) {"
FRAME = "    s_drawFrame++;"
WALK = "    while (nextTok) {"
PRIM = "        if (!isBucket) {"
PRIM_END = "        }\n        nextTok = rawTagOfCur;"
INVALID_TOKEN = "            break;\n        }\n        rawTagOfCur = ((P_TAG *)cur)->tag;"
CYCLE = "        if (++walkSteps > 1000000UL) {"
END = "    TrcFrameEnd();"

DECLARATIONS = r"""#if defined(VH_MAP02_VRAM_EDGE_PROBE) && !defined(VH_MAP02_SCOPED_BLEND_PROBE)
#error "VRAM edge sampling requires selected-frame DrawOTag scope"
#endif
#ifdef VH_MAP02_VRAM_EDGE_PROBE
#include "map02_vram_edges.h"
#endif
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
/* Link to the bounded private sink, not to a public capture artifact. */
extern void vh_map02_scope_reset(void);
extern void vh_map02_scope_abort(void);
extern int vh_map02_scope_begin_frame(unsigned frame, int x, int y);
extern int vh_map02_scope_begin_primitive(unsigned ordinal,
                                             unsigned primitive_type);
extern int vh_map02_scope_end_primitive(void);
extern int vh_map02_scope_end_frame(void);
#ifdef VH_MAP02_POSIX_STAGE
extern int vh_map02_stage_private_pair(const char *private_directory);
#endif

/* Decimal-only environment configuration: no default target, no capture.
 * Every value is checked in full, with explicit upper bounds.
 * Malformed opt-in configuration invalidates the private sink. */
static int vh_map02_decimal(const char *s, unsigned long maximum,
                            unsigned long *value) {
    unsigned long out = 0;
    if (!s || !*s) return 0;
    while (*s) {
        unsigned digit;
        if (*s < '0' || *s > '9') return 0;
        digit = (unsigned)(*s++ - '0');
        if (out > (maximum - digit) / 10UL) return 0;
        out = out * 10UL + digit;
    }
    *value = out;
    return 1;
}

static int vh_map02_choose_frame(unsigned frame, int *x, int *y) {
    const char *fs = getenv("VH_MAP02_PROBE_FRAME");
    const char *xs = getenv("VH_MAP02_PROBE_X");
    const char *ys = getenv("VH_MAP02_PROBE_Y");
    unsigned long target, px, py;
    if (!fs && !xs && !ys) return 0;
    if (!vh_map02_decimal(fs, 4294967295UL, &target) || !target ||
        !vh_map02_decimal(xs, 1023UL, &px) ||
        !vh_map02_decimal(ys, 511UL, &py)) return -1;
    *x = (int)px;
    *y = (int)py;
    return (unsigned long)frame == target ? 1 : 0;
}
#endif

"""
ENTRY_NEW = r"""void DrawOTag(unsigned int *p) {
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    unsigned vh_scope_ordinal = 0;
    int vh_scope_active = 0, vh_scope_x = 0, vh_scope_y = 0;
#endif"""
FRAME_NEW = r"""    s_drawFrame++;
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    {
        int selection = vh_map02_choose_frame(s_drawFrame,
                                             &vh_scope_x, &vh_scope_y);
        if (selection < 0) {
            vh_map02_scope_reset();
            vh_map02_scope_abort();
#ifdef VH_MAP02_VRAM_EDGE_PROBE
            vh_map02_edges_reset();
            vh_map02_edges_abort();
#endif
        } else if (selection > 0) {
            vh_map02_scope_reset();
            vh_scope_active = vh_map02_scope_begin_frame(
                s_drawFrame, vh_scope_x, vh_scope_y);
            if (!vh_scope_active) vh_map02_scope_abort();
#ifdef VH_MAP02_VRAM_EDGE_PROBE
            vh_map02_edges_reset();
            if (!vh_map02_edges_begin_frame(s_drawFrame,
                                            vh_scope_x, vh_scope_y))
                vh_map02_edges_abort();
#endif
        }
    }
#endif"""
PRIM_NEW = r"""        if (!isBucket) {
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
            /* The verified native-VRAM event stream counts only DRAW
             * operations. DR_MODE and unknown packets must not advance
             * the ordinal used by the independent VRAM snapshot join. */
            int vh_scope_type = PC_GPU_PRIM_TYPE((P_TAG *)cur);
            int vh_scope_is_draw =
                vh_scope_type == PC_GPU_PRIM_POLY_F4 ||
                vh_scope_type == PC_GPU_PRIM_POLY_FT4 ||
                vh_scope_type == PC_GPU_PRIM_SPRT ||
                vh_scope_type == PC_GPU_PRIM_TILE;
            if (vh_scope_active && vh_scope_is_draw &&
                !vh_map02_scope_begin_primitive(
                    vh_scope_ordinal, (unsigned)vh_scope_type))
                vh_map02_scope_abort();
#ifdef VH_MAP02_VRAM_EDGE_PROBE
            if (vh_scope_active && vh_scope_is_draw &&
                !vh_map02_edges_begin_primitive(
                    vh_scope_ordinal, (unsigned)vh_scope_type,
                    PC_GpuVram()[vh_scope_y][vh_scope_x]))
                vh_map02_edges_abort();
#endif
            if (vh_scope_is_draw) vh_scope_ordinal++;
#endif"""
PRIM_END_NEW = r"""#ifdef VH_MAP02_SCOPED_BLEND_PROBE
#ifdef VH_MAP02_VRAM_EDGE_PROBE
            if (vh_scope_active && vh_scope_is_draw &&
                !vh_map02_edges_end_primitive(
                    PC_GpuVram()[vh_scope_y][vh_scope_x]))
                vh_map02_edges_abort();
#endif
            if (vh_scope_active && vh_scope_is_draw &&
                !vh_map02_scope_end_primitive())
                vh_map02_scope_abort();
#endif
        }
        nextTok = rawTagOfCur;"""
INVALID_NEW = r"""#ifdef VH_MAP02_SCOPED_BLEND_PROBE
            if (vh_scope_active) vh_map02_scope_abort();
#ifdef VH_MAP02_VRAM_EDGE_PROBE
            if (vh_scope_active) vh_map02_edges_abort();
#endif
#endif
            break;
        }
        rawTagOfCur = ((P_TAG *)cur)->tag;"""
CYCLE_NEW = r"""        if (++walkSteps > 1000000UL) {
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
            if (vh_scope_active) vh_map02_scope_abort();
#ifdef VH_MAP02_VRAM_EDGE_PROBE
            if (vh_scope_active) vh_map02_edges_abort();
#endif
#endif"""
END_NEW = r"""#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    /* Close before deferred hi-res workers run. Their pixels are excluded. */
    if (vh_scope_active) {
        if (!vh_map02_scope_end_frame())
            vh_map02_scope_abort();
#ifdef VH_MAP02_VRAM_EDGE_PROBE
        if (!vh_map02_edges_end_frame())
            vh_map02_edges_abort();
#endif
#ifdef VH_MAP02_POSIX_STAGE
        else {
            const char *private_dir = getenv("VH_MAP02_PROBE_OUTPUT_DIR");
            if (private_dir &&
                (!*private_dir || !vh_map02_stage_private_pair(private_dir)))
                vh_map02_scope_abort();
        }
#endif
    }
#endif
    TrcFrameEnd();"""


def instrument(source):
    if not isinstance(source, str):
        raise ValueError("original libgpu source must be text")
    # The synthetic harness uses #ifdef VH_MAP02_SCOPED_BLEND_PROBE
    # in its own assertions. Only reject actual installed instrumentation.
    if ("static int vh_map02_decimal(" in source or
            "unsigned vh_scope_ordinal = 0;" in source):
        raise ValueError("libgpu source already instrumented")
    for anchor in (ENTRY, FRAME, WALK, PRIM, PRIM_END,
                   INVALID_TOKEN, CYCLE, END):
        if source.count(anchor) != 1:
            raise ValueError("missing or ambiguous original DrawOTag anchor")
    patched = source.replace(ENTRY, DECLARATIONS + ENTRY_NEW, 1)
    # Replacement of the full invalid-token segment comes BEFORE PRIM_END
    # so that a broken OT walk is explicitly marked incomplete.
    for before, after in (
        (FRAME, FRAME_NEW),
        (INVALID_TOKEN, INVALID_NEW),
        (PRIM, PRIM_NEW),
        (PRIM_END, PRIM_END_NEW),
        (CYCLE, CYCLE_NEW),
        (END, END_NEW),
    ):
        patched = patched.replace(before, after, 1)
    return patched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_libgpu", type=Path)
    parser.add_argument("patched_copy", type=Path)
    args = parser.parse_args()
    if args.upstream_libgpu.resolve() == args.patched_copy.resolve():
        parser.error("refuse modification in place")
    try:
        result = instrument(args.upstream_libgpu.read_text(encoding="utf-8"))
        with args.patched_copy.open("x", encoding="utf-8") as output:
            output.write(result)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
