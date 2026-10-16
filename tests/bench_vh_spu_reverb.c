/* Host-only diagnostic benchmark: native STUDIO_C optimized/reference.
 * No speed assertions; runner variability is high in GitHub Actions.
 * All input is synthetic; checksum compares exact output and work area.
 */
#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "vh_spu_reverb.h"

#define BENCH_FRAMES 240000u
static VhSpuReverb reverb;

static uint64_t nanos(struct timespec t) {
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) +
           (uint64_t)t.tv_nsec;
}
static uint64_t hash_step(uint64_t h, int16_t sample) {
    return (h ^ (uint16_t)sample) * UINT64_C(1099511628211);
}

int main(void) {
    struct timespec begin, end;
    if (clock_gettime(CLOCK_MONOTONIC, &begin)) return 1;
    vh_spu_reverb_reset(&reverb);
    uint64_t hash = UINT64_C(1469598103934665603);
    for (unsigned i = 0; i < BENCH_FRAMES; ++i) {
        const int left = i < 180000u ? (int)((i*47u)%26000u)-13000 : 0;
        const int right = i < 180000u ? (int)((i*29u)%23000u)-11500 : 0;
        int wet_l=0, wet_r=0;
        vh_spu_reverb_process(&reverb, left, right, 0.5f,
                              &wet_l, &wet_r);
        hash = hash_step(hash,(int16_t)wet_l);
        hash = hash_step(hash,(int16_t)wet_r);
    }
    for (unsigned i=0; i<VH_REV_SAMPLES; ++i)
        hash=hash_step(hash,reverb.work[i]);
    if (clock_gettime(CLOCK_MONOTONIC, &end)) return 2;
    const uint64_t elapsed=nanos(end)-nanos(begin);
    printf("CHECKSUM %016" PRIx64 "\n",hash);
    printf("FRAMES %u\n",BENCH_FRAMES);
    printf("ELAPSED_NS %" PRIu64 "\n",elapsed);
    printf("FRAMES_PER_SEC %.1f\n",
           elapsed ? (double)BENCH_FRAMES * 1.0e9 / elapsed : 0.0);
    return 0;
}
