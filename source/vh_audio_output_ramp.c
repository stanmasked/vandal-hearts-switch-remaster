#include "vh_audio_output_ramp.h"

#include <stdint.h>

void vh_audio_output_ramp_arm(VhAudioOutputRamp *ramp) {
    if (ramp) ramp->position=0;
}

int vh_audio_output_ramp_apply(VhAudioOutputRamp *ramp,
                               int16_t *pcm_stereo, size_t frames) {
    if (!ramp || (!pcm_stereo && frames) || frames > 2048u ||
        ramp->position > VH_AUDIO_OUTPUT_RAMP_FRAMES)
        return -1;

    const unsigned denominator=VH_AUDIO_OUTPUT_RAMP_FRAMES-1u;
    for (size_t i=0;i<frames;i++) {
        const unsigned position=ramp->position;
        if (position<VH_AUDIO_OUTPUT_RAMP_FRAMES) {
            /* Intermediate product fits signed 32 bit even at -32768.
             * Integer division rounds toward zero, matching the
             * existing signed PCM mixer and never overflowing int16.
             */
            const int32_t left=(int32_t)pcm_stereo[i*2u] *
                               (int32_t)position;
            const int32_t right=(int32_t)pcm_stereo[i*2u+1u] *
                                (int32_t)position;
            pcm_stereo[i*2u]=(int16_t)(left/(int32_t)denominator);
            pcm_stereo[i*2u+1u]=(int16_t)(right/(int32_t)denominator);
            ramp->position=position+1u;
        }
    }
    return 0;
}
