#ifndef VH_PS1_ABR_BLEND_H
#define VH_PS1_ABR_BLEND_H

/*
 * Optional PS1 ABR reference blend for pixel-format-independent FT4.
 *
 * Textured ABE requires both the polygon's semi-transparent bit and the
 * texel's STP flag. The FT4 classifier omits color zero, copies unflagged
 * texels and calls this callback only for flagged texels. If ABE is off,
 * STP texels must be copied unchanged rather than blended.
 *
 * Blend takes 5-bit BGR channel values, saturates to [0,31], and expands
 * to 8-bit using bit replication. Hardware-accurate RGB modulation,
 * dithering, destination mask bits, subpixel setup and GPU VRAM timing
 * are NOT claimed. Half and quarter contributions truncate 5-bit values.
 */
#include <stdint.h>
#include "ps1_indexed_texture.h"

enum {
    VH_PS1_ABR_AVERAGE = 0,  /* B/2 + F/2 */
    VH_PS1_ABR_ADD = 1,      /* B + F */
    VH_PS1_ABR_SUBTRACT = 2, /* B - F */
    VH_PS1_ABR_QUARTER = 3   /* B + F/4 */
};

typedef void (*VhPs1RgbUnpackFn)(
    uint32_t packed, uint8_t *r, uint8_t *g, uint8_t *b, void *context);

typedef struct {
    uint8_t abr;                 /* 0..3; chosen by GPU texture page. */
    uint8_t primitive_semi;      /* Whether ABE is set on the polygon. */
    VhPs1RgbUnpackFn unpack;
    VhPs1RgbPackFn pack;
    void *context;
} VhPs1AbrState;

static inline int vh_ps1_abr_mode_valid(unsigned abr) {
    return abr <= VH_PS1_ABR_QUARTER;
}

/* Integer-only 5-bit channel blend with saturated outputs. */
static inline uint8_t vh_ps1_abr_blend_5bit(
    unsigned back, unsigned front, unsigned abr) {
    unsigned result;
    if (back > 31u || front > 31u || !vh_ps1_abr_mode_valid(abr))
        return 0;
    switch (abr) {
    case VH_PS1_ABR_AVERAGE:
        result = (back >> 1) + (front >> 1);
        break;
    case VH_PS1_ABR_ADD:
        result = back + front;
        break;
    case VH_PS1_ABR_SUBTRACT:
        result = back > front ? back - front : 0;
        break;
    default:
        result = back + (front >> 2);
        break;
    }
    return (uint8_t)(result > 31u ? 31u : result);
}

static inline int vh_ps1_abr_state_valid(const VhPs1AbrState *state) {
    return state && vh_ps1_abr_mode_valid(state->abr) &&
           state->unpack && state->pack;
}

/* Explicitly handles STP blend requests with caller-owned pixel format.
 * Invalid settings return the unmodified foreground rather than guessing.
 * No lookup of GPU status is performed; caller must supply ABR and ABE. */
static inline uint32_t vh_ps1_abr_stp_blend(
    uint32_t destination, uint32_t foreground, void *opaque_state) {
    const VhPs1AbrState *state = (const VhPs1AbrState *)opaque_state;
    uint8_t br, bg, bb, fr, fg, fb;
    uint8_t r, g, b;
    if (!vh_ps1_abr_state_valid(state) || !state->primitive_semi)
        return foreground;
    state->unpack(destination, &br, &bg, &bb, state->context);
    state->unpack(foreground, &fr, &fg, &fb, state->context);
    r = vh_ps1_5_to_8(vh_ps1_abr_blend_5bit(br >> 3, fr >> 3, state->abr));
    g = vh_ps1_5_to_8(vh_ps1_abr_blend_5bit(bg >> 3, fg >> 3, state->abr));
    b = vh_ps1_5_to_8(vh_ps1_abr_blend_5bit(bb >> 3, fb >> 3, state->abr));
    return state->pack(r, g, b, state->context);
}

/* PS1 TPage ABR state occupies bits [6:5]. */
static inline unsigned vh_ps1_tpage_abr(uint16_t texture_page) {
    return (texture_page >> 5) & 3u;
}

#endif
