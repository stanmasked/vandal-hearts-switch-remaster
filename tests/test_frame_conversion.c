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
    /* A single-pixel crop must preserve the original pixel and guard bytes. */
    uint8_t guarded[5] = {0xaa, 0, 0, 0, 0xbb};
    assert(vh_frame_from_bgr555(vram, 12, 4, 3, 1, 0, 1, 1,
                                 guarded + 1, 3));
    assert(guarded[0] == 0xaa && guarded[4] == 0xbb);
    assert(guarded[1] == 255 && guarded[2] == 0 && guarded[3] == 0);
    assert(!vh_frame_from_bgr555(vram, 12, 4, 3, 4, 0, 1, 1,
                                  guarded + 1, 3));
    assert(!vh_frame_from_bgr555(vram, 12, 4, 3, 0, 3, 1, 1,
                                  guarded + 1, 3));

    /* Top-down movie conversion also preserves its output guard bytes. */
    const uint8_t single_pixel[] = {13, 27, 41};
    uint8_t movie_guarded[5] = {0xcc, 0, 0, 0, 0xdd};
    assert(vh_frame_from_rgb24_top_down(single_pixel, 3, 1, 1,
                                        movie_guarded + 1, 3));
    assert(movie_guarded[0] == 0xcc && movie_guarded[4] == 0xdd);
    assert(memcmp(movie_guarded + 1, single_pixel, 3) == 0);
    assert(!vh_frame_from_rgb24_top_down(single_pixel, 2, 1, 1,
                                         movie_guarded + 1, 3));
    assert(!vh_frame_from_rgb24_top_down(single_pixel, 3, 1, 1,
                                         movie_guarded + 1, 2));
    assert(movie_guarded[0] == 0xcc && movie_guarded[4] == 0xdd);
    /* Overlapping buffers must fail before either buffer changes. */
    uint16_t shared_vram[16] = {0x001f, 0x03e0, 0x7c00, 0x7fff};
    uint16_t original_vram[16];
    memcpy(original_vram, shared_vram, sizeof(shared_vram));
    assert(!vh_frame_from_bgr555(shared_vram, 16, 4, 4, 0, 0, 2, 2,
                                  (uint8_t *)shared_vram + 8, 12));
    assert(memcmp(shared_vram, original_vram, sizeof(shared_vram)) == 0);

    uint8_t shared_movie[24] = {1,2,3,4,5,6,7,8,9,10,11,12};
    uint8_t original_movie[24];
    memcpy(original_movie, shared_movie, sizeof(shared_movie));
    assert(!vh_frame_from_rgb24_top_down(shared_movie, 12, 2, 2,
                                         shared_movie, sizeof(shared_movie)));
    assert(!vh_frame_from_rgb24_top_down(shared_movie, 12, 2, 2,
                                         shared_movie + 6, 12));
    assert(memcmp(shared_movie, original_movie, sizeof(shared_movie)) == 0);
    puts("Checked frame conversion tests passed.");
    return 0;
}
