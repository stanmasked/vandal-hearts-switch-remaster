/* Bounded independent native VRAM edge sampler. Never consults PutPixel
 * callbacks: words are provided directly by original DrawOTag's PC_GpuVram.
 * Captures UNCHANGED drawing primitives too (transparent texels).
 */
#include "map02_vram_edges.h"
#include <string.h>

static VHMap02VramEdge edges[VH_MAP02_MAX_DRAW_EDGES];
static VHMap02VramEdge pending;
static unsigned count, next_ordinal, frame_id;
static int target_x, target_y, active, drawing, sealed, failed;

static int fail(void) { failed = 1; return 0; }

void vh_map02_edges_reset(void) {
    memset(edges, 0, sizeof(edges));
    memset(&pending, 0, sizeof(pending));
    count = next_ordinal = frame_id = 0;
    target_x = target_y = active = drawing = sealed = failed = 0;
}
void vh_map02_edges_abort(void) { (void)fail(); }

int vh_map02_edges_begin_frame(unsigned frame, int x, int y) {
    if (failed || active || sealed || !frame ||
        x < 0 || x >= 1024 || y < 0 || y >= 512) return fail();
    frame_id = frame;
    target_x = x;
    target_y = y;
    active = 1;
    return 1;
}

int vh_map02_edges_begin_primitive(unsigned ordinal, unsigned primitive_type,
                                  unsigned short before) {
    if (failed || !active || drawing || count >= VH_MAP02_MAX_DRAW_EDGES ||
        ordinal != next_ordinal || next_ordinal == (unsigned)-1 ||
        primitive_type < 1u || primitive_type > 4u) return fail();
    memset(&pending, 0, sizeof(pending));
    pending.frame = frame_id;
    pending.ordinal = ordinal;
    pending.primitive_type = primitive_type;
    pending.x = target_x;
    pending.y = target_y;
    pending.before = before;
    next_ordinal++;
    drawing = 1;
    return 1;
}

int vh_map02_edges_end_primitive(unsigned short after) {
    if (failed || !active || !drawing) return fail();
    pending.after = after;
    edges[count++] = pending;
    memset(&pending, 0, sizeof(pending));
    drawing = 0;
    return 1;
}

int vh_map02_edges_end_frame(void) {
    if (failed || !active || drawing || !count) return fail();
    active = 0;
    sealed = 1;
    return 1;
}

unsigned vh_map02_edges_count(void) { return failed ? 0u : count; }
int vh_map02_edges_failed(void) { return failed; }

int vh_map02_edges_copy(unsigned index, VHMap02VramEdge *out) {
    if (failed || !sealed || !out || index >= count) return 0;
    *out = edges[index];
    return 1;
}
