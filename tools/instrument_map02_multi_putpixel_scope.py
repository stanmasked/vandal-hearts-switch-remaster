#!/usr/bin/env python3
"""Generate an opt-in, TWO-coordinate, same-binary native DrawOTag/PutPixel probe.

Both private VRAM words share one original PC raster loop, one monotonically
numbered JSONL, one primitive scope and one bounded 64-call budget. This
supplies simultaneous *instrumentation*, not authenticated retail gameplay
or proof that no raster call escaped the bounded observer.
"""
import argparse
import json
from pathlib import Path

from tools.instrument_map02_putpixel_scope import (
    FLAG as SINGLE_FLAG, GPU_BLOB, RASTER_BLOB, one,
    scope_gpu, scope_raster, instrument_gpu_native,
)
from tools.prepare_map02_pcport import git_blob_sha1

FLAG = "VH_MAP02_MULTI_PUTPIXEL_SCOPE"
SECOND_COORDINATE = r'''
    {
        const char *vx2 = getenv("VH_MAP02_PUTPIXEL_X2");
        const char *vy2 = getenv("VH_MAP02_PUTPIXEL_Y2");
        char *endx2 = NULL, *endy2 = NULL;
        long x2, y2;
        if (!vx2 || !*vx2 || !vy2 || !*vy2) return;
        x2 = strtol(vx2, &endx2, 10);
        y2 = strtol(vy2, &endy2, 10);
        if (endx2 == vx2 || !endx2 || *endx2 != '\0' ||
            endy2 == vy2 || !endy2 || *endy2 != '\0' ||
            x2 < 0 || x2 >= VRAM_W || y2 < 0 || y2 >= VRAM_H ||
            (x2 == vh_pixel_sample_x && y2 == vh_pixel_sample_y)) return;
        vh_pixel_sample_x2 = (int)x2;
        vh_pixel_sample_y2 = (int)y2;
    }
'''


def multi_raster(original):
    if FLAG in original:
        raise ValueError("two-word native raster observer already installed")
    src = scope_raster(original)
    src = one(src, "static int vh_pixel_sample_x, vh_pixel_sample_y;",
              "static int vh_pixel_sample_x, vh_pixel_sample_y;\n"
              "static int vh_pixel_sample_x2, vh_pixel_sample_y2;",
              "second native private sample coordinates")
    src = one(src, "    vh_pixel_sample_active = 1;",
              SECOND_COORDINATE + "    vh_pixel_sample_active = 1;",
              "require exactly two distinct opted-in words")
    src = one(src, "x == vh_pixel_sample_x && y == vh_pixel_sample_y;",
              "((x == vh_pixel_sample_x && y == vh_pixel_sample_y) ||\n"
              "            (x == vh_pixel_sample_x2 && y == vh_pixel_sample_y2));",
              "match either native VRAM coordinate")
    if src.count(SINGLE_FLAG) != 3:
        raise ValueError("unexpected single-coordinate scope guard count")
    return src.replace(SINGLE_FLAG, FLAG)


def multi_gpu(original):
    if FLAG in original:
        raise ValueError("two-word native GPU scope already injected")
    src = scope_gpu(instrument_gpu_native(original))
    if src.count(SINGLE_FLAG) != 4:
        raise ValueError("unexpected native DrawOTag scope guard count")
    return src.replace(SINGLE_FLAG, FLAG)


def prepare(gpu_path, raster_path, output_dir):
    if output_dir.is_symlink() or output_dir.exists():
        raise ValueError("output directory already exists; refusing overwrite")
    gpu_raw, raster_raw = gpu_path.read_bytes(), raster_path.read_bytes()
    if git_blob_sha1(gpu_raw) != GPU_BLOB:
        raise ValueError("source-pinned PC libgpu.c Git blob differs")
    if git_blob_sha1(raster_raw) != RASTER_BLOB:
        raise ValueError("source-pinned PC pc_raster.c Git blob differs")
    gpu = multi_gpu(gpu_raw.decode("utf-8"))
    raster = multi_raster(raster_raw.decode("utf-8"))
    output_dir.mkdir(parents=True)
    (output_dir / "libgpu.multiscope.c").write_text(gpu, encoding="utf-8")
    (output_dir / "pc_raster.multiscope.c").write_text(raster, encoding="utf-8")
    return {
        "exact_original_gpu_sources_pinned": True,
        "generated": ["libgpu.multiscope.c", "pc_raster.multiscope.c"],
        "enabled_by": ["-DVH_MAP02_GPU_CAPTURE", f"-D{FLAG}"],
        "required_private_environment": [
            "VH_MAP02_GPU_CAPTURE_DIR", "VH_MAP02_GPU_CAPTURE_FRAME",
            "VH_MAP02_PUTPIXEL_DIR", "VH_MAP02_PUTPIXEL_FRAME",
            "VH_MAP02_PUTPIXEL_X", "VH_MAP02_PUTPIXEL_Y",
            "VH_MAP02_PUTPIXEL_X2", "VH_MAP02_PUTPIXEL_Y2",
        ],
        "distinct_sample_coordinates_required": 2,
        "total_pixel_calls_record_cap": 64,
        "single_shared_putpixel_event_stream": True,
        "same_native_drawotag_primitive_scope": True,
        "ordinary_gpu_backend_modified": False,
        "original_gameplay_captured": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_libgpu", type=Path)
    p.add_argument("original_raster", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    try:
        result = prepare(a.original_libgpu, a.original_raster, a.output_dir)
    except (ValueError, OSError, UnicodeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
