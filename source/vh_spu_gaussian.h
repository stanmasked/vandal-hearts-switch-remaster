#ifndef VH_SPU_GAUSSIAN_H
#define VH_SPU_GAUSSIAN_H

#include <stddef.h>
#include <stdint.h>

/* Integer 4-tap fetch using the PC-port's 512 PlayStation SPU
 * coefficients. Phase is a 20.12 fixed-point sample position.
 * Prior-to-start history is zero; looped history reads from the
 * loop tail. No heap allocation or dynamic source asset access.
 */
int16_t vh_spu_gaussian_sample(
    const int16_t *pcm, size_t frames, uint64_t phase,
    int64_t loop_start, int64_t loop_end, int looped);

#endif
