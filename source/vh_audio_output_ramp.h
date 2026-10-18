#ifndef VH_AUDIO_OUTPUT_RAMP_H
#define VH_AUDIO_OUTPUT_RAMP_H

#include <stddef.h>
#include <stdint.h>

/* At 48,000 Hz, 192 output frames are a four-millisecond linear
 * de-click fade-in after starting or recreating audout. This only
 * changes the final output page; SEQ, SPU and resampler clocks stay
 * untouched. Do not apply again when retrying an already prepared
 * PCM page after an audout submission error.
 */
#define VH_AUDIO_OUTPUT_RAMP_FRAMES 192u

typedef struct {
    unsigned position; /* [0..RAMP_FRAMES], saturated once complete */
} VhAudioOutputRamp;

/* Arm whenever output transitions from stopped to playing. */
void vh_audio_output_ramp_arm(VhAudioOutputRamp *ramp);

/* In-place interleaved PCM16 stereo; 0 means success, -1 for bad args.
 * A full-strength sample at frame RAMP_FRAMES-1 guarantees continuity
 * to an unchanged following page. A partial page resumes the ramp in
 * the next page, with no allocation or retained PCM pointers.
 */
int vh_audio_output_ramp_apply(VhAudioOutputRamp *ramp,
                               int16_t *pcm_stereo, size_t frames);

#endif
