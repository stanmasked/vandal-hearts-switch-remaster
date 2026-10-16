/* Private opt-in observer implementation. No output: caller must explicitly
 * transfer validated events to its own private file (never a CI artifact).
 * Not thread-safe: only the original synchronous native-VRAM path may call.
 */
#include "map02_scoped_blend_sink.h"
#include <string.h>

static VHMap02BlendEvent captured[VH_MAP02_MAX_EVENTS];
static VHMap02BlendEvent pending;
static unsigned count, next_ordinal, blend_count;
static unsigned active_frame, active_ordinal;
static int target_x, target_y, in_frame, in_primitive, in_pixel, closed, failed;

static int failure(void) {
    failed = 1;
    return 0;
}

void vh_map02_scope_abort(void) { (void)failure(); }

void vh_map02_scope_reset(void) {
    memset(captured, 0, sizeof(captured));
    memset(&pending, 0, sizeof(pending));
    count = next_ordinal = blend_count = 0;
    active_frame = active_ordinal = 0;
    target_x = target_y = 0;
    in_frame = in_primitive = in_pixel = closed = failed = 0;
}

int vh_map02_scope_begin_frame(unsigned frame, int x, int y) {
    if (failed || in_frame || closed || !frame ||
        x < 0 || x >= 1024 || y < 0 || y >= 512)
        return failure();
    in_frame = 1;
    active_frame = frame;
    target_x = x;
    target_y = y;
    return 1;
}

int vh_map02_scope_begin_primitive(unsigned ordinal) {
    if (failed || !in_frame || in_primitive || in_pixel ||
        ordinal != next_ordinal || next_ordinal == (unsigned)-1)
        return failure();
    active_ordinal = ordinal;
    next_ordinal++;
    in_primitive = 1;
    return 1;
}

int vh_map02_scope_end_primitive(void) {
    if (failed || !in_frame || !in_primitive || in_pixel)
        return failure();
    in_primitive = 0;
    return 1;
}

int vh_map02_scope_end_frame(void) {
    if (failed || !in_frame || in_primitive || in_pixel ||
        !count || !blend_count)
        return failure();
    in_frame = 0;
    closed = 1;
    return 1;
}

unsigned vh_map02_scope_count(void) { return failed ? 0u : count; }
int vh_map02_scope_failed(void) { return failed; }

int vh_map02_scope_copy(unsigned index, VHMap02BlendEvent *out) {
    if (failed || !closed || !out || index >= count)
        return 0;
    *out = captured[index];
    return 1;
}

void vh_map02_probe_begin(int x, int y, unsigned short before,
                          unsigned short front, int abr, int semi,
                          int textured, int accurate) {
    if (failed || !in_frame) return;
    if (x != target_x || y != target_y) {
        if (in_pixel) failure(); /* no nested interleaving is permitted */
        return;
    }
    if (!in_frame || !in_primitive || in_pixel ||
        count >= VH_MAP02_MAX_EVENTS ||
        abr < 0 || abr > 3 || (semi != 0 && semi != 1) ||
        (textured != 0 && textured != 1) ||
        (accurate != 0 && accurate != 1)) {
        failure();
        return;
    }
    memset(&pending, 0, sizeof(pending));
    pending.frame = active_frame;
    pending.ordinal = active_ordinal;
    pending.step = count;
    pending.x = x;
    pending.y = y;
    pending.abr = abr;
    pending.semi = semi;
    pending.textured = textured;
    pending.accurate = accurate;
    pending.before = before;
    pending.front = front;
    in_pixel = 1;
}

void vh_map02_probe_blendg1(int x, int y, unsigned short fg,
                             unsigned short bg, unsigned short result,
                             int abr, int textured) {
    if (failed || !in_frame) return;
    if (x != target_x || y != target_y) {
        if (in_pixel) failure();
        return;
    }
    if (!in_pixel || pending.has_blend || !pending.semi ||
        !pending.accurate || abr != pending.abr ||
        textured != pending.textured ||
        fg != (unsigned short)(pending.front | 0x8000u) ||
        bg != pending.before) {
        failure();
        return;
    }
    pending.has_blend = 1;
    pending.blend_fg = fg;
    pending.blend_bg = bg;
    pending.blend_result = result;
}

void vh_map02_probe_end(int x, int y, unsigned short after) {
    if (failed || !in_frame) return;
    if (x != target_x || y != target_y) {
        if (in_pixel) failure();
        return;
    }
    if (!in_pixel ||
        !!pending.has_blend != !!(pending.semi && pending.accurate) ||
        (pending.has_blend && after != pending.blend_result) ||
        (!pending.semi && after != pending.front)) {
        failure();
        return;
    }
    pending.after = after;
    captured[count++] = pending;
    blend_count += !!pending.has_blend;
    memset(&pending, 0, sizeof(pending));
    in_pixel = 0;
}
