#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "../source/software_renderer.h"

int main(void) {
    enum { WIDTH = 5, HEIGHT = 4, STRIDE = 7, STORAGE = STRIDE * HEIGHT };
    uint32_t pixels[STORAGE];
    for (int i = 0; i < STORAGE; ++i) pixels[i] = 0xA5A5A5A5u;

    VhCanvas canvas = {pixels, STRIDE, WIDTH, HEIGHT};

    /* Normal fill respects row stride and leaves padding untouched. */
    vh_canvas_fill_rect(&canvas, 1, 1, 2, 2, 0x11223344u);
    assert(pixels[1 * STRIDE + 1] == 0x11223344u);
    assert(pixels[1 * STRIDE + 2] == 0x11223344u);
    assert(pixels[2 * STRIDE + 1] == 0x11223344u);
    assert(pixels[2 * STRIDE + 2] == 0x11223344u);
    assert(pixels[1 * STRIDE] == 0xA5A5A5A5u);
    assert(pixels[1 * STRIDE + 3] == 0xA5A5A5A5u);
    assert(pixels[1 * STRIDE + WIDTH] == 0xA5A5A5A5u);

    /* Negative origin clips to the top-left corner. */
    vh_canvas_fill_rect(&canvas, -2, -1, 4, 3, 0x01020304u);
    assert(pixels[0] == 0x01020304u);
    assert(pixels[1] == 0x01020304u);
    assert(pixels[STRIDE] == 0x01020304u);
    assert(pixels[STRIDE + 1] == 0x01020304u);
    assert(pixels[STRIDE + 2] == 0x11223344u);

    /* Right/bottom clipping and wholly off-screen rectangles are safe. */
    vh_canvas_fill_rect(&canvas, 4, 3, 10, 10, 0x55667788u);
    assert(pixels[3 * STRIDE + 4] == 0x55667788u);
    assert(pixels[3 * STRIDE + 3] == 0xA5A5A5A5u);
    vh_canvas_fill_rect(&canvas, 9, 9, 2, 2, 0xFFFFFFFFu);
    vh_canvas_fill_rect(&canvas, 0, 0, 0, 3, 0xFFFFFFFFu);
    vh_canvas_fill_rect(&canvas, 0, 0, 3, -1, 0xFFFFFFFFu);

    /* Null and malformed canvases are no-ops. */
    vh_canvas_fill_rect(NULL, 0, 0, 1, 1, 0);
    VhCanvas null_pixels = {NULL, STRIDE, WIDTH, HEIGHT};
    vh_canvas_fill_rect(&null_pixels, 0, 0, 1, 1, 0);
    VhCanvas short_stride = {pixels, WIDTH - 1, WIDTH, HEIGHT};
    vh_canvas_fill_rect(&short_stride, 0, 0, 1, 1, 0);


    /* Pixel and line primitives respect bounds and padded row stride. */
    vh_canvas_put_pixel(&canvas, 3, 2, 0xCAFEBABEu);
    assert(pixels[2 * STRIDE + 3] == 0xCAFEBABEu);
    vh_canvas_put_pixel(&canvas, -1, 2, 0xFFFFFFFFu);
    vh_canvas_put_pixel(&canvas, WIDTH, 2, 0xFFFFFFFFu);
    assert(pixels[2 * STRIDE + WIDTH] == 0xA5A5A5A5u);

    vh_canvas_draw_hline(&canvas, -2, 0, 4, 0x12345678u);
    assert(pixels[0] == 0x12345678u);
    assert(pixels[1] == 0x12345678u);
    assert(pixels[2] == 0xA5A5A5A5u);
    vh_canvas_draw_vline(&canvas, 4, 2, 5, 0x87654321u);
    assert(pixels[2 * STRIDE + 4] == 0x87654321u);
    assert(pixels[3 * STRIDE + 4] == 0x87654321u);
    assert(pixels[3 * STRIDE + WIDTH] == 0xA5A5A5A5u);
    vh_canvas_draw_hline(&canvas, 0, HEIGHT, 3, 0xFFFFFFFFu);
    vh_canvas_draw_vline(&canvas, WIDTH, 0, 3, 0xFFFFFFFFu);
    vh_canvas_put_pixel(NULL, 0, 0, 0xFFFFFFFFu);


    /* Rectangle outlines draw borders without touching the interior. */
    for (int i = 0; i < STORAGE; ++i) pixels[i] = 0xA5A5A5A5u;
    vh_canvas_draw_rect_outline(&canvas, 1, 0, 3, 3, 0x0BADF00Du);
    assert(pixels[1] == 0x0BADF00Du);
    assert(pixels[2] == 0x0BADF00Du);
    assert(pixels[3] == 0x0BADF00Du);
    assert(pixels[STRIDE + 1] == 0x0BADF00Du);
    assert(pixels[STRIDE + 2] == 0xA5A5A5A5u);
    assert(pixels[STRIDE + 3] == 0x0BADF00Du);
    assert(pixels[2 * STRIDE + 1] == 0x0BADF00Du);
    assert(pixels[2 * STRIDE + 2] == 0x0BADF00Du);
    assert(pixels[2 * STRIDE + 3] == 0x0BADF00Du);
    assert(pixels[STRIDE + 4] == 0xA5A5A5A5u);
    assert(pixels[STRIDE + WIDTH] == 0xA5A5A5A5u);

    for (int i = 0; i < STORAGE; ++i) pixels[i] = 0xA5A5A5A5u;
    vh_canvas_draw_rect_outline(&canvas, -1, -1, 4, 4, 0xABCDEF01u);
    assert(pixels[0] == 0xABCDEF01u);
    assert(pixels[1] == 0xABCDEF01u);
    assert(pixels[STRIDE] == 0xABCDEF01u);
    assert(pixels[STRIDE + 1] == 0xA5A5A5A5u);
    vh_canvas_draw_rect_outline(&canvas, 0, 0, 0, 3, 0xFFFFFFFFu);

    puts("All software renderer tests passed.");
    return 0;
}
