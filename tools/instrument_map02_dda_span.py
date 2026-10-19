"""Opt-in native DDA span observer on an already source-pinned raster.

Records only *executed* dda_span calls. Vertically rejected rows NEVER
reach dda_span; this is not a reconstruction of those rows' edge spans.
"""
from tools.instrument_map02_raster_skips import SPAN_ANCHOR
from tools.instrument_map02_putpixel_scope import one

FLAG = "VH_MAP02_DDA_SPAN_TRACE"
DEPENDENCIES = ("VH_MAP02_GPU_CAPTURE", "VH_MAP02_PUTPIXEL_SCOPE",
                "VH_MAP02_RASTER_SKIP_TRACE", "VH_MAP02_DDA_VERTICAL_TRACE")
GUARD = """
#if defined(VH_MAP02_DDA_SPAN_TRACE) && (!defined(VH_MAP02_GPU_CAPTURE) || !defined(VH_MAP02_PUTPIXEL_SCOPE) || !defined(VH_MAP02_RASTER_SKIP_TRACE) || !defined(VH_MAP02_DDA_VERTICAL_TRACE))
#error "DDA span trace requires all native GPU, pixel, skip and vertical flags"
#endif
"""
RECORDER = r'''
#if defined(VH_MAP02_DDA_SPAN_TRACE)
#define VH_MAP02_SPAN_CAP 64u
static unsigned vh_map02_span_count;
static void VH_Map02SpanObserve(const DdaCtx *cx, int y, int start, int bound) {
    char path[1024];
    FILE *file;
    int n;
    VH_PixelSampleInit();
    if (cx->rc->target != 0 || !vh_pixel_sample_active ||
        !vh_sample_scope_active || y != vh_pixel_sample_y ||
        vh_map02_span_count >= VH_MAP02_SPAN_CAP) return;
    n = snprintf(path, sizeof path, "%s/dda-native-spans.jsonl", vh_pixel_sample_dir);
    if (n < 0 || (size_t)n >= sizeof path) return;
    file = fopen(path, "ab");
    if (!file) return;
    n = fprintf(file,
        "{\"stage\":\"native_dda_span\",\"step\":%u,\"frame\":%u,"
        "\"primitive_ordinal\":%u,\"primitive_type\":%d,\"y\":%d,"
        "\"x_start\":%d,\"x_bound\":%d,\"clip_l\":%d,"
        "\"clip_r\":%d,\"clip_t\":%d,\"clip_b\":%d}\n",
        vh_map02_span_count, vh_sample_scope_frame, vh_sample_scope_ordinal,
        vh_sample_scope_type, y, start, bound, cx->clipL, cx->clipR,
        cx->clipT, cx->clipB);
    if (n < 0) { fclose(file); return; }
    if (fclose(file) != 0) return;
    vh_map02_span_count++;
}
#endif
'''

def instrument_span(raster):
    if FLAG in raster:
        raise ValueError("DDA span observer already installed")
    if "VH_Map02SkipAt" not in raster:
        raise ValueError("requires existing source-pinned raster-skip observer")
    raster = one(raster, SPAN_ANCHOR,
        GUARD + RECORDER + "\n" + SPAN_ANCHOR + """
#if defined(VH_MAP02_DDA_SPAN_TRACE)
    VH_Map02SpanObserve(cx, y, x_start, x_bound);
#endif""", "actual native dda_span entry")
    return raster

def prepare_span(original_gpu, original_raster, output_dir):
    """Generate pinned original GPU/span overlay without mutating upstream.

    Fail closed on source drift or an existing destination.
    """
    from pathlib import Path
    from tools.instrument_map02_putpixel_scope import (
        GPU_BLOB, RASTER_BLOB, scope_gpu, scope_raster,
    )
    from tools.instrument_map02_gpu_native_events import instrument as gpu_capture
    from tools.instrument_map02_raster_skips import instrument_raster_skips
    from tools.instrument_map02_vertical_dda import instrument_vertical
    from tools.prepare_map02_pcport import git_blob_sha1

    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("output directory exists; refusing overwrite")
    gpu_raw = Path(original_gpu).read_bytes()
    raster_raw = Path(original_raster).read_bytes()
    if git_blob_sha1(gpu_raw) != GPU_BLOB or git_blob_sha1(raster_raw) != RASTER_BLOB:
        raise ValueError("source does not match pinned original PC GPU Git blobs")
    gpu = scope_gpu(gpu_capture(gpu_raw.decode("utf-8")))
    raster = instrument_span(instrument_vertical(
        instrument_raster_skips(scope_raster(raster_raw.decode("utf-8")))))
    # Keep validation ahead of publication and never overwrite overlay files.
    output_dir.mkdir(parents=True)
    created = []
    try:
        for name, source in (("libgpu.span.c", gpu), ("pc_raster.span.c", raster)):
            destination = output_dir / name
            with destination.open("x", encoding="utf-8") as stream:
                created.append(destination)
                stream.write(source)
    except BaseException:
        # An interrupted second write must never leave a seemingly valid
        # one-file overlay. Remove only files exclusively created by us.
        for destination in reversed(created):
            destination.unlink(missing_ok=True)
        try:
            output_dir.rmdir()
        except OSError:
            # Preserve the write failure; never delete unknown files.
            pass
        raise
    return {"pinned_original_gpu": True, "native_only": True,
            "entered_spans_only": True,
            "vertical_rejected_row_coverage_proven": False,
            "retail_MAP02_verified": False}

def main():
    """Offline CLI for reproducible source-pinned overlay generation."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_gpu", type=Path)
    parser.add_argument("original_raster", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare_span(args.original_gpu, args.original_raster, args.output_dir)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
