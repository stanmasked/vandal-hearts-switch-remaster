#include <assert.h>
#include <stdio.h>

#include "../source/switch_presenter_layout.h"

static void expect_rect(int sw, int sh, int vw, int vh,
                        int x, int y, int w, int h) {
    VhPresenterRect rect = {-1, -1, -1, -1};
    assert(vh_presenter_fit_rect(sw, sh, vw, vh, &rect));
    assert(rect.x == x);
    assert(rect.y == y);
    assert(rect.width == w);
    assert(rect.height == h);
}

int main(void) {
    /* Native 4:3 image letterboxed into a 16:9 720p output. */
    expect_rect(320, 240, 1280, 720, 160, 0, 960, 720);

    /* Wide source fits the width; top/bottom bars are centered. */
    expect_rect(16, 9, 800, 600, 0, 75, 800, 450);

    /* Portrait source fits the height; left/right bars are centered. */
    expect_rect(240, 320, 1280, 720, 370, 0, 540, 720);

    /* Same-size and 1:1 viewports remain exact. */
    expect_rect(320, 240, 320, 240, 0, 0, 320, 240);
    expect_rect(1, 1, 7, 7, 0, 0, 7, 7);

    VhPresenterRect rect = {1, 2, 3, 4};
    assert(!vh_presenter_fit_rect(0, 240, 1280, 720, &rect));
    assert(!vh_presenter_fit_rect(320, -1, 1280, 720, &rect));
    assert(!vh_presenter_fit_rect(320, 240, 0, 720, &rect));
    assert(!vh_presenter_fit_rect(320, 240, 1280, 0, &rect));
    assert(!vh_presenter_fit_rect(320, 240, 1280, 720, NULL));

    puts("Switch presenter layout tests passed.");
    return 0;
}
