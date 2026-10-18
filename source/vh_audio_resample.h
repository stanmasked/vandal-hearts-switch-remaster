#ifndef VH_AUDIO_RESAMPLE_H
#define VH_AUDIO_RESAMPLE_H

#include <stddef.h>
#include <stdint.h>

/* Stateful conversion from the 44.1-kHz PS1 SPU clock to the native
 * Nintendo Switch audout 48-kHz clock. Both are signed stereo PCM16.
 * Integer linear interpolation, phase continues across input blocks.
 * No heap, no game data, no dynamic OS services.
 */
#define VH_NATIVE_AUDOUT_RATE 48000u
#define VH_AUDIO_RESAMPLE_MAX_FRAMES 640u

typedef struct {
    uint64_t input_frames;
    uint64_t next_output_tick; /* source frame position × 48000 */
    int16_t previous_left, previous_right;
    int have_previous;
} VhAudioResample;

void vh_audio_resample_reset(VhAudioResample *state);

/* Process 1..512 input stereo frames. Returns generated output frames
 * (can be 0 for capacity errors); on invalid capacity state is unchanged.
 * output_capacity is measured in stereo frames (not bytes).
 */
size_t vh_audio_resample_process(VhAudioResample *state,
                                 const int16_t *input, size_t input_frames,
                                 int16_t *output, size_t output_capacity);

#endif
