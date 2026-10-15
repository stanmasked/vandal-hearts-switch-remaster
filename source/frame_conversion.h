#ifndef VH_FRAME_CONVERSION_H
#define VH_FRAME_CONVERSION_H
#include <stddef.h>
#include <stdint.h>
#include "rgb24_frame.h"

/* All lengths are in elements/bytes, not merely assumed from dimensions. */
int vh_rgb24_required(int width, int height, size_t *bytes);
int vh_frame_from_bgr555(const uint16_t *src, size_t src_pixels,
                         int src_width, int src_height,
                         int x, int y, int width, int height,
                         uint8_t *dst, size_t dst_bytes);
int vh_frame_from_rgb24_top_down(const uint8_t *src, size_t src_bytes,
                                 int width, int height,
                                 uint8_t *dst, size_t dst_bytes);
#endif
