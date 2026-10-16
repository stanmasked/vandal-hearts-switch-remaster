#ifndef VH_NATIVE_TONE_H
#define VH_NATIVE_TONE_H

#include <stddef.h>
#include <stdint.h>

/* Generated 440-Hz-ish stereo PCM16 diagnostic at 48,000 Hz.
 * Exact 32-bit integer phase with no math library, heap or original assets.
 * This is a hardware-path test, NOT the original Vandal Hearts soundtrack.
 */
#define VH_NATIVE_TONE_RATE 48000u
#define VH_NATIVE_TONE_FRAMES 800u
#define VH_NATIVE_TONE_CHANNELS 2u
#define VH_NATIVE_TONE_PHASE_STEP UINT32_C(39370534)

typedef struct {
    uint32_t phase;
    uint64_t frames_emitted;
} VhNativeTone;

/* All-or-nothing capacity validation; buffer capacity is stereo frames. */
static inline size_t vh_native_tone_fill(VhNativeTone *tone, int16_t *pcm,
                                         size_t frames, size_t capacity) {
    if (!tone || !pcm || !frames || frames > capacity ||
        frames > (UINT64_MAX - tone->frames_emitted)) {
        return 0;
    }
    uint32_t phase = tone->phase;
    for (size_t i = 0; i < frames; ++i) {
        const uint32_t position = phase >> 16;
        const int32_t triangle = position < 32768u
            ? (int32_t)position - 16384
            : 49152 - (int32_t)position;
        const int16_t sample = (int16_t)(triangle / 4);
        pcm[i * 2] = sample;
        pcm[i * 2 + 1] = sample;
        phase += VH_NATIVE_TONE_PHASE_STEP;
    }
    tone->phase = phase;
    tone->frames_emitted += frames;
    return frames;
}

#endif
