/* Regression for fail-closed resampler capacity and sentinel preservation.
 * No proprietary sound data, no Switch system service dependencies.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

static int16_t input[VH_AUDIO_BLOCK_FRAMES * 2u];
static int16_t output[(VH_AUDIO_RESAMPLE_MAX_FRAMES + 2u) * 2u];

int main(void) {
    VhAudioResample state, before;
    vh_audio_resample_reset(&state);
    for (size_t i = 0; i < VH_AUDIO_BLOCK_FRAMES * 2u; i++)
        input[i] = (int16_t)((int)(i * 47u) % 20000 - 10000);
    memset(output, 0x5a, sizeof output);
    before = state;
    /* Deliberately insufficient capacity: no reads/writes or state advance. */
    assert(vh_audio_resample_process(&state, input, 512, output, 1u) == 0);
    assert(memcmp(&state, &before, sizeof state) == 0);
    for (size_t i = 0; i < sizeof output / sizeof output[0]; i++)
        assert((uint16_t)output[i] == UINT16_C(0x5a5a));
    /* Successful output must never touch the guard stereo frame beyond cap. */
    const size_t cap = VH_AUDIO_RESAMPLE_MAX_FRAMES;
    const size_t n = vh_audio_resample_process(&state, input, 512, output, cap);
    assert(n >= 555 && n <= 559);
    for (size_t i = cap * 2u; i < sizeof output / sizeof output[0]; i++)
        assert((uint16_t)output[i] == UINT16_C(0x5a5a));
    assert(state.input_frames == 512u);
    /* Reject zero frames without consuming input or writing output. */
    before = state;
    assert(vh_audio_resample_process(&state, input, 0, output, cap) == 0);
    assert(memcmp(&state, &before, sizeof state) == 0);
    puts("resampler buffer capacity and sentinels: PASS");
    return 0;
}
