#ifndef VH_SWITCH_CONVERTED_FRAME_H
#define VH_SWITCH_CONVERTED_FRAME_H
#include "frame_conversion.h"
#include "switch_frame_bridge.h"

/* The scratch pointer belongs to caller; upload/draw finishes before return.
 * Requires current GLES2 context, initialized presenter, distinct backing
 * allocations for source and scratch, and a target-owned buffer swap later.
 */
int vh_switch_present_bgr555(VhSwitchRgb24Presenter *presenter,
                             const uint16_t *vram, size_t vram_pixels,
                             int vram_width, int vram_height,
                             int x, int y, int width, int height,
                             uint8_t *scratch, size_t scratch_bytes,
                             int viewport_width, int viewport_height);

int vh_switch_present_movie_rgb24(VhSwitchRgb24Presenter *presenter,
                                  const uint8_t *movie, size_t movie_bytes,
                                  int width, int height,
                                  uint8_t *scratch, size_t scratch_bytes,
                                  int viewport_width, int viewport_height);
#endif
