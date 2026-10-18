#!/usr/bin/env python3
"""Opt-in v39 terrain provenance instrumentation for pinned US PC-port source.

Apply only in a disposable checkout after tools.make_map02_trace_patch has
already been applied. No game data or HD texel substitution.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

PIN = "14552fffa0e0b47e02b57592e274fc6e7a649923"
GRAPHICS = "src/core/graphics.c"
LIBGPU = "platform/pc/src/libgpu.c"
RASTER = "platform/pc/src/pc_raster.c"
HEADER = "platform/pc/src/vh_map02_v39_tokens.h"
GPU_SHA = "9d0fab71c45ed09dda072cfeacd557ab9c5d81e5"
RASTER_SHA = "ba8a05d161ad778c0b75e452ff0a11ed163c65cd"


def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, got {count}")
    return text.replace(old, new, 1)


def terrain_graphics(text):
    text = once(
        text, '#include "PsyQ/gtemac.h"\n',
        '#include "PsyQ/gtemac.h"\n'
        '#if defined(PC_FEAT) && defined(VH_MAP02_V39_TRACE)\n'
        'extern void PC_Map02V39MarkSubmitted(void *, void *, int, int, int);\n'
        '#endif\n', "terrain forward declaration"
    )
    sections = [
        ("RenderMapTile", "RenderEdgeMapTile", 1),
        ("RenderEdgeMapTile", "RenderOverheadMapTile", 2),
        ("RenderOverheadMapTile", "GetBestViewOfTarget", 3)
    ]
    for name, end_name, route in sections:
        start_marker = f"void {name}("
        end_marker = ("\ns32 " if route == 3 else "\nvoid ") + f"{end_name}("
        start = text.find(start_marker)
        end = text.find(end_marker, start)
        if start < 0 or end <= start:
            raise ValueError(f"missing {name} function bounds")
        section = text[start:end]
        anchor = "AddPrim(ot + OT_SIZE - otz, poly);"
        replacement = (
            anchor + "\n"
            "#if defined(PC_FEAT) && defined(VH_MAP02_V39_TRACE)\n"
            "         if (gState.mapNum == 11)\n"
            f"            PC_Map02V39MarkSubmitted(ot + OT_SIZE - otz, poly, gfx, (int)gState.mapNum, {route});\n"
            "#endif"
        )
        section = once(section, anchor, replacement, f"terrain {name} AddPrim")
        text = text[:start] + section + text[end:]
    return text


def libgpu(text):
    text = once(text, '#include "PsyQ/libgpu.h"\n',
                '#include "PsyQ/libgpu.h"\n'
                '#include "vh_map02_v39_tokens.h"\n',
                "include v39 header")
    text = once(text, 'static int s_otOverflowed;  /* latched, so the warning prints once per frame */',
                'static int s_otOverflowed;  /* latched, so the warning prints once per frame */\n'
                'static VhMap02V39Tag s_v39Tags[PC_OT_MAX_TOKENS];\n'
                'volatile unsigned VH_Map02V39Active = 0;\n'
                'volatile unsigned VH_Map02V39Token = 0;\n'
                'volatile unsigned VH_Map02V39Gfx = 0;\n'
                'volatile unsigned VH_Map02V39Route = 0;\n'
                'static int s_v39TraceEnabled = -1;',
                "tag storage")
    text = once(text, '    s_otIsBucket[s_otTokens] = (unsigned char)isBucket;',
                '    s_otIsBucket[s_otTokens] = (unsigned char)isBucket;\n'
                '    vh_map02_v39_clear(s_v39Tags, PC_OT_MAX_TOKENS, s_otTokens);',
                "reset on token reuse")
    insertion = r'''
/* Tag precisely the token most recently emitted by AddPrim, not UV/CLUT. */
void PC_Map02V39MarkSubmitted(void *ot, void *prim, int gfx, int mapnum, int route) {
    if (!ot || !prim) return;
    vh_map02_v39_mark(s_v39Tags, PC_OT_MAX_TOKENS, s_otTokens,
                      s_otPtr[s_otTokens], s_otIsBucket[s_otTokens],
                      ((P_TAG *)ot)->tag, prim, mapnum, gfx, (unsigned int)route);
}

'''
    text = once(text, '    ((P_TAG *)ot)->tag = PC_OtMint(p, 0);\n}',
                '    ((P_TAG *)ot)->tag = PC_OtMint(p, 0);\n}' + insertion,
                "AddPrim mark API")
    text = once(text, '    TrcInit();\n    s_drawFrame++;',
                '    TrcInit();\n'
                '    if (s_v39TraceEnabled < 0)\n'
                '        s_v39TraceEnabled = getenv("VH_MAP02_V39_TRACE") ? 1 : 0;\n'
                '    s_drawFrame++;', "environment opt-in")
    anchor = ('                FillQuad(&rcn, a, b, c, d, q->r0, q->g0, q->b0, 1, '
              'q->tpage, q->clut, semi, (q->tpage >> 5) & 3);')
    pre = (
        '                VhMap02V39Tag v39Tag;\n'
        '                VH_Map02V39Active = 0;\n'
        '                if (s_v39TraceEnabled &&\n'
        '                    vh_map02_v39_get(s_v39Tags, PC_OT_MAX_TOKENS, nextTok,\n'
        '                                        isBucket, &v39Tag)) {\n'
        '                    VH_Map02V39Token = nextTok;\n'
        '                    VH_Map02V39Gfx = v39Tag.gfx;\n'
        '                    VH_Map02V39Route = v39Tag.route;\n'
        '                    VH_Map02V39Active = 1;\n'
        '                    fprintf(stderr,\n'
        '                        "[v39-terrain-ot] f=%u token=%u gfx=%u route=%u tpage=%u clut=%u\\n",\n'
        '                        s_drawFrame, nextTok, v39Tag.gfx, v39Tag.route,\n'
        '                        (unsigned)q->tpage, (unsigned)q->clut);\n'
        '                }\n'
    )
    text = once(text, anchor, pre + anchor + '\n'
                '                VH_Map02V39Active = 0;', "draw-tagged terrain")
    return text


def raster(text):
    text = once(text, "#define HD_SC 16", "#define HD_SC 16\n"
                "extern volatile unsigned VH_Map02V39Active;\n"
                "extern volatile unsigned VH_Map02V39Token;\n"
                "extern volatile unsigned VH_Map02V39Gfx;\n"
                "extern volatile unsigned VH_Map02V39Route;", "raster declaration")
    anchor = "            if (draw) {                                      /* 0000h = transparent (skip, still step) */"
    logging = (
        '            /* Read-only native PS1 texel sample. Never applied to sprites. */\n'
        '            if (VH_Map02V39Active && !cx->rc->target && !cx->hdPx &&\n'
        '                (current_x & 31) == 0 && (y & 31) == 0)\n'
        '                fprintf(stderr,\n'
        '                    "[v39-terrain-dda] token=%u gfx=%u route=%u x=%d y=%d u=%d v=%d raw=%u draw=%d semi=%d abr=%d\\n",\n'
        '                    VH_Map02V39Token, VH_Map02V39Gfx, VH_Map02V39Route,\n'
        '                    current_x, y, su, sv, draw ? (unsigned)texel : 0u,\n'
        '                    draw, cx->semiTrans, cx->abr);\n'
    )
    return once(text, anchor, logging + anchor, "native dda sample")


def run(root, header):
    rev = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                  text=True).strip()
    if rev != PIN:
        raise ValueError("expected pinned upstream revision " + PIN)
    for path, expected in ((LIBGPU, GPU_SHA), (RASTER, RASTER_SHA)):
        actual = subprocess.check_output(
            ["git", "-C", str(root), "hash-object", path], text=True).strip()
        if actual != expected:
            raise ValueError(path + " does not match pinned source")
    if not (root / GRAPHICS).read_text().count("VH_Map02TraceDraw"):
        raise ValueError("apply existing Map02 trace patch before v39")
    if (root / HEADER).exists():
        raise ValueError("v39 header already exists")
    changes = {
        GRAPHICS: terrain_graphics((root / GRAPHICS).read_text()),
        LIBGPU: libgpu((root / LIBGPU).read_text()),
        RASTER: raster((root / RASTER).read_text())
    }
    # Validate all substitutions before writing anything.
    content = header.read_bytes()
    if not content.startswith(b"#ifndef VH_MAP02_V39_TOKENS_H"):
        raise ValueError("invalid provenance header")
    for path, changed in changes.items():
        (root / path).write_text(changed)
    (root / HEADER).write_bytes(content)
    print("Applied v39 to pinned disposable checkout: three modified .c and one header")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("upstream", type=Path)
    ap.add_argument("--header", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="required; edits specified disposable checkout")
    args = ap.parse_args()
    if not args.apply:
        ap.error("refusing to edit without --apply")
    run(args.upstream.resolve(strict=True), args.header.resolve(strict=True))


if __name__ == "__main__":
    main()
