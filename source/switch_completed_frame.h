#ifndef VH_SWITCH_COMPLETED_FRAME_H
#define VH_SWITCH_COMPLETED_FRAME_H

#include <stddef.h>
#include <stdint.h>
#include "switch_frame_bridge.h"

/*
 * Boundary for the ORIGINAL upstream PC_GpuPresent scratch image, after OSD,
 * subtitles and overlay composition. Pixels are packed bottom-up RGB24.
 * Borrowed pointer must remain valid until this synchronous call returns.
 * pixel_bytes is the actual accessible allocation size, not an estimate.
 * This path performs NO second conversion or vertical flip.
 */
int vh_switch_present_completed_rgb24(VhSwitchRgb24Presenter *presenter,
                                      const uint8_t *pixels,
                                      size_t pixel_bytes,
                                      int width, int height,
                                      int viewport_width, int viewport_height);
#endif
