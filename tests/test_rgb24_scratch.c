#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "../source/rgb24_scratch.h"

int main(void) {
    VhRgb24Scratch scratch;
    vh_rgb24_scratch_init(&scratch);
    assert(scratch.pixels == NULL && scratch.capacity == 0);

    assert(vh_rgb24_scratch_reserve(&scratch, 320, 240, 230400u));
    assert(scratch.capacity == 230400u && scratch.pixels);
    uint8_t *initial = scratch.pixels;
    initial[0] = 0xa5;
    assert(vh_rgb24_scratch_reserve(&scratch, 2, 2, 230400u));
    assert(scratch.pixels == initial && scratch.pixels[0] == 0xa5);

    /* Reject undersized caps without invalidating a previously valid frame. */
    assert(!vh_rgb24_scratch_reserve(&scratch, 321, 240, 230400u));
    assert(scratch.pixels == initial && scratch.capacity == 230400u);

    assert(vh_rgb24_scratch_reserve(&scratch, 321, 240, 231120u));
    assert(scratch.capacity == 231120u);
    uint8_t *larger = scratch.pixels;
    assert(!vh_rgb24_scratch_reserve(&scratch, 0, 240, SIZE_MAX));
    assert(!vh_rgb24_scratch_reserve(&scratch, 320, -1, SIZE_MAX));
    assert(!vh_rgb24_scratch_reserve(&scratch, 320, 240, 0));
    assert(scratch.pixels == larger && scratch.capacity == 231120u);

    vh_rgb24_scratch_destroy(&scratch);
    assert(!scratch.pixels && scratch.capacity == 0);
    vh_rgb24_scratch_destroy(&scratch);
    assert(!vh_rgb24_scratch_reserve(NULL, 320, 240, 230400u));
    vh_rgb24_scratch_init(NULL);
    vh_rgb24_scratch_destroy(NULL);
    puts("RGB24 scratch lifetime tests passed.");
    return 0;
}
