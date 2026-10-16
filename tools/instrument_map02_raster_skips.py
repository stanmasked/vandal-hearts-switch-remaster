#!/usr/bin/env python3
"""Opt-in, source-pinned native PC raster rejection observer.

Builds synchronized GPU before/after capture + PutPixel scope from the
same pinned libgpu.c/pc_raster.c and additionally observes *executed*
pixel-skip branches. Only three strictly evidenced reasons are recorded:
1: DDA textured texel BGR555 == 0 (native only)
2: target X belongs to an un-clipped DDA span but is horizontally clipped
3: legacy barycentric textured texel BGR555 == 0 (native only)

No conjectures about unobserved pixels, vertical clipping, per-pixel
hardware mask rejections or triangle coverage. Disabled build is inert.
"""
import argparse
import json
from pathlib import Path

from tools.instrument_map02_gpu_native_events import instrument as gpu_capture
from tools.instrument_map02_putpixel_scope import (
    GPU_BLOB, RASTER_BLOB, scope_gpu, scope_raster, one
)
from tools.prepare_map02_pcport import git_blob_sha1

FLAG = "VH_MAP02_RASTER_SKIP_TRACE"

RECORDER = r'''
#if defined(VH_MAP02_RASTER_SKIP_TRACE)
/* Only an explicitly selected private native VRAM word, in a real
 * DrawOTag primitive. This observer never modifies clipping or texels.
 * The 64-record hard cap is independent of the PutPixel call cap. */
#define VH_MAP02_SKIP_CAP 64u
static unsigned vh_map02_skip_count;
static void VH_Map02SkipAt(int x, int y, int reason) {
    char path[1024];
    int n;
    FILE *file;
    VH_PixelSampleInit();
    if (!vh_pixel_sample_active || !vh_sample_scope_active ||
        vh_map02_skip_count >= VH_MAP02_SKIP_CAP ||
        x != vh_pixel_sample_x || y != vh_pixel_sample_y) return;
    n = snprintf(path, sizeof path, "%s/putpixel-native-skips.jsonl",
                 vh_pixel_sample_dir);
    if (n < 0 || (size_t)n >= sizeof path) return;
    file = fopen(path, "ab");
    if (!file) return;
    n = fprintf(file, "{\"stage\":\"native_raster_skip\","
                "\"step\":%u,\"frame\":%u,\"primitive_ordinal\":%u,"
                "\"primitive_type\":%d,\"x\":%d,\"y\":%d,\"reason\":%d}\n",
                vh_map02_skip_count, vh_sample_scope_frame,
                vh_sample_scope_ordinal, vh_sample_scope_type,
                x, y, reason);
    if (n < 0) { fclose(file); return; }
    if (fclose(file) != 0) return;
    vh_map02_skip_count++;
}
#endif
'''

SPAN_ANCHOR = "static void dda_span(const DdaCtx *cx, int y, int x_start, int x_bound, DdaUV uv) {"
DDA_DRAW_ANCHOR = '''            if (draw) {                                      /* 0000h = transparent (skip, still step) */
                UnpackColor(texel, &tr, &tg, &tb);'''
DDA_END_ANCHOR = '''                          cx->abr, cx->semiTrans && (texel & 0x8000), 1);
            }
        } else {'''
LEGACY_ANCHOR = '''                if (texel == 0) continue; /* real hw: 0000h texel = transparent */'''


def instrument_raster_skips(scoped_raster):
    if FLAG in scoped_raster:
        raise ValueError("raster skip observer already installed")
    # The scoped PutPixel helper is the only place holding the frame/ordinal
    # and the private coordinate selection. Insert new helper afterwards.
    src = one(
        scoped_raster, "static void VH_PixelSampleRecord(",
        RECORDER + "\nstatic void VH_PixelSampleRecord(",
        "scoped PutPixel skip helper insertion")
    # Original unclipped span includes x in [start, bound). Even if
    # drawing-area clip eliminates the entire span, this is an observed
    # horizontal clip rejection of that X at that Y, not a triangle proof.
    src = one(
        src, SPAN_ANCHOR,
        SPAN_ANCHOR + '''
#if defined(VH_MAP02_RASTER_SKIP_TRACE)
    if (cx->rc->target == 0 && x_start <= vh_pixel_sample_x &&
        vh_pixel_sample_x < x_bound &&
        (vh_pixel_sample_x < cx->clipL || vh_pixel_sample_x > cx->clipR))
        VH_Map02SkipAt(vh_pixel_sample_x, y, 2);
#endif''',
        "original DDA half-open span")
    # DDA's draw == false occurs only when the actual sampled texel
    # (ordinary indexed/direct or optional HD replacement) is BGR555=0.
    # Native target=0 explicitly excludes deferred supersampling.
    src = one(src, DDA_END_ANCHOR,
              '''                          cx->abr, cx->semiTrans && (texel & 0x8000), 1);
            }
#if defined(VH_MAP02_RASTER_SKIP_TRACE)
            else if (cx->rc->target == 0)
                VH_Map02SkipAt(current_x, y, 1);
#endif
        } else {''', "actual DDA zero-color texel branch")
    src = one(src, LEGACY_ANCHOR,
              '''                if (texel == 0) {
#if defined(VH_MAP02_RASTER_SKIP_TRACE)
                    if (rc->target == 0) VH_Map02SkipAt(x, y, 3);
#endif
                    continue;
                } /* real hw: 0000h texel = transparent */''',
              "actual fallback barycentric zero texel")
    return src


def prepare(original_gpu, original_raster, output_dir):
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("output directory exists; no overwrite")
    gpu_bytes, raster_bytes = original_gpu.read_bytes(), original_raster.read_bytes()
    if git_blob_sha1(gpu_bytes) != GPU_BLOB or git_blob_sha1(raster_bytes) != RASTER_BLOB:
        raise ValueError("unrecognized source: pinned original PC GPU blob mismatch")
    gpu = scope_gpu(gpu_capture(gpu_bytes.decode("utf-8")))
    raster = instrument_raster_skips(scope_raster(raster_bytes.decode("utf-8")))
    output_dir.mkdir(parents=True)
    (output_dir / "libgpu.skip.c").write_text(gpu, encoding="utf-8")
    (output_dir / "pc_raster.skip.c").write_text(raster, encoding="utf-8")
    return {
        "original_pc_source_pinned": True,
        "native_capture_same_binary": True,
        "enabled_by": [
            "-DVH_MAP02_GPU_CAPTURE", "-DVH_MAP02_PUTPIXEL_SCOPE",
            "-DVH_MAP02_RASTER_SKIP_TRACE",
        ],
        "required_private_environment": [
            "VH_MAP02_GPU_CAPTURE_DIR", "VH_MAP02_GPU_CAPTURE_FRAME",
            "VH_MAP02_PUTPIXEL_DIR", "VH_MAP02_PUTPIXEL_FRAME",
            "VH_MAP02_PUTPIXEL_X", "VH_MAP02_PUTPIXEL_Y",
        ],
        "reason_codes": {
            "1": "dda_sampled_zero_bgr555",
            "2": "dda_span_horizontal_clip",
            "3": "legacy_barycentric_sampled_zero_bgr555",
        },
        "max_raster_skip_records": 64,
        "max_putpixel_records": 64,
        "native_only": True,
        "real_gameplay_captured": False,
        "hardware_mask_test_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_gpu", type=Path)
    parser.add_argument("original_raster", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = prepare(args.original_gpu, args.original_raster, args.output_dir)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
