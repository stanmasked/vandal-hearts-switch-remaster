#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "../source/texture_sample.h"

int main(void) {
    const uint32_t texels[8] = {
        0x00000001u, 0x00000002u, 0xDEADBEEFu, 0xDEADBEEFu,
        0x00000003u, 0x00000004u, 0xDEADBEEFu, 0xDEADBEEFu
    };
    uint32_t out = 0xA5A5A5A5u;
    assert(vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, 0.0f, 0.0f, &out));
    assert(out == 0x00000001u);
    assert(vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, 0.5f, 0.0f, &out));
    assert(out == 0x00000002u);
    assert(vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, 0.0f, 0.5f, &out));
    assert(out == 0x00000003u);
    assert(vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, 0.999f, 0.999f, &out));
    assert(out == 0x00000004u);
    out = 0xA5A5A5A5u;
    assert(!vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, 1.0f, 0.5f, &out));
    assert(out == 0xA5A5A5A5u);
    assert(!vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, -0.01f, 0.5f, &out));
    assert(!vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, 0.5f, 1.0f, &out));
    assert(!vh_texture_sample_nearest_rgba32(NULL, 2, 2, 2, 0.0f, 0.0f, &out));
    assert(!vh_texture_sample_nearest_rgba32(texels, 0, 2, 4, 0.0f, 0.0f, &out));
    assert(!vh_texture_sample_nearest_rgba32(texels, 2, 2, 1, 0.0f, 0.0f, &out));
    assert(!vh_texture_sample_nearest_rgba32(texels, 2, 2, 4, 0.0f, 0.0f, NULL));
    puts("texture sample tests passed");
    return 0;
}
