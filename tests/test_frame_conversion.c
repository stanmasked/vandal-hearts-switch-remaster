#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/frame_conversion.h"

int main(void) {
    size_t required = 0;
    assert(vh_rgb24_required(320, 240, &required) && required == 230400u);
    assert(vh_rgb24_required(321, 240, &required) && required == 231120u);
    assert(!vh_rgb24_required(0, 240, &required));
    assert(!vh_rgb24_required(320, -1, &required));
    assert(!vh_rgb24_required(320, 240, NULL));
    const uint16_t vram[12] = {
        0x0000, 0x001f, 0x03e0, 0x7c00,
        0x0000, 0x7fff, 0x001f, 0x0000,
        0x0000, 0x03e0, 0x7c00, 0x0000
    };
    uint8_t out[18] = {0};
    assert(vh_frame_from_bgr555(vram, 12, 4, 3, 1, 0, 2, 3,
                                 out, sizeof(out)));
    /* Top input row is last in output. */
    assert(out[0] == 0 && out[1] == 255 && out[2] == 0);
    assert(out[3] == 0 && out[4] == 0 && out[5] == 255);
    assert(out[12] == 255 && out[13] == 0 && out[14] == 0);
    assert(out[15] == 0 && out[16] == 255 && out[17] == 0);
    assert(!vh_frame_from_bgr555(vram, 11, 4, 3, 1, 0, 2, 3,
                                  out, sizeof(out)));
    assert(!vh_frame_from_bgr555(vram, 12, 4, 3, 3, 0, 2, 3,
                                  out, sizeof(out)));
    assert(!vh_frame_from_bgr555(vram, 12, 4, 3, -1, 0, 2, 3,
                                  out, sizeof(out)));
    assert(!vh_frame_from_bgr555(vram, 12, 4, 3, 1, 0, 2, 3,
                                  out, sizeof(out) - 1));
    const uint8_t movie[] = {1,2,3, 4,5,6, 7,8,9, 10,11,12};
    uint8_t flipped[12] = {0};
    assert(vh_frame_from_rgb24_top_down(movie, sizeof(movie), 2, 2,
                                        flipped, sizeof(flipped)));
    assert(memcmp(flipped, movie + 6, 6) == 0);
    assert(memcmp(flipped + 6, movie, 6) == 0);
    assert(!vh_frame_from_rgb24_top_down(movie, 11, 2, 2,
                                         flipped, sizeof(flipped)));
    assert(!vh_frame_from_rgb24_top_down(movie, sizeof(movie), 2, 2,
                                         flipped, 11));
    puts("Checked frame conversion tests passed.");
    return 0;
}
