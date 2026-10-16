#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../source/vh_native_tone.h"

static void test_stereo_phase_continuity(void) {
    enum { COUNT = 2400 };
    int16_t contiguous[COUNT * 2];
    int16_t chunked[COUNT * 2];
    VhNativeTone whole = {0, 0};
    VhNativeTone segments = {0, 0};
    assert(vh_native_tone_fill(&whole, contiguous, COUNT, COUNT) == COUNT);
    for (unsigned i = 0; i < 3; ++i) {
        assert(vh_native_tone_fill(&segments,
                                   chunked + i * VH_NATIVE_TONE_FRAMES * 2,
                                   VH_NATIVE_TONE_FRAMES,
                                   VH_NATIVE_TONE_FRAMES) == VH_NATIVE_TONE_FRAMES);
    }
    assert(memcmp(contiguous, chunked, sizeof(contiguous)) == 0);
    assert(whole.phase == segments.phase);
    assert(whole.frames_emitted == COUNT);
    assert(segments.frames_emitted == COUNT);
    int min = INT_MAX, max = INT_MIN;
    unsigned transitions = 0;
    for (unsigned i = 0; i < COUNT; ++i) {
        int sample = contiguous[i * 2];
        assert(sample == contiguous[i * 2 + 1]);
        if (sample < min) min = sample;
        if (sample > max) max = sample;
        if (i && contiguous[(i - 1) * 2] != sample) ++transitions;
    }
    assert(min < -2000 && max > 2000);
    assert(transitions > 100);
}

static void test_bad_capacity_leaves_state_and_buffer_untouched(void) {
    VhNativeTone tone = {1234u, 777u}, old = tone;
    int16_t output[16];
    for (unsigned i = 0; i < 16; ++i) output[i] = 123;
    assert(!vh_native_tone_fill(&tone, output, 9, 8));
    assert(!vh_native_tone_fill(NULL, output, 2, 8));
    assert(!vh_native_tone_fill(&tone, NULL, 2, 8));
    assert(!vh_native_tone_fill(&tone, output, 0, 8));
    assert(memcmp(&tone, &old, sizeof(tone)) == 0);
    for (unsigned i = 0; i < 16; ++i) assert(output[i] == 123);
}

static void test_48k_sample_count_and_phase_wrap(void) {
    VhNativeTone tone = {UINT32_MAX - 15u, 0};
    int16_t output[VH_NATIVE_TONE_FRAMES * 2];
    for (unsigned n = 0; n < 60; ++n) {
        assert(vh_native_tone_fill(&tone, output, VH_NATIVE_TONE_FRAMES,
                                   VH_NATIVE_TONE_FRAMES) == VH_NATIVE_TONE_FRAMES);
    }
    assert(tone.frames_emitted == VH_NATIVE_TONE_RATE);
    const uint32_t expected = (UINT32_MAX - 15u)
        + (uint32_t)((uint64_t)VH_NATIVE_TONE_PHASE_STEP * VH_NATIVE_TONE_RATE);
    assert(tone.phase == expected);
}

int main(void) {
    test_stereo_phase_continuity();
    test_bad_capacity_leaves_state_and_buffer_untouched();
    test_48k_sample_count_and_phase_wrap();
    puts("Native stereo PCM16 audio-generator host tests passed");
    return 0;
}
