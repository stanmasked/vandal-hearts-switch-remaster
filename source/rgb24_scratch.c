#include "rgb24_scratch.h"
#include "frame_conversion.h"
#include <stdlib.h>

void vh_rgb24_scratch_init(VhRgb24Scratch *scratch) {
    if (!scratch) return;
    scratch->pixels = NULL;
    scratch->capacity = 0;
}

int vh_rgb24_scratch_reserve(VhRgb24Scratch *scratch,
                             int width, int height, size_t max_bytes) {
    size_t required;
    void *memory;
    if (!scratch || !vh_rgb24_required(width, height, &required) ||
        required > max_bytes)
        return 0;
    if (scratch->capacity >= required)
        return scratch->pixels != NULL;
    memory = realloc(scratch->pixels, required);
    if (!memory)
        return 0; /* Preserve the existing buffer on allocation failure. */
    scratch->pixels = (uint8_t *)memory;
    scratch->capacity = required;
    return 1;
}

void vh_rgb24_scratch_destroy(VhRgb24Scratch *scratch) {
    if (!scratch) return;
    free(scratch->pixels);
    scratch->pixels = NULL;
    scratch->capacity = 0;
}
