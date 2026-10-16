#ifndef VH_SPU_REVERB_H
#define VH_SPU_REVERB_H

#include <stdint.h>

/* PS1 SPU STUDIO_C wet processor from the PC port, 44100 Hz in/out
 * and a 22050 Hz comb/all-pass work area. Caller owns the state.
 * Processes one stereo sample per call, including silent tail frames.
 */
#define VH_REV_FIR_TAPS 39u
#define VH_REV_SAMPLES 0x37F0u

typedef struct {
    int16_t work[VH_REV_SAMPLES];
    int16_t in_l[VH_REV_FIR_TAPS], in_r[VH_REV_FIR_TAPS];
    int16_t out_l[VH_REV_FIR_TAPS], out_r[VH_REV_FIR_TAPS];
    int cursor, in_cursor, out_cursor, phase;
} VhSpuReverb;

void vh_spu_reverb_reset(VhSpuReverb *state);
void vh_spu_reverb_process(VhSpuReverb *state, int send_left,
                           int send_right, float depth,
                           int *wet_left, int *wet_right);

#endif
