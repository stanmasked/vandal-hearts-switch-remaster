#!/usr/bin/env python3
"""Build two matched, opt-in public PC GPU source copies for native pixel/OT correlation.

Unlike unsourced pixel guessing, the original DrawOTag walker explicitly
sets a frame-scoped primitive ordinal around its real native render switch.
The real PutPixel then logs this ordinal alongside each selected coordinate's
actual input, before and after BGR555. Hires worker draws and GPU transfers
are NOT attributed to this native primitive. The ordinary source is not
altered and baseline compilation contains no new symbols.
"""
import argparse
import json
from pathlib import Path

from tools.instrument_map02_native_putpixel import (
    BLOB as RASTER_BLOB,
    instrument as instrument_raster_pixel,
)
from tools.instrument_map02_gpu_native_events import (
    PINNED_SOURCE as GPU_BLOB,
)
from tools.prepare_map02_pcport import git_blob_sha1

FLAG = "VH_MAP02_PUTPIXEL_SCOPE"
RASTER_ORIGINAL_FLAG = "VH_MAP02_PUTPIXEL_SAMPLE"

SCOPE_STATE = r'''
/* Written by the synchronous native DrawOTag walker only.
 * The later deferred high-resolution worker pass never calls this path. */
static unsigned vh_sample_scope_frame, vh_sample_scope_ordinal;
static int vh_sample_scope_type, vh_sample_scope_active;
static unsigned long vh_sample_target_frame;
static void VH_Map02PixelScopeEnd(void) { vh_sample_scope_active = 0; }
void VH_Map02PixelScopeSet(unsigned frame, unsigned ordinal, int type) {
    VH_PixelSampleInit();
    vh_sample_scope_active = vh_pixel_sample_active &&
        (unsigned long)frame == vh_sample_target_frame;
    if (vh_sample_scope_active) {
        vh_sample_scope_frame = frame;
        vh_sample_scope_ordinal = ordinal;
        vh_sample_scope_type = type;
    }
}
void VH_Map02PixelScopeClear(void) { VH_Map02PixelScopeEnd(); }
'''

def one(text, old, new, description):
    n = text.count(old)
    if n != 1:
        raise ValueError(f"{description}: pinned source anchor count {n} != 1")
    return text.replace(old, new, 1)


def scope_raster(original):
    # First use the exact previously tested source-pinned observer, with
    # identical direct WritePixel. Only its optional capture metadata changes.
    src = instrument_raster_pixel(original)
    src = one(src, f"#if defined({RASTER_ORIGINAL_FLAG})",
              f"#if defined({FLAG})", "raster helper macro first")
    # The three remaining helper/callsite guards are source generated, and
    # all must be changed so on/off builds are mutually coherent.
    if src.count(RASTER_ORIGINAL_FLAG) != 2:
        raise ValueError("pixel observer guard count drift")
    src = src.replace(RASTER_ORIGINAL_FLAG, FLAG)
    src = one(src, "static unsigned vh_pixel_sample_count;",
              "static unsigned vh_pixel_sample_count;\n"
              "static void VH_PixelSampleInit(void);\n" + SCOPE_STATE,
              "scope state and C declarations")
    src = one(src, '    if (!vh_pixel_sample_dir || vh_pixel_sample_dir[0] != \'/\' ||',
              '    if (!vh_pixel_sample_dir || vh_pixel_sample_dir[0] != \'/\' ||',
              "private capture directory unchanged")
    # Require an explicit target frame IN ADDITION to previous x/y/dir.
    src = one(src, "    vh_pixel_sample_x = (int)x;",
              r'''    {
        const char *vf = getenv("VH_MAP02_PUTPIXEL_FRAME");
        char *endf = NULL;
        unsigned long frame;
        if (!vf || !vf[0]) return;
        frame = strtoul(vf, &endf, 10);
        if (endf == vf || !endf || *endf != '\0' ||
            frame == 0 || frame > 0xffffffffUL) return;
        vh_sample_target_frame = frame;
    }
    vh_pixel_sample_x = (int)x;''',
              "strict frame opt-in")
    src = one(src, "return vh_pixel_sample_active &&",
              "return vh_pixel_sample_active && vh_sample_scope_active &&",
              "must be in live native primitive scope")
    src = one(src, '"\\"x\\":%d,\\"y\\":%d,\\"before\\":%u,\\"front\\":%u,"',
              '"\\"frame\\":%u,\\"primitive_ordinal\\":%u,\\"primitive_type\\":%d,"'
              '"\\"x\\":%d,\\"y\\":%d,\\"before\\":%u,\\"front\\":%u,"',
              "scoped pixel sample JSON")
    src = one(src, "vh_pixel_sample_count, x, y, (unsigned)before, (unsigned)front,",
              "vh_pixel_sample_count, vh_sample_scope_frame, "
              "vh_sample_scope_ordinal, vh_sample_scope_type,\n"
              "        x, y, (unsigned)before, (unsigned)front,",
              "scoped pixel sample arguments")
    if RASTER_ORIGINAL_FLAG in src:
        raise ValueError("previous optional pixel macro remains in new source")
    return src


def scope_gpu(original):
    if FLAG in original:
        raise ValueError("GPU scope already injected")
    proto = f'''#if defined({FLAG})
extern void VH_Map02PixelScopeSet(unsigned frame, unsigned ordinal, int type);
extern void VH_Map02PixelScopeClear(void);
#endif
'''
    src = one(original, "void DrawOTag(unsigned int *p) {",
              proto + "void DrawOTag(unsigned int *p) {",
              "DrawOTag entry")
    src = one(src, "    unsigned long walkSteps = 0;",
              "    unsigned long walkSteps = 0;"
              f"\n#if defined({FLAG})\n"
              "    unsigned vh_sample_primitive_ordinal = 0;\n#endif",
              "per-frame native primitive ordinal")
    src = one(src, "            switch (type) {",
              f"#if defined({FLAG})\n"
              "            VH_Map02PixelScopeSet((unsigned)s_drawFrame,\n"
              "                vh_sample_primitive_ordinal++, type);\n"
              "#endif\n            switch (type) {",
              "begin native primitive scope")
    src = one(src, "            default:\n                break;\n            }\n        }\n        nextTok = rawTagOfCur;",
              "            default:\n                break;\n            }\n"
              f"#if defined({FLAG})\n"
              "            VH_Map02PixelScopeClear();\n"
              "#endif\n        }\n        nextTok = rawTagOfCur;",
              "end native primitive scope")
    return src


def prepare(gpu_path, raster_path, output_dir):
    if output_dir.is_symlink() or output_dir.exists():
        raise ValueError("output directory already exists; refusing overwrite")
    gpu_bytes, raster_bytes = gpu_path.read_bytes(), raster_path.read_bytes()
    if git_blob_sha1(gpu_bytes) != GPU_BLOB:
        raise ValueError("source-pinned PC libgpu.c Git blob differs")
    if git_blob_sha1(raster_bytes) != RASTER_BLOB:
        raise ValueError("source-pinned PC pc_raster.c Git blob differs")
    gpu = scope_gpu(gpu_bytes.decode("utf-8"))
    raster = scope_raster(raster_bytes.decode("utf-8"))
    output_dir.mkdir(parents=True)
    (output_dir / "libgpu.scope.c").write_text(gpu, encoding="utf-8")
    (output_dir / "pc_raster.scope.c").write_text(raster, encoding="utf-8")
    return {
        "exact_original_gpu_sources_pinned": True,
        "generated": ["libgpu.scope.c", "pc_raster.scope.c"],
        "enabled_by": f"-D{FLAG}",
        "required_private_environment": [
            "VH_MAP02_PUTPIXEL_DIR", "VH_MAP02_PUTPIXEL_X",
            "VH_MAP02_PUTPIXEL_Y", "VH_MAP02_PUTPIXEL_FRAME",
        ],
        "pixel_calls_record_cap": 64,
        "scope_walk_includes_all_native_primitives": True,
        "native_primitive_frame_and_ordinal_logged": True,
        "original_gameplay_captured": False,
        "ordinary_gpu_backend_modified": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_libgpu", type=Path)
    p.add_argument("original_raster", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    try:
        result = prepare(args.original_libgpu, args.original_raster,
                         args.output_dir)
    except (ValueError, OSError, UnicodeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
