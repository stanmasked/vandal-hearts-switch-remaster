#ifndef VH_AUDOUT_PRESUBMIT_WITNESS_H
#define VH_AUDOUT_PRESUBMIT_WITNESS_H

#include <stddef.h>
#include <stdint.h>

/* Opt-in, generated-only research. No libnx, allocations or audio I/O.
 * Limit CPU work to the first eight normal audout pages, NOT stop-taper
 * or speaker/DAC output. One owner thread calls all functions.
 */
#define VH_AUDOUT_PRESUBMIT_CAP 8u
#define VH_AUDOUT_PRESUBMIT_MAX_FRAMES 640u

typedef struct {
    uint64_t fnv1a64;
    uint32_t crc32;
    uint32_t frames;
    uint32_t attempts;
    uint32_t successful_returns;
} VhAudoutPresubmitPage;

typedef struct {
    VhAudoutPresubmitPage page[VH_AUDOUT_PRESUBMIT_CAP];
    unsigned count;
    unsigned pending; /* armed but not yet successfully returned */
    unsigned checked; /* at least one verified call since last return */
    unsigned mismatches;
} VhAudoutPresubmitWitness;

void vh_audout_presubmit_reset(VhAudoutPresubmitWitness *w);

/* Seal a prepared, post-ramp PCM16 stereo page exactly once, before
 * output-recovery starts. Returns 0=armed, 1=capacity exhausted, -1=bad.
 * No PCM pointers are retained.
 */
int vh_audout_presubmit_arm(VhAudoutPresubmitWitness *w,
                            const int16_t *pcm,size_t frames);

/* Called immediately before audoutPlayBuffer using the exact descriptor
 * payload. Compare frames plus two independently computed fingerprints.
 * A retry MUST present identical PCM bytes (including any start ramp).
 * Returns 0=match, 1=monitor capacity exhausted, -1=mismatch/bad state.
 */
int vh_audout_presubmit_before_call(VhAudoutPresubmitWitness *w,
                                     const int16_t *pcm,size_t frames);

/* Call after a verified audoutPlayBuffer attempt with returned=1 only
 * when the exact descriptor lease was released. On error keep the same
 * sealed page for a retry; do not ever sample PCM after giving the lease
 * to audout. Returns 0=recorded, 1=unmonitored, -1=bad state.
 */
int vh_audout_presubmit_return(VhAudoutPresubmitWitness *w,int returned);

#endif
