"""Separate candidate DDA edge snapshots for vertically rejected scanlines.

Input must already have the original source-pinned vertical observer. Candidate
edges are NOT executed dda_span calls, pixels, or verified triangle coverage.
"""
from tools.instrument_map02_putpixel_scope import one

FLAG = "VH_MAP02_DDA_REJECTED_EDGES_TRACE"
ANCHOR = "static void dda_part(const DdaCtx *cx, const DdaPart *tp, DdaUV origin) {"
HELPER = r'''
#if defined(VH_MAP02_DDA_REJECTED_EDGES_TRACE) && (!defined(VH_MAP02_DDA_VERTICAL_TRACE) || !defined(VH_MAP02_RASTER_SKIP_TRACE) || !defined(VH_MAP02_PUTPIXEL_SCOPE) || !defined(VH_MAP02_GPU_CAPTURE))
#error "DDA rejected edges requires original native diagnostic chain"
#endif
#if defined(VH_MAP02_DDA_REJECTED_EDGES_TRACE)
static unsigned vh_rejected_edge_count;
static void VH_Map02RejectedEdges(const DdaCtx *cx, int y,
                                  long long left_x, long long right_x,
                                  int reason) {
    char path[1024];
    FILE *file;
    int n;
    VH_PixelSampleInit();
    if (cx->rc->target != 0 || !vh_pixel_sample_active ||
        !vh_sample_scope_active || y != vh_pixel_sample_y ||
        vh_rejected_edge_count >= 64u ||
        ((reason == 4 || reason == 7) ? y >= cx->clipT :
         (reason == 5 || reason == 6) ? y <= cx->clipB : 1)) return;
    n = snprintf(path, sizeof path, "%s/dda-rejected-edge-candidates.jsonl",
                 vh_pixel_sample_dir);
    if (n < 0 || (size_t)n >= sizeof path) return;
    file = fopen(path, "ab");
    if (!file) return;
    n = fprintf(file,
        "{\"stage\":\"rejected_edge_candidate\",\"step\":%u,"
        "\"frame\":%u,\"primitive_ordinal\":%u,\"reason\":%d,"
        "\"y\":%d,\"x_start\":%d,\"x_bound\":%d,"
        "\"clip_t\":%d,\"clip_b\":%d}\n",
        vh_rejected_edge_count, vh_sample_scope_frame,
        vh_sample_scope_ordinal, reason, y,
        dda_unfp(left_x), dda_unfp(right_x), cx->clipT, cx->clipB);
    if (n < 0) { fclose(file); return; }
    if (fclose(file) != 0) return;
    vh_rejected_edge_count++;
}
#endif
'''
def instrument_rejected_edges(raster):
    if FLAG in raster:
        raise ValueError("candidate observer already installed")
    if "VH_MAP02_DDA_VERTICAL_TRACE" not in raster:
        raise ValueError("source-pinned vertical observer required")
    result = one(raster, ANCHOR, HELPER + "\n" + ANCHOR,
                 "pinned native DDA walker")
    for reason in (4, 5, 6, 7):
        original = f"VH_Map02SkipAt(vh_pixel_sample_x, y, {reason});"
        # The original skip call is nested under a single-line C if in
        # branches 4-6 and under an else-if in branch 7. Keep that syntax.
        # The separate candidate observer performs its own target/sample
        # checks; this does not alter the original rejection decision.
        condition = "y < cx->clipT" if reason in (4, 7) else "y > cx->clipB"
        replacement = (
            f"VH_Map02SkipAt(vh_pixel_sample_x, y, {reason});\n"
            "#if defined(VH_MAP02_DDA_REJECTED_EDGES_TRACE)\n"
            f"                    if ({condition}) "
            f"VH_Map02RejectedEdges(cx, y, left_x, right_x, {reason});\n"
            "#endif"
        )
        result = one(result, original, replacement,
                     f"native vertically rejected row {reason}")
    return result
