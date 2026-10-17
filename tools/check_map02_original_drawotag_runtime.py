#!/usr/bin/env python3
"""Execute actual PC libgpu DrawOTag + pc_raster on asset-free OT packets.

Runtime synthetic: DR_MODE -> semi F4 -> semi textured FT4 using hand-made
15-bit STP texture. Tests actual upstream OT token traversal, native VRAM
writes and independently recorded BlendG1 callbacks. Game/HD dependencies
are disabled by isolated headless stubs; this is NOT original MAP02 gameplay.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from tools.instrument_map02_drawotag_scope import instrument as patch_ot
from tools.instrument_map02_scoped_blend import instrument as patch_raster
from tools.map02_blendg1_witness import compare_blendg1_witnesses
from tools.map02_vram_edge_witness import parse_and_compare_edges

HARNESS = r"""
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "PsyQ/libgpu.h"
#include "pc_platform.h"
#include "pc_gpu_internal.h"
#include "pc_lang.h"
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
#include "map02_scoped_blend_sink.h"
#endif
#ifdef VH_MAP02_VRAM_EDGE_PROBE
#include "map02_vram_edges.h"
#endif

/* Headless stubs ONLY for non-raster external subsystems. Never link these
 * stubs into a real game build, replay, or authenticated original capture. */
const char *PC_LangBgDir(void) { return NULL; }
void PC_LangPatchFwdUpload(int x, int y, int w, int h, unsigned short *pix) {
    (void)x; (void)y; (void)w; (void)h; (void)pix;
}
void TrcInit(void) {}
void TrcWrite(char op, const void *a, u32 na, const void *b, u32 nb) {
    (void)op; (void)a; (void)na; (void)b; (void)nb;
}
void TrcPrim(int type, const void *prim) { (void)type; (void)prim; }
void TrcFrameEnd(void) {}
int TrcReplaying(void) { return 0; }
void HdPack_OnLoad(const RECT *rect, const unsigned short *src) {
    (void)rect; (void)src;
}
int HdRegionCount(void) { return 0; }
int HdReplaceCount(void) { return 0; }
int HdAnyActive(void) { return 0; }
const char *HdDumpDir(void) { return NULL; }
void HdMaybeDump(int tp, int cl, int x0, int x1, int y0, int y1) {
    (void)tp; (void)cl; (void)x0; (void)x1; (void)y0; (void)y1;
    assert(!"unexpected HD dump");
}
HdRegion *HdFindTriRegion(int tp, int x0, int x1, int y0, int y1) {
    (void)tp; (void)x0; (void)x1; (void)y0; (void)y1;
    assert(!"unexpected HD lookup");
    return NULL;
}
void PC_UpdateCamOsd(void) {}
int PC_CpuCount(void) { return 1; } /* no worker pool in native 1x mode */
void PC_GpuPresent(unsigned short *vram, int width, int height,
                   int x, int y, int w, int h) {
    (void)vram; (void)width; (void)height;
    (void)x; (void)y; (void)w; (void)h;
}

#ifdef VH_MAP02_VRAM_EDGE_PROBE
/* Independent boundary sampler does not read PutPixel events itself.
 * This harness performs the JOIN after both sealed buffers exist. */
static void verify_edges_against_putpixel(void) {
    unsigned i, j = 0, total = vh_map02_scope_count();
    VHMap02VramEdge edge;
    VHMap02BlendEvent pixel;
    assert(!vh_map02_edges_failed());
    assert(vh_map02_edges_count() > 0);
    for (i = 0; i < vh_map02_edges_count(); i++) {
        unsigned matched = 0;
        unsigned short latest = 0;
        assert(vh_map02_edges_copy(i, &edge));
        assert(edge.frame == 1 && edge.ordinal == i);
        assert(edge.x == 10 && edge.y == 10);
        while (j < total) {
            assert(vh_map02_scope_copy(j, &pixel));
            if (pixel.ordinal != i) break;
            assert(pixel.frame == edge.frame);
            assert(pixel.primitive_type == edge.primitive_type);
            if (!matched) assert(pixel.before == edge.before);
            else assert(pixel.before == latest);
            latest = pixel.after;
            matched++;
            j++;
        }
        if (matched) assert(latest == edge.after);
        else assert(edge.before == edge.after);
    }
    assert(j == total);
}
#endif

int main(void) {
    unsigned int ot[2];
    DR_MODE mode;
    POLY_F4 f4;
    POLY_FT4 ft4;
    DRAWENV env;
    DISPENV disp;
    unsigned short (*vram)[1024] = PC_GpuVram();
    int u, v;
    unsigned short before = 1u, after;
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    VHMap02BlendEvent event;
    unsigned i, seen_f4 = 0, seen_ft4 = 0, last_ordinal = 0;
#endif
    ResetGraph(0);
    SetDefDrawEnv(&env, 0, 0, 320, 240);
    SetDefDispEnv(&disp, 0, 0, 320, 240);
    PutDrawEnv(&env);
    PutDispEnv(&disp);

    /* Original texture sampler reads a native 15-bit page, with STP set. */
    for (v = 0; v < 8; v++)
        for (u = 0; u < 8; u++)
            vram[v][640 + u] = 0x8010;
    vram[10][10] = before;

    SetPolyF4(&f4);
    setRGB0(&f4, 200, 0, 0);
    setXYWH(&f4, 9, 9, 6, 6);
    SetSemiTrans(&f4, 1);
    SetPolyFT4(&ft4);
    setRGB0(&ft4, 128, 128, 128);
    setXYWH(&ft4, 9, 9, 6, 6);
    setUVWH(&ft4, 0, 0, 6, 6);
    ft4.tpage = GetTPage(2, 2, 640, 0);
    ft4.clut = 0;
    SetSemiTrans(&ft4, 1);
    SetDrawMode(&mode, 0, 0, GetTPage(2, 1, 640, 0), NULL);

    /* AddPrim is LIFO: walker processes mode, F4, FT4. Two draw
     * ordinals, not three. Real OT token mint/resolve functions used. */
    ClearOTag(ot, 2);
    AddPrim(&ot[0], &ft4);
    AddPrim(&ot[0], &f4);
    AddPrim(&ot[0], &mode);
    DrawOTag(ot);
#ifdef VH_MAP02_VRAM_EDGE_PROBE
    verify_edges_against_putpixel();
    assert(vh_map02_edges_count() == 2);
#endif
    after = vram[10][10];
    assert(after != before);
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    assert(!vh_map02_scope_failed());
    assert(vh_map02_scope_count() >= 2);
    for (i = 0; i < vh_map02_scope_count(); i++) {
        assert(vh_map02_scope_copy(i, &event));
        assert(event.frame == 1 && event.x == 10 && event.y == 10);
        assert(event.ordinal <= 1 && event.ordinal >= last_ordinal);
        assert(event.semi && event.accurate && event.has_blend);
        assert(event.blend_fg == (unsigned short)(event.front | 0x8000u));
        assert(event.blend_bg == event.before);
        assert(event.blend_result == event.after);
        if (event.ordinal == 0) {
            assert(!seen_ft4);
            assert(event.primitive_type == PC_GPU_PRIM_POLY_F4);
            assert(event.abr == 1);
            if (i == 0) assert(event.before == before);
            seen_f4++;
        } else {
            assert(seen_f4);
            assert(event.primitive_type == PC_GPU_PRIM_POLY_FT4);
            assert(event.abr == 2 && event.textured);
            seen_ft4++;
        }
        last_ordinal = event.ordinal;
        if (i + 1u == vh_map02_scope_count()) assert(event.after == after);
    }
    assert(seen_f4 && seen_ft4);
#endif
    /* Hash the entire native 1 MiB VRAM to prove observer/no-observer
     * code produces the SAME framebuffer. Only the digest is printed. */
    {
        size_t byte_count, i;
        const unsigned char *bytes = PC_GpuVramBytes(&byte_count);
        unsigned long long digest = 14695981039346656037ULL;
        assert(byte_count == 1024u * 512u * 2u && bytes);
        for (i = 0; i < byte_count; i++)
            digest = (digest ^ bytes[i]) * 1099511628211ULL;
        printf("%016llx\n", digest);
    }
    return 0;
}
"""


def run_original_ot(upstream, *, compiler="cc", harness=HARNESS,
                    expected_ordinals=frozenset((0, 1)), minimum_blends=2):
    base = Path(upstream).resolve() / "platform" / "pc"
    source = base / "src"
    if not (source / "libgpu.c").is_file() or not (source / "pc_raster.c").is_file():
        raise FileNotFoundError("missing original PC GPU translation unit")
    walker = patch_ot((source / "libgpu.c").read_text(encoding="utf-8"))
    raster = patch_raster((source / "pc_raster.c").read_text(encoding="utf-8"))
    tools = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="vh-map02-original-ot-runtime-") as temp:
        root = Path(temp)
        (root / "libgpu.c").write_text(walker, encoding="utf-8")
        (root / "pc_raster.c").write_text(raster, encoding="utf-8")
        (root / "main.c").write_text(harness, encoding="utf-8")
        results = []
        ordinary_digest = None
        for mode, defines in (
            ("ordinary", []),
            ("scoped", ["-DVH_MAP02_SCOPED_BLEND_PROBE"]),
            ("staged", ["-DVH_MAP02_SCOPED_BLEND_PROBE", "-DVH_MAP02_POSIX_STAGE",
                        "-DVH_MAP02_VRAM_EDGE_PROBE"]),
        ):
            args = [
                compiler, "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-missing-field-initializers",
                "-ffunction-sections", "-fdata-sections",
                "-DVH_REGION_US", *defines,
                "-I", str(base / "include"), "-I", str(base / "src"),
                "-I", str(tools),
                str(root / "libgpu.c"), str(root / "pc_raster.c"),
                str(root / "main.c"),
            ]
            if defines:
                args.append(str(tools / "map02_scoped_blend_sink.c"))
            if mode == "staged":
                args.append(str(tools / "map02_scoped_blend_stage.c"))
                args.append(str(tools / "map02_vram_edges.c"))
            exe = root / ("test-" + mode)
            args += ["-Wl,--gc-sections", "-lm", "-pthread", "-o", str(exe)]
            compiled = subprocess.run(args, capture_output=True, text=True,
                                      timeout=90, check=False)
            if compiled.returncode:
                raise ValueError(mode + " original OT compile: " + compiled.stderr[-4000:])
            env = dict(os.environ, VH_ACCURATE="1",
                       VH_INTERNAL_SCALE="1", VH_MAP02_PROBE_FRAME="1",
                       VH_MAP02_PROBE_X="10", VH_MAP02_PROBE_Y="10")
            if mode == "staged":
                out = root / "private-native"
                out.mkdir(mode=0o700)
                env["VH_MAP02_PROBE_OUTPUT_DIR"] = str(out)
            executed = subprocess.run([str(exe)], env=env,
                                      capture_output=True, text=True, timeout=30)
            if executed.returncode:
                raise ValueError(mode + " original OT runtime: " + executed.stderr[-4000:])
            digest = executed.stdout.strip()
            if len(digest) != 16 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError(mode + " missing native VRAM digest")
            if ordinary_digest is None:
                ordinary_digest = digest
            elif digest != ordinary_digest:
                raise ValueError(mode + " native VRAM changed under instrumentation")
            if mode == "staged":
                pixel_file = out / "putpixel-native-events.pending.jsonl"
                blend_file = out / "blendg1-native-events.pending.jsonl"
                edge_file = out / "vram-edges-native-events.pending.jsonl"
                edge_report = parse_and_compare_edges(
                    pixel_file.read_bytes(), edge_file.read_bytes())
                if edge_report["independently_sampled_draw_edges"] != (
                        max(expected_ordinals) + 1):
                    raise ValueError("independent staged VRAM edge count mismatch")
                pixels = [json.loads(row) for row in pixel_file.read_text().splitlines()]
                blends = [json.loads(row) for row in blend_file.read_text().splitlines()]
                report = compare_blendg1_witnesses(pixels, blends)
                if (report["observed_blendg1_putpixel_pairs"] < minimum_blends or
                        {p["primitive_ordinal"] for p in pixels} != set(expected_ordinals)):
                    raise ValueError("staged actual DrawOTag witnesses do not match")
            results.append(mode)
        return tuple(results)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_upstream", type=Path)
    a = p.parse_args()
    try:
        result = run_original_ot(a.pinned_upstream)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print("Original DrawOTag + raster runtime modes: " + ", ".join(result))
    print("Asset-free synthetic F4/FT4/DR_MODE, NOT genuine MAP02 capture.")


if __name__ == "__main__":
    main()
