#include "vh_spu_adpcm.h"

#include <limits.h>
#include <stdint.h>

static const int coeff_pos[5] = {0, 60, 115, 98, 122};
static const int coeff_neg[5] = {0, 0, -52, -55, -60};

/* C signed division truncates toward 0; the Python/PS1 reference uses
 * arithmetic right shifts (rounding negative inputs toward -infinity).
 * The actual values here are tightly bounded by signed 16-bit history.
 */
static int64_t floor_div_positive(int64_t value, int64_t divisor) {
    if (value >= 0) return value / divisor;
    return -(((-value) + divisor - 1) / divisor);
}

static int16_t clip16(int64_t sample) {
    if (sample > INT16_MAX) return INT16_MAX;
    if (sample < INT16_MIN) return INT16_MIN;
    return (int16_t)sample;
}

int vh_spu_adpcm_decode(const uint8_t *adpcm, size_t adpcm_bytes,
                        int16_t *out_mono, size_t output_frames,
                        VhSpuAdpcmInfo *info) {
    if (!adpcm || !out_mono || !info || !adpcm_bytes ||
        adpcm_bytes % VH_SPU_ADPCM_BLOCK_BYTES != 0) return -1;
    const size_t blocks = adpcm_bytes / VH_SPU_ADPCM_BLOCK_BYTES;
    if (blocks > SIZE_MAX / VH_SPU_ADPCM_BLOCK_FRAMES) return -1;
    const size_t frames = blocks * VH_SPU_ADPCM_BLOCK_FRAMES;
    if (output_frames < frames || frames > (size_t)INT64_MAX) return -1;

    for (size_t b = 0; b < blocks; ++b) {
        const uint8_t *block = adpcm + b * VH_SPU_ADPCM_BLOCK_BYTES;
        if ((block[0] >> 4) > 4 || (block[0] & 15) > 12 ||
            (block[1] & (uint8_t)~7u) != 0) return -1;
    }

    VhSpuAdpcmInfo result = {blocks, frames, -1, -1, -1};
    int previous = 0;
    int older = 0;
    int64_t loop_mark = -1;
    for (size_t b = 0; b < blocks; ++b) {
        const uint8_t *block = adpcm + b * VH_SPU_ADPCM_BLOCK_BYTES;
        const unsigned shift = block[0] & 15u;
        const unsigned predictor = block[0] >> 4;
        const unsigned flags = block[1];
        if (flags & 4u) loop_mark = (int64_t)(b * VH_SPU_ADPCM_BLOCK_FRAMES);
        if ((flags & 1u) && result.first_end_block < 0)
            result.first_end_block = (int64_t)b;

        for (size_t n = 0; n < VH_SPU_ADPCM_BLOCK_FRAMES; ++n) {
            const uint8_t coded = block[2u + n / 2u];
            const unsigned nibble = n & 1u ? coded >> 4 : coded & 15u;
            const int signed_nibble = nibble & 8u ? (int)nibble - 16 : (int)nibble;
            const int64_t unpacked = (int64_t)signed_nibble * 4096;
            const int64_t predicted = ((int64_t)previous * coeff_pos[predictor]
                                     + (int64_t)older * coeff_neg[predictor] + 32);
            const int64_t current = floor_div_positive(unpacked, INT64_C(1) << shift)
                                   + floor_div_positive(predicted, 64);
            const int16_t clipped = clip16(current);
            out_mono[b * VH_SPU_ADPCM_BLOCK_FRAMES + n] = clipped;
            older = previous;
            previous = clipped;
        }
        if ((flags & 3u) == 3u) {
            result.loop_start_frame = loop_mark < 0 ? 0 : loop_mark;
            result.loop_end_frame = (int64_t)((b + 1u) * VH_SPU_ADPCM_BLOCK_FRAMES);
        }
    }
    *info = result;
    return 0;
}
