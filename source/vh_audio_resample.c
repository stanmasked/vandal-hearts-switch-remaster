#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

#include <limits.h>
#include <string.h>

void vh_audio_resample_reset(VhAudioResample *state) {
    if (state) memset(state, 0, sizeof(*state));
}

static int16_t interpolate(int16_t a, int16_t b, uint32_t fraction) {
    const int64_t weighted =
        (int64_t)a * (VH_NATIVE_AUDOUT_RATE - fraction) +
        (int64_t)b * fraction;
    int64_t sample = weighted / VH_NATIVE_AUDOUT_RATE;
    if (sample > INT16_MAX) sample = INT16_MAX;
    if (sample < INT16_MIN) sample = INT16_MIN;
    return (int16_t)sample;
}

size_t vh_audio_resample_process(VhAudioResample *state,
                                 const int16_t *input, size_t input_frames,
                                 int16_t *output, size_t output_capacity) {
    if (!state || !input || !output || input_frames == 0 ||
        input_frames > VH_AUDIO_BLOCK_FRAMES ||
        output_capacity > SIZE_MAX / 2u) return 0;
    /* Conservative output bound includes a prior-block interpolation
     * sample. Reject insufficient output storage without changing state.
     */
    const size_t required =
        ((input_frames * VH_NATIVE_AUDOUT_RATE +
          VH_AUDIO_SAMPLE_RATE - 1u) / VH_AUDIO_SAMPLE_RATE) + 2u;
    if (output_capacity < required ||
        state->input_frames > UINT64_MAX - input_frames ||
        state->next_output_tick > UINT64_MAX -
                                     required * VH_AUDIO_SAMPLE_RATE)
        return 0;

    const uint64_t start = state->input_frames;
    const uint64_t end = start + input_frames;
    size_t written = 0;
    for (;;) {
        const uint64_t index =
            state->next_output_tick / VH_NATIVE_AUDOUT_RATE;
        const uint32_t fraction =
            (uint32_t)(state->next_output_tick % VH_NATIVE_AUDOUT_RATE);
        if (index >= end) break;
        if (index < start && (!state->have_previous ||
                              index != start - 1u)) break;
        if (index == end - 1u && fraction != 0u) break;

        for (unsigned ch = 0; ch < 2u; ++ch) {
            const int16_t a = index < start
                ? (ch ? state->previous_right : state->previous_left)
                : input[2u * (size_t)(index - start) + ch];
            const int16_t b = fraction == 0u ? a :
                input[2u * (size_t)(index + 1u - start) + ch];
            output[2u * written + ch] = interpolate(a, b, fraction);
        }
        ++written;
        state->next_output_tick += VH_AUDIO_SAMPLE_RATE;
    }
    state->input_frames = end;
    state->previous_left = input[2u * (input_frames - 1u)];
    state->previous_right = input[2u * (input_frames - 1u) + 1u];
    state->have_previous = 1;
    return written;
}
