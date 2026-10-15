#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/switch_converted_frame.h"

static int uploads, draws, accept_upload = 1;
static uint8_t pixels_seen[18];
static int frame_width, frame_height;

int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *p,
                                      const VhRgb24Frame *frame) {
    size_t n;
    assert(p && p->initialized);
    assert(vh_rgb24_required(frame->width, frame->height, &n));
    assert(n <= sizeof(pixels_seen));
    memcpy(pixels_seen, frame->pixels, n);
    frame_width = frame->width;
    frame_height = frame->height;
    ++uploads;
    return accept_upload;
}
int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *p, int w, int h) {
    assert(p && w == 1280 && h == 720);
    ++draws;
    return 1;
}
int main(void) {
    VhSwitchRgb24Presenter presenter = {0};
    uint16_t vram[] = {0x001f,0x03e0,0x7c00, 0x7fff,0,0};
    uint8_t scratch[18] = {0};
    uint8_t movie[] = {1,2,3,4,5,6, 7,8,9,10,11,12};
    presenter.initialized = 1;

    assert(vh_switch_present_bgr555(&presenter, vram, 6, 3, 2,
                                    0, 0, 3, 2, scratch, sizeof(scratch),
                                    1280, 720));
    assert(uploads == 1 && draws == 1 && frame_width == 3 && frame_height == 2);
    assert(pixels_seen[0] == 255 && pixels_seen[1] == 255 && pixels_seen[2] == 255);
    assert(pixels_seen[9] == 255 && pixels_seen[10] == 0 && pixels_seen[11] == 0);

    assert(vh_switch_present_movie_rgb24(&presenter, movie, sizeof(movie),
                                         2, 2, scratch, sizeof(scratch),
                                         1280, 720));
    assert(uploads == 2 && draws == 2 && frame_width == 2 && frame_height == 2);
    assert(memcmp(pixels_seen, movie + 6, 6) == 0);
    assert(memcmp(pixels_seen + 6, movie, 6) == 0);

    assert(!vh_switch_present_bgr555(&presenter, vram, 5, 3, 2,
                                     0, 0, 3, 2, scratch, sizeof(scratch),
                                     1280, 720));
    assert(!vh_switch_present_movie_rgb24(&presenter, movie, 11, 2, 2,
                                          scratch, sizeof(scratch), 1280, 720));
    assert(!vh_switch_present_movie_rgb24(&presenter, movie, sizeof(movie), 2, 2,
                                          scratch, 11, 1280, 720));
    assert(uploads == 2 && draws == 2);

    /* The top-level bridge also rejects source/scratch overlap before upload. */
    uint8_t aliased_movie[24] = {1,2,3,4,5,6,7,8,9,10,11,12};
    uint8_t saved_movie[24];
    memcpy(saved_movie, aliased_movie, sizeof(saved_movie));
    assert(!vh_switch_present_movie_rgb24(&presenter, aliased_movie, 12,
                                          2, 2, aliased_movie + 3, 12,
                                          1280, 720));
    assert(memcmp(aliased_movie, saved_movie, sizeof(saved_movie)) == 0);
    uint16_t aliased_vram[16] = {0x001f, 0x03e0, 0x7c00, 0x7fff};
    uint16_t saved_vram[16];
    memcpy(saved_vram, aliased_vram, sizeof(saved_vram));
    assert(!vh_switch_present_bgr555(&presenter, aliased_vram, 16, 4, 4,
                                     0, 0, 2, 2, (uint8_t *)aliased_vram + 4,
                                     12, 1280, 720));
    assert(memcmp(aliased_vram, saved_vram, sizeof(saved_vram)) == 0);
    assert(uploads == 2 && draws == 2);

    accept_upload = 0;
    assert(!vh_switch_present_movie_rgb24(&presenter, movie, sizeof(movie), 2, 2,
                                          scratch, sizeof(scratch), 1280, 720));
    assert(uploads == 3 && draws == 2);
    presenter.initialized = 0;
    assert(!vh_switch_present_movie_rgb24(&presenter, movie, sizeof(movie), 2, 2,
                                          scratch, sizeof(scratch), 1280, 720));
    assert(uploads == 3 && draws == 2);
    puts("Converted frame integration tests passed.");
    return 0;
}
