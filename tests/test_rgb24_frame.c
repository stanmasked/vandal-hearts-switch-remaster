#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>

#include "../source/rgb24_frame.h"

int main(void) {
    /* 3 pixels wide means a 9-byte row: catches accidental 4-byte padding. */
    const uint8_t pixels[] = {
        /* bottom row: red, green, blue */
        255, 0, 0,   0, 255, 0,   0, 0, 255,
        /* top row: yellow, magenta, cyan */
        255, 255, 0,  255, 0, 255,  0, 255, 255
    };
    VhRgb24Frame frame = {pixels, 9u, 3, 2};
    assert(vh_rgb24_frame_valid(&frame));

    const uint8_t *top = vh_rgb24_top_row(&frame, 0);
    assert(top != NULL);
    assert(top[0] == 255 && top[1] == 255 && top[2] == 0);
    assert(top[3] == 255 && top[4] == 0 && top[5] == 255);
    assert(top[6] == 0 && top[7] == 255 && top[8] == 255);

    const uint8_t *bottom = vh_rgb24_top_row(&frame, 1);
    assert(bottom == pixels);
    assert(bottom[0] == 255 && bottom[1] == 0 && bottom[2] == 0);
    assert(bottom[3] == 0 && bottom[4] == 255 && bottom[5] == 0);
    assert(bottom[6] == 0 && bottom[7] == 0 && bottom[8] == 255);

    assert(vh_rgb24_top_row(&frame, -1) == NULL);
    assert(vh_rgb24_top_row(&frame, 2) == NULL);

    VhRgb24Frame null_frame = {NULL, 9u, 3, 2};
    VhRgb24Frame wrong_stride = {pixels, 12u, 3, 2};
    VhRgb24Frame zero_width = {pixels, 0u, 0, 2};
    VhRgb24Frame zero_height = {pixels, 9u, 3, 0};
    assert(!vh_rgb24_frame_valid(NULL));
    assert(!vh_rgb24_frame_valid(&null_frame));
    assert(!vh_rgb24_frame_valid(&wrong_stride));
    assert(!vh_rgb24_frame_valid(&zero_width));
    assert(!vh_rgb24_frame_valid(&zero_height));

    /* Normal upstream width: 320 RGB pixels => 960 bytes per row. */
    VhRgb24Frame native = {pixels, 960u, 320, 2};
    assert(!vh_rgb24_frame_valid(&native)); /* backing data is too small only conceptually;
                                             * validity checks layout, not allocation length. */

    puts("RGB24 frame contract tests passed.");
    return 0;
}
