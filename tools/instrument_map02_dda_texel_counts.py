#!/usr/bin/env python3
"""Source-pinned, opt-in FT4 *executed DDA sample* counters for PC GPU.

Never estimate native DDA sampling from a texture UV rectangle: this hooks
the exact draw/transparent decision in pc_raster.c while the real DrawOTag
primitive scope is active. One bounded, aggregate-only row per FT4 (including
zero-sample FT4), with frame/ordinal/type and counts for BGR555 == 0,
nonzero STP bit 15, and other nonzero texels. This is NOT a PS1 GPU trace.
"""
import argparse
import json
from pathlib import Path

from tools.instrument_map02_gpu_native_events import instrument as capture_gpu
from tools.instrument_map02_putpixel_scope import (
    GPU_BLOB, RASTER_BLOB, one, scope_gpu, scope_raster,
)
from tools.prepare_map02_pcport import git_blob_sha1

FLAG = "VH_MAP02_DDA_TEXEL_COUNTS"
DDA_ANCHOR = "            if (draw) {                                      /* 0000h = transparent (skip, still step) */"
RECORD = r'''
#if defined(VH_MAP02_DDA_TEXEL_COUNTS)
#define VH_MAP02_DDA_TEXEL_CAP 64u
static unsigned vh_dda_texel_records;
static unsigned long long vh_dda_zero, vh_dda_stp, vh_dda_opaque;
static void VH_Map02TexelReset(void) {
    vh_dda_zero = vh_dda_stp = vh_dda_opaque = 0u;
}
static void VH_Map02TexelCount(unsigned short bgr555) {
    if (!vh_sample_scope_active || vh_sample_scope_type != 2) return;
    /* Native only: the deferred higher-resolution pass is not observed. */
    if (!bgr555) ++vh_dda_zero;
    else if (bgr555 & 0x8000u) ++vh_dda_stp;
    else ++vh_dda_opaque;
}
static void VH_Map02TexelFinish(void) {
    char path[1024];
    int n;
    FILE *out;
    if (!vh_sample_scope_active || vh_sample_scope_type != 2 ||
        vh_dda_texel_records >= VH_MAP02_DDA_TEXEL_CAP) return;
    n = snprintf(path, sizeof path, "%s/native-dda-ft4-texel-counts.jsonl",
                 vh_pixel_sample_dir);
    if (n < 0 || (size_t)n >= sizeof path) return;
    out = fopen(path, "ab");
    if (!out) return;
    n = fprintf(out, "{\"stage\":\"native_dda_ft4_texel_counts\","
                "\"step\":%u,\"frame\":%u,\"primitive_ordinal\":%u,"
                "\"primitive_type\":%d,\"zero\":%llu,\"stp\":%llu,"
                "\"opaque\":%llu}\n",
                vh_dda_texel_records, vh_sample_scope_frame,
                vh_sample_scope_ordinal, vh_sample_scope_type,
                vh_dda_zero, vh_dda_stp, vh_dda_opaque);
    if (n >= 0 && fclose(out) == 0) ++vh_dda_texel_records;
    else if (n < 0) fclose(out);
}
#endif
'''


def instrument_scoped_raster(scoped):
    if FLAG in scoped:
        raise ValueError("DDA texel counter already installed")
    scoped = one(
        scoped, "static void VH_PixelSampleRecord(",
        RECORD + "\nstatic void VH_PixelSampleRecord(",
        "native DDA aggregate helper insertion",
    )
    scoped = one(
        scoped, "        vh_sample_scope_type = type;",
        "        vh_sample_scope_type = type;\n"
        f"#if defined({FLAG})\n        VH_Map02TexelReset();\n#endif",
        "synchronous DrawOTag per-primitive counter reset",
    )
    scoped = one(
        scoped, "void VH_Map02PixelScopeClear(void) { VH_Map02PixelScopeEnd(); }",
        f"void VH_Map02PixelScopeClear(void) {{\n"
        f"#if defined({FLAG})\n    VH_Map02TexelFinish();\n#endif\n"
        "    VH_Map02PixelScopeEnd();\n}",
        "one aggregate before closing native primitive scope",
    )
    scoped = one(
        scoped, DDA_ANCHOR,
        f"#if defined({FLAG})\n"
        "            if (cx->rc->target == 0)\n"
        "                VH_Map02TexelCount(draw ? texel : 0u);\n"
        "#endif\n" + DDA_ANCHOR,
        "original native DDA sampled texel decision",
    )
    return scoped


def prepare(original_gpu, original_raster, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError("output directory exists; refusing overwrite")
    gpu_bytes, raster_bytes = original_gpu.read_bytes(), original_raster.read_bytes()
    if (git_blob_sha1(gpu_bytes) != GPU_BLOB or
            git_blob_sha1(raster_bytes) != RASTER_BLOB):
        raise ValueError("pinned original PC GPU/raster blobs do not match")
    gpu = scope_gpu(capture_gpu(gpu_bytes.decode("utf-8")))
    raster = instrument_scoped_raster(scope_raster(raster_bytes.decode("utf-8")))
    destination.mkdir(parents=True)
    (destination / "libgpu.dda-count.c").write_text(gpu, encoding="utf-8")
    (destination / "pc_raster.dda-count.c").write_text(raster, encoding="utf-8")
    return {
        "original_source_pinned": True,
        "enabled_by": ["-DVH_MAP02_GPU_CAPTURE", "-DVH_MAP02_PUTPIXEL_SCOPE",
                       "-DVH_MAP02_DDA_TEXEL_COUNTS"],
        "required_private_environment": [
            "VH_MAP02_GPU_CAPTURE_DIR", "VH_MAP02_GPU_CAPTURE_FRAME",
            "VH_MAP02_PUTPIXEL_DIR", "VH_MAP02_PUTPIXEL_FRAME",
            "VH_MAP02_PUTPIXEL_X", "VH_MAP02_PUTPIXEL_Y",
        ],
        "output": "native-dda-ft4-texel-counts.jsonl",
        "maximum_ft4_count_records": 64,
        "native_dda_only": True,
        "zero_is_bgr555_0000": True,
        "stp_counts_are_nonzero_texels_with_bit15": True,
        "pixels_written_or_ps1_accuracy_proven": False,
        "gameplay_captured": False,
        "game_data_published": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_gpu", type=Path)
    parser.add_argument("original_raster", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.original_gpu, args.original_raster,
                                 args.output_dir), sort_keys=True, indent=2))
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
