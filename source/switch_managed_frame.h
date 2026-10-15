#ifndef VH_SWITCH_MANAGED_FRAME_H
#define VH_SWITCH_MANAGED_FRAME_H
#include "rgb24_scratch.h"
#include "switch_converted_frame.h"

/* Synchronous, caller-owned allocation reused between regular and movie frames.
 * max_bytes sets a strict per-frame ceiling. Call scratch_init before use.
 * The source and scratch allocations must be distinct.
 */
int vh_switch_present_managed_bgr555(VhSwitchRgb24Presenter *presenter,
    VhRgb24Scratch *scratch, size_t max_bytes,
    const uint16_t *vram, size_t vram_pixels, int vram_width, int vram_height,
    int x, int y, int width, int height, int viewport_width, int viewport_height);

int vh_switch_present_managed_movie(VhSwitchRgb24Presenter *presenter,
    VhRgb24Scratch *scratch, size_t max_bytes,
    const uint8_t *movie, size_t movie_bytes, int width, int height,
    int viewport_width, int viewport_height);
#endif
