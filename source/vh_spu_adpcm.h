#ifndef VH_SPU_ADPCM_H
#define VH_SPU_ADPCM_H

#include <stddef.h>
#include <stdint.h>

#define VH_SPU_ADPCM_BLOCK_BYTES 16u
#define VH_SPU_ADPCM_BLOCK_FRAMES 28u

/* Raw headerless PS1 VAG sample metadata. Loop markers are -1 if absent.
 * This is a decoder, not a VAB (VH/VB) parser, sequencer or audio device.
 */
typedef struct {
    size_t blocks;
    size_t frames;
    int64_t loop_start_frame;
    int64_t loop_end_frame;
    int64_t first_end_block;
} VhSpuAdpcmInfo;

/* Decode complete, nonempty PS1 SPU-ADPCM blocks into caller-owned PCM.
 * Exactly frames=adpcm_bytes/16*28 samples must fit in output_frames.
 * Returns 0 on success, -1 for invalid input or insufficient capacity.
 * No allocations, global predictor state or input writes. Validation
 * precedes decoding so malformed headers cannot partially alter PCM.
 */
int vh_spu_adpcm_decode(const uint8_t *adpcm, size_t adpcm_bytes,
                        int16_t *out_mono, size_t output_frames,
                        VhSpuAdpcmInfo *info);

#endif
