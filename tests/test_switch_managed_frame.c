#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/switch_managed_frame.h"

static int uploads;
static int draws;
static uint8_t captured[18];
static int captured_width;
static int captured_height;

int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *p,
                                     const VhRgb24Frame *f) {
    size_t required;
    assert(p && p->initialized);
    assert(vh_rgb24_required(f->width, f->height, &required));
    assert(required <= sizeof(captured));
    memcpy(captured, f->pixels, required);
    captured_width = f->width;
    captured_height = f->height;
    ++uploads;
    return 1;
}
int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *p, int w, int h) {
    assert(p && w == 1280 && h == 720);
    ++draws;
    return 1;
}
int main(void) {
    VhRgb24Scratch scratch;
    VhSwitchRgb24Presenter p = {0};
    uint16_t vram[] = {0x001f, 0x03e0, 0x7c00, 0x7fff, 0, 0};
    uint8_t movie[] = {1,2,3,4,5,6,7,8,9,10,11,12};
    vh_rgb24_scratch_init(&scratch);
    p.initialized = 1;

    assert(vh_switch_present_managed_bgr555(&p, &scratch, 18,
        vram, 6, 3, 2, 0, 0, 3, 2, 1280, 720));
    assert(scratch.capacity == 18 && uploads == 1 && draws == 1);
    assert(captured_width == 3 && captured_height == 2);
    assert(captured[0] == 255 && captured[1] == 255 && captured[2] == 255);
    assert(captured[9] == 255 && captured[10] == 0 && captured[11] == 0);
    uint8_t *first = scratch.pixels;

    assert(vh_switch_present_managed_movie(&p, &scratch, 18,
        movie, sizeof(movie), 2, 2, 1280, 720));
    assert(scratch.pixels == first && scratch.capacity == 18);
    assert(uploads == 2 && draws == 2);
    assert(captured_width == 2 && captured_height == 2);
    assert(memcmp(captured, movie + 6, 6) == 0);
    assert(memcmp(captured + 6, movie, 6) == 0);

    assert(!vh_switch_present_managed_movie(&p, &scratch, 11,
        movie, sizeof(movie), 2, 2, 1280, 720));
    assert(!vh_switch_present_managed_movie(&p, &scratch, 18,
        movie, 11, 2, 2, 1280, 720));
    assert(!vh_switch_present_managed_bgr555(&p, &scratch, 18,
        vram, 5, 3, 2, 0, 0, 3, 2, 1280, 720));
    assert(!vh_switch_present_managed_bgr555(&p, &scratch, 18,
        vram, 6, 3, 2, 2, 0, 3, 2, 1280, 720));
    assert(!vh_switch_present_managed_movie(NULL, &scratch, 18,
        movie, sizeof(movie), 2, 2, 1280, 720));
    assert(uploads == 2 && draws == 2 && scratch.pixels == first);

    vh_rgb24_scratch_destroy(&scratch);
    assert(scratch.capacity == 0 && scratch.pixels == NULL);
    puts("Managed Switch frame pipeline tests passed.");
    return 0;
}
