#ifndef VH_AUDIO_PAGE_TELEMETRY_H
#define VH_AUDIO_PAGE_TELEMETRY_H

#include <stdint.h>
#include <limits.h>
#include "vh_audio_compute_wait_join.h"
#include "vh_audio_listening_marks.h"

/* Commit one *returned* logical PCM page to two independent in-memory
 * diagnostic accumulators as a single no-partial-write transaction.
 * Invoke only AFTER the exact audout buffer was returned, and after
 * the seam classifier identified this page's audout wait band.
 *
 * Stage only the small DSP/audout joint counters (not a copy of the
 * 32-page listening ring). Its existing record function checks its
 * own bounds without mutation on failure. The listening recorder
 * also validates all of its bounds BEFORE mutating the ring. Thus
 * publishing the staged joint counters LAST is non-failing.
 *
 * The caller serializes these operations on the owning audio thread.
 * No rendering, PCM contents, heap, SD writes or additional polling.
 */
static inline int vh_audio_page_telemetry_record(
    VhAudioComputeWaitJoin *joint, VhAudioListeningMarks *marks,
    unsigned wait_band, unsigned scene_boundary, unsigned retried,
    uint32_t seam_step, unsigned dsp_over_budget) {
    if (!joint || !marks) return -1;
    const VhAudioComputeWaitBucket *a=&joint->ordinary;
    const VhAudioComputeWaitBucket *b=&joint->first_after_switch;
    /* Reject duplicate/skipped pages and previously diverged totals
     * BEFORE either recorder can accept a new page.
     */
    if (a->returned>UINT64_MAX-b->returned ||
        a->dsp_over>UINT64_MAX-b->dsp_over ||
        a->both_over_2x>UINT64_MAX-b->both_over_2x ||
        a->both_over_4x>UINT64_MAX-b->both_over_4x ||
        a->returned+b->returned!=marks->returned_pages ||
        vh_audio_listening_verify_dsp_totals(
            marks,a->dsp_over+b->dsp_over,
            a->both_over_2x+b->both_over_2x,
            a->both_over_4x+b->both_over_4x))
        return -1;

    VhAudioComputeWaitJoin next=*joint;
    if (vh_audio_compute_wait_record(
            &next,scene_boundary,dsp_over_budget,wait_band))
        return -1;
    if (vh_audio_listening_observe(
            marks,wait_band,scene_boundary,retried,seam_step,
            dsp_over_budget))
        return -1;
    *joint=next;
    return 0;
}
#endif
