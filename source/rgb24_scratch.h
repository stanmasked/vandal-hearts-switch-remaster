#ifndef VH_RGB24_SCRATCH_H
#define VH_RGB24_SCRATCH_H

#include <stddef.h>
#include <stdint.h>

/* Owned, reusable scratch buffer. Call init before reserve and destroy once. */
typedef struct {
    uint8_t *pixels;
    size_t capacity;
} VhRgb24Scratch;

void vh_rgb24_scratch_init(VhRgb24Scratch *scratch);
int vh_rgb24_scratch_reserve(VhRgb24Scratch *scratch,
                             int width, int height,
                             size_t max_bytes);
void vh_rgb24_scratch_destroy(VhRgb24Scratch *scratch);

#endif
