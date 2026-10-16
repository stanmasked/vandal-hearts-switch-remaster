#!/usr/bin/env python3
"""Add opt-in original PC DDA vertical *scanline* rejection evidence.

The earlier native observer records actual texel-zero and horizontal
span clipping. This companion additionally records four distinct
branches in the EXACT pinned original dda_part scanline traversal.
These are scanline-only events: selected X is merely the diagnostic
address, and *horizontal pixel coverage is NOT proven*.

All original PC rasterization and UV stepping remain unchanged.
"""
import argparse
import json
from pathlib import Path

from tools.instrument_map02_raster_skips import (
    prepare as prepare_base,
    instrument_raster_skips,
)
from tools.instrument_map02_putpixel_scope import (
    GPU_BLOB, RASTER_BLOB, scope_raster, scope_gpu, one,
)
from tools.instrument_map02_gpu_native_events import instrument as gpu_capture
from tools.prepare_map02_pcport import git_blob_sha1

FLAG = "VH_MAP02_DDA_VERTICAL_TRACE"
BASE_FLAG = "VH_MAP02_RASTER_SKIP_TRACE"

ANCHORS = {
    "upside_top_break": "            if (y < cx->clipT) break;",
    "upside_bottom_continue": "            if (y > cx->clipB) continue;",
    "forward_bottom_break": "            if (y > cx->clipB) break;",
    "forward_top_no_span": (
        "            if (y >= cx->clipT) dda_span("
        "cx, y, dda_unfp(left_x), dda_unfp(right_x), luv);"
    ),
}
REASONS = {
    "4": "dda_upside_down_row_below_clip_top_break",
    "5": "dda_upside_down_row_above_clip_bottom_continue",
    "6": "dda_forward_row_above_clip_bottom_break",
    "7": "dda_forward_row_below_clip_top_no_span",
}


def instrument_vertical(scoped_and_horizontal_raster):
    if FLAG in scoped_and_horizontal_raster:
        raise ValueError("vertical DDA observer already installed")
    src = one(
        scoped_and_horizontal_raster,
        "static void dda_part(const DdaCtx *cx, const DdaPart *tp, DdaUV origin) {",
        """#if defined(VH_MAP02_DDA_VERTICAL_TRACE) && !defined(VH_MAP02_RASTER_SKIP_TRACE)
#error "DDA vertical observer requires the native raster skip recorder"
#endif
static void dda_part(const DdaCtx *cx, const DdaPart *tp, DdaUV origin) {""",
        "pinned original DDA row walker")
    src = one(
        src, ANCHORS["upside_top_break"],
        """            if (y < cx->clipT) {
#if defined(VH_MAP02_DDA_VERTICAL_TRACE)
                if (cx->rc->target == 0)
                    VH_Map02SkipAt(vh_pixel_sample_x, y, 4);
#endif
                break;
            }""", "upside-down below-top row break")
    src = one(
        src, ANCHORS["upside_bottom_continue"],
        """            if (y > cx->clipB) {
#if defined(VH_MAP02_DDA_VERTICAL_TRACE)
                if (cx->rc->target == 0)
                    VH_Map02SkipAt(vh_pixel_sample_x, y, 5);
#endif
                continue;
            }""", "upside-down above-bottom row continue")
    src = one(
        src, ANCHORS["forward_bottom_break"],
        """            if (y > cx->clipB) {
#if defined(VH_MAP02_DDA_VERTICAL_TRACE)
                if (cx->rc->target == 0)
                    VH_Map02SkipAt(vh_pixel_sample_x, y, 6);
#endif
                break;
            }""", "forward above-bottom row break")
    src = one(
        src, ANCHORS["forward_top_no_span"],
        """            if (y >= cx->clipT)
                dda_span(cx, y, dda_unfp(left_x), dda_unfp(right_x), luv);
#if defined(VH_MAP02_DDA_VERTICAL_TRACE)
            else if (cx->rc->target == 0)
                VH_Map02SkipAt(vh_pixel_sample_x, y, 7);
#endif""", "forward below-top row no-span")
    return src


def prepare(original_gpu: Path, original_raster: Path, output_dir: Path):
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("output directory exists; refusing overwrite")
    gpu_raw, raster_raw = original_gpu.read_bytes(), original_raster.read_bytes()
    if git_blob_sha1(gpu_raw) != GPU_BLOB or git_blob_sha1(raster_raw) != RASTER_BLOB:
        raise ValueError("source does not match pinned original PC GPU Git blobs")
    gpu = scope_gpu(gpu_capture(gpu_raw.decode("utf-8")))
    raster = instrument_vertical(
        instrument_raster_skips(scope_raster(raster_raw.decode("utf-8"))))
    output_dir.mkdir(parents=True)
    (output_dir / "libgpu.vertical.c").write_text(gpu, encoding="utf-8")
    (output_dir / "pc_raster.vertical.c").write_text(raster, encoding="utf-8")
    return {
        "original_pc_gpu_sources_pinned": True,
        "same_native_drawotag_session": True,
        "required_flags": [
            "-DVH_MAP02_GPU_CAPTURE",
            "-DVH_MAP02_PUTPIXEL_SCOPE",
            "-DVH_MAP02_RASTER_SKIP_TRACE",
            "-DVH_MAP02_DDA_VERTICAL_TRACE",
        ],
        "vertical_scanline_reasons": REASONS,
        "previous_zero_texel_and_horizontal_codes": [1, 2, 3],
        "native_only": True,
        "single_coordinate_bounded_record_cap": 64,
        "per_pixel_triangle_coverage_verified": False,
        "vertical_row_rejected_but_horizontal_coverage_unknown": True,
        "retail_gameplay_captured": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_gpu", type=Path)
    p.add_argument("original_raster", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    try:
        report = prepare(a.original_gpu, a.original_raster, a.output_dir)
    except (OSError, UnicodeError, ValueError) as e:
        p.error(str(e))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
