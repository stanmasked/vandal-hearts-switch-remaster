#ifndef VH_MAP02_VRAM4_TRANSFER_LEDGER_H
#define VH_MAP02_VRAM4_TRANSFER_LEDGER_H

/*
 * Opt-in MAP02 GPU transfer ledger gate for per-submission VRAM snapshots.
 *
 * Models pinned PC-port LoadImage, MoveImage, ClearImage loops between the
 * supplied frozen VRAM captures. MoveImage copies FORWARD in-place, not via
 * memmove. The entire 1 MiB image is compared after each submission boundary.
 *
 * This is not a trace recorder, source authentication, nor a GPU rasterizer.
 * The caller separately verifies event hashes/pinned source provenance; this
 * replay cannot prove unrecorded writes did not occur and revert. Any missing
 * GPU write (including rasterized writes) makes this bounded replay fail.
 *
 * Caller supplies >=VH_MAP02_VRAM_BYTES non-overlapping scratch bytes. Failed
 * replay may change scratch, but NEVER changes workspace/renderer output.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "map02_vram4_timeline_frame.h"

#define VH_MAP02_VRAM_LEDGER_MAX_EVENTS 512u
#define VH_MAP02_VRAM_LEDGER_MAX_WORDS 16384u

enum {
    VH_MAP02_VRAM_OP_LOAD = 1,
    VH_MAP02_VRAM_OP_MOVE = 2,
    VH_MAP02_VRAM_OP_CLEAR = 3
};

typedef struct {
    uint64_t frame;
    size_t step;                 /* strictly consecutive, starting at zero */
    size_t before_submission;    /* transition to this submission, >=1 */
    int operation;
    int x, y, w, h;              /* original source RECT, including clipping */
    int dest_x, dest_y;          /* MoveImage destination */
    int red, green, blue;        /* ClearImage 8-bit RGB */
    const uint8_t *load_le;      /* LoadImage little-endian words */
    size_t load_bytes;
} VhMap02VramTransfer;

static inline uint16_t vh_map02_vram_ledger_read(
    const uint8_t *raw, size_t word_index) {
    size_t n = word_index * 2u;
    return (uint16_t)((uint16_t)raw[n] |
                      ((uint16_t)raw[n + 1u] << 8));
}

static inline void vh_map02_vram_ledger_write(
    uint8_t *raw, size_t word_index, uint16_t word) {
    size_t n = word_index * 2u;
    raw[n] = (uint8_t)word;
    raw[n + 1u] = (uint8_t)(word >> 8);
}

static inline int vh_map02_vram_ledger_coord(int value) {
    return value >= 0 && value < 1024;
}
static inline int vh_map02_vram_ledger_row(int value) {
    return value >= 0 && value < 512;
}

/* Workspaces and captured input buffers must not overlap replay scratch.
 * Fail closed on address/length wrap rather than trust caller metadata.
 * This diagnostic runs on the host and libnx, where uintptr_t is available. */
static inline int vh_map02_vram_ledger_ranges_overlap(
    const void *a, size_t an, const void *b, size_t bn) {
    uintptr_t av, bv;
    if (!a || !b || !an || !bn)
        return 0;
    av = (uintptr_t)a;
    bv = (uintptr_t)b;
    if (an > UINTPTR_MAX - av || bn > UINTPTR_MAX - bv)
        return 1;
    return av < bv + bn && bv < av + an;
}


static inline int vh_map02_vram_ledger_event_valid(
    const VhMap02VramTransfer *ev, size_t index,
    uint64_t frame, size_t submissions) {
    size_t words;
    if (!ev || ev->frame != frame || ev->step != index ||
        ev->before_submission < 1u ||
        ev->before_submission >= submissions ||
        ev->x < -2048 || ev->x > 2048 ||
        ev->y < -2048 || ev->y > 2048 ||
        ev->w < 1 || ev->w > 2048 ||
        ev->h < 1 || ev->h > 2048)
        return 0;
    words = (size_t)ev->w * (size_t)ev->h;
    if (words > VH_MAP02_VRAM_LEDGER_MAX_WORDS)
        return 0;
    /* Canonicalize fields unused by each PC GPU operation. The binary
     * importer already enforces this: callers using the C API directly
     * must not bypass that evidence-format constraint. */
    if (ev->operation == VH_MAP02_VRAM_OP_LOAD)
        return ev->dest_x == 0 && ev->dest_y == 0 &&
               ev->red == 0 && ev->green == 0 && ev->blue == 0 &&
               ev->load_le && ev->load_bytes == words * 2u;
    if (ev->load_le || ev->load_bytes)
        return 0;
    if (ev->operation == VH_MAP02_VRAM_OP_MOVE)
        return ev->red == 0 && ev->green == 0 && ev->blue == 0 &&
               ev->dest_x >= -2048 && ev->dest_x <= 2048 &&
               ev->dest_y >= -2048 && ev->dest_y <= 2048;
    if (ev->operation == VH_MAP02_VRAM_OP_CLEAR)
        return ev->dest_x == 0 && ev->dest_y == 0 &&
               ev->red >= 0 && ev->red <= 255 &&
               ev->green >= 0 && ev->green <= 255 &&
               ev->blue >= 0 && ev->blue <= 255;
    return 0;
}

/* Events must already have passed complete preflight. */
static inline void vh_map02_vram_ledger_apply(
    uint8_t *vram, const VhMap02VramTransfer *ev) {
    int j, i;
    uint16_t clear = (uint16_t)(
        ((unsigned)ev->blue >> 3u) << 10u |
        ((unsigned)ev->green >> 3u) << 5u |
        ((unsigned)ev->red >> 3u));
    for (j = 0; j < ev->h; ++j) {
        for (i = 0; i < ev->w; ++i) {
            int sx = ev->x + i, sy = ev->y + j;
            size_t from = (size_t)j * (size_t)ev->w + (size_t)i;
            if (ev->operation == VH_MAP02_VRAM_OP_LOAD) {
                if (vh_map02_vram_ledger_coord(sx) &&
                    vh_map02_vram_ledger_row(sy))
                    vh_map02_vram_ledger_write(vram,
                        (size_t)sy * 1024u + (size_t)sx,
                        vh_map02_vram_ledger_read(ev->load_le, from));
            } else if (ev->operation == VH_MAP02_VRAM_OP_CLEAR) {
                if (vh_map02_vram_ledger_coord(sx) &&
                    vh_map02_vram_ledger_row(sy))
                    vh_map02_vram_ledger_write(vram,
                        (size_t)sy * 1024u + (size_t)sx, clear);
            } else {
                int dx = ev->dest_x + i, dy = ev->dest_y + j;
                if (vh_map02_vram_ledger_coord(sx) &&
                    vh_map02_vram_ledger_row(sy) &&
                    vh_map02_vram_ledger_coord(dx) &&
                    vh_map02_vram_ledger_row(dy))
                    vh_map02_vram_ledger_write(vram,
                        (size_t)dy * 1024u + (size_t)dx,
                        vh_map02_vram_ledger_read(vram,
                            (size_t)sy * 1024u + (size_t)sx));
            }
        }
    }
}

/*
 * All metadata and source faces validated before scratch replay begins.
 * If there are no events, the snapshots must be identical.
 * The complete VRAM (not just the current crop) must match at every point.
 */
static inline int vh_map02_vram4_timeline_verify_ledger(
    const VhMap02Vram4TimelineInput *input,
    const VhMap02Vram4FrameWorkspace *workspace,
    const VhMap02VramTransfer *events, size_t event_count,
    uint8_t *scratch_vram, size_t scratch_bytes) {
    size_t i, next = 0u, boundary;
    if (!vh_map02_vram4_timeline_preflight(input, workspace) ||
        !scratch_vram || scratch_bytes < VH_MAP02_VRAM_BYTES ||
        event_count > VH_MAP02_VRAM_LEDGER_MAX_EVENTS ||
        (event_count && !events))
        return 0;
    /* Prevent self-fulfilling comparisons when scratch aliases a captured
     * snapshot or rewrites pending transfers, source geometry or OT buffers.
     * All of these checks occur before even the first scratch write. */
    if (vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, input, sizeof *input) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, workspace, sizeof *workspace) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, input->decoded,
            input->decoded_bytes) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, input->entries,
            input->count * sizeof *input->entries) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, events,
            event_count * sizeof *events) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, workspace->bucket_heads,
            input->ot_size * sizeof *workspace->bucket_heads) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, workspace->nodes,
            workspace->face_capacity * sizeof *workspace->nodes) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, workspace->prepared,
            workspace->face_capacity * sizeof *workspace->prepared) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, workspace->atlases,
            workspace->atlas_capacity_bytes) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, workspace->palettes,
            workspace->palette_capacity_bytes) ||
        vh_map02_vram_ledger_ranges_overlap(
            scratch_vram, scratch_bytes, workspace->stats,
            workspace->face_capacity * sizeof *workspace->stats))
        return 0;
    for (i = 0u; i < input->count; ++i)
        if (vh_map02_vram_ledger_ranges_overlap(
                scratch_vram, scratch_bytes, input->entries[i].vram_le,
                input->entries[i].vram_bytes))
            return 0;
    for (i = 0u; i < event_count; ++i) {
        if (!vh_map02_vram_ledger_event_valid(
                &events[i], i, input->frame, input->count) ||
            (i && events[i].before_submission <
                      events[i - 1u].before_submission) ||
            vh_map02_vram_ledger_ranges_overlap(
                scratch_vram, scratch_bytes,
                events[i].load_le, events[i].load_bytes))
            return 0;
    }
    memcpy(scratch_vram, input->entries[0].vram_le, VH_MAP02_VRAM_BYTES);
    for (boundary = 1u; boundary < input->count; ++boundary) {
        while (next < event_count &&
               events[next].before_submission == boundary) {
            vh_map02_vram_ledger_apply(scratch_vram, &events[next]);
            ++next;
        }
        if (memcmp(scratch_vram,input->entries[boundary].vram_le,
                   VH_MAP02_VRAM_BYTES) != 0)
            return 0;
    }
    return next == event_count;
}

/* The renderer workspace is NEVER touched on replay failure. The caller
 * owns the scratch buffer and freezes the inputs for both passes. */
static inline int vh_map02_vram4_timeline_build_with_ledger(
    const VhMap02Vram4TimelineInput *input,
    VhMap02Vram4FrameWorkspace *workspace,
    const VhMap02VramTransfer *events, size_t event_count,
    uint8_t *scratch_vram, size_t scratch_bytes) {
    if (!vh_map02_vram4_timeline_verify_ledger(
            input, workspace, events, event_count, scratch_vram,
            scratch_bytes))
        return 0;
    return vh_map02_vram4_timeline_build(input, workspace);
}

#endif
