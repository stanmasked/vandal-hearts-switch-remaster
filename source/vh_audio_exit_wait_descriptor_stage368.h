#ifndef VH_AUDIO_EXIT_WAIT_DESCRIPTOR_STAGE368_H
#define VH_AUDIO_EXIT_WAIT_DESCRIPTOR_STAGE368_H

/* Stage368: the *existing* single bounded audoutWaitPlayFinish call's
 * returned descriptor/count, not a service queue measurement or DAC proof.
 * The audio worker writes once. Read/serialize ONLY after thread join.
 * No additional wait, queue query, clock, heap, lock, file or PCM operation.
 * Never export a descriptor address or treat a missing pointer as zero queue.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdatomic.h>
#include "vh_audio_exit_tail_wait_result_stage357.h"

typedef struct {
    unsigned observed;
    uint32_t raw_result;
    uint32_t reported_released_count;
    unsigned returned_pointer_present;
    unsigned returned_pointer_matches_submitted;
} VhAudioExitWaitDescriptor368;

static inline void vh_tail368_reset(VhAudioExitWaitDescriptor368 *w) {
    if (w) *w=(VhAudioExitWaitDescriptor368){0};
}

/* Called AFTER the original wait and existing lease decision, solely
 * comparing pointer identity. A mismatch NEVER changes PCM ownership.
 */
static inline int vh_tail368_record(
        VhAudioExitWaitDescriptor368 *w,uint32_t raw_result,
        uint32_t count,const void *released,const void *submitted) {
    if (!w || w->observed || !submitted) return -1;
    w->raw_result=raw_result;
    w->reported_released_count=count;
    w->returned_pointer_present=released!=NULL ? 1u : 0u;
    w->returned_pointer_matches_submitted=
        released!=NULL && released==submitted ? 1u : 0u;
    w->observed=1u;
    return 0;
}

/* Exactly eight numeric rows after scope,value. Cross-check the
 * independent original Stage351 and Stage357 worker witnesses; do not
 * infer physical playback or a kernel subcall from a service result.
 */
static inline int vh_tail368_write_csv(
        const VhAudioExitWaitDescriptor368 *w,
        const VhAudioTailWaitResult357 *raw_source,
        const VhAudioExitTailReason *reason,FILE *out) {
    if (!w || !raw_source || !reason || !out) return -1;
    const unsigned code=vh_audio_tail_reason_read(reason);
    const unsigned old_seen=atomic_load_explicit(
        &raw_source->observed,memory_order_acquire);
    const unsigned old_raw=atomic_load_explicit(
        &raw_source->raw_result,memory_order_acquire);
    if (code>VH_TAIL_RETURN_CONFIRMED || w->observed>1u ||
        w->returned_pointer_present>1u ||
        w->returned_pointer_matches_submitted>1u ||
        (w->returned_pointer_matches_submitted &&
         !w->returned_pointer_present) ||
        (w->observed!=(unsigned)(code>=VH_TAIL_WAIT_FAILED)) ||
        old_seen!=w->observed || old_raw!=w->raw_result ||
        (!w->observed &&
         (w->raw_result || w->reported_released_count ||
          w->returned_pointer_present || w->returned_pointer_matches_submitted)) ||
        (code==VH_TAIL_WAIT_FAILED && !w->raw_result) ||
        (code>=VH_TAIL_WAIT_EMPTY && w->raw_result) ||
        (code==VH_TAIL_WAIT_EMPTY && w->reported_released_count) ||
        (code==VH_TAIL_RELEASE_MISMATCH && !w->reported_released_count) ||
        (code==VH_TAIL_RETURN_CONFIRMED &&
         (!w->reported_released_count ||
          !w->returned_pointer_matches_submitted)))
        return -1;
    if (fprintf(out,
        "scope,value\n"
        "software_wait_descriptor_only,1\n"
        "wait_observed,%u\n"
        "audout_wait_result_raw,%u\n"
        "released_count_reported,%u\n"
        "returned_pointer_present,%u\n"
        "returned_pointer_matches_submitted,%u\n"
        "stage351_tail_reason_code,%u\n"
        "stage357_raw_result_crosschecked,1\n",
        w->observed,(unsigned)w->raw_result,
        (unsigned)w->reported_released_count,
        w->returned_pointer_present,
        w->returned_pointer_matches_submitted,code)<0) return -1;
    return 8;
}
#endif
