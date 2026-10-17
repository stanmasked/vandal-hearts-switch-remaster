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

/* End-of-run and pre-commit cross-check for the most recent RETURNED
 * PCM page. Final failed audout submissions are intentionally absent
 * from BOTH objects: they may extend wait buckets, but never update
 * the last PCM seam or the human listening ring.
 *
 * All operations are read-only. The ring may wrap every 32 pages;
 * the tail is always at (returned_pages - 1) % 32. No PCM samples
 * or input-event history are inspected, copied or retained.
 */
static inline int vh_audio_last_returned_page_verify(
    const VhAudioPcmSeams *seams, const VhAudioListeningMarks *marks,
    uint64_t expected_returned) {
    if (!seams || !marks ||
        seams->delivered_pages!=expected_returned ||
        marks->returned_pages!=expected_returned ||
        (seams->has_previous!=0 && seams->has_previous!=1))
        return -1;
    if (!expected_returned)
        return (seams->has_previous || seams->last_wait_band ||
            seams->first_wait_band || seams->last_abs_step ||
            seams->last_l || seams->last_r) ? -1 : 0;

    if (!seams->has_previous ||
        seams->last_wait_band>=VH_AUDIO_WAIT_BANDS ||
        seams->first_wait_band>=VH_AUDIO_WAIT_BANDS ||
        seams->last_abs_step>65535u) return -1;
    const unsigned slot=(unsigned)(
        (expected_returned-1u)%VH_LISTEN_RECENT_PAGES);
    const VhListenPage *tail=&marks->recent[slot];
    if (tail->wait_band>=VH_AUDIO_WAIT_BANDS ||
        tail->scene_boundary>1u || tail->retry>1u ||
        tail->dsp_over_budget>1u || tail->seam_step>65535u ||
        tail->wait_band!=seams->last_wait_band ||
        tail->seam_step!=seams->last_abs_step)
        return -1;
    /* No previous tail exists on the first returned page. */
    if (expected_returned==1u &&
        (seams->last_abs_step!=0u ||
         seams->last_wait_band!=seams->first_wait_band))
        return -1;
    return 0;
}

/* Atomic transaction for ONE successfully returned logical PCM page:
 * 1. Stage latency category and inter-page PCM16 seam counters.
 * 2. Stage joint DSP/wait counters.
 * 3. Record into the A/B ring (its own recorder validates before write).
 * 4. Publish the three staged smaller objects without further failure.
 *
 * A malformed input or overflow in ANY one of the four systems must
 * leave all four byte-for-byte unchanged. No PCM is stored or copied,
 * no additional audio callbacks, allocations, locks or SD traffic.
 * One owner thread guarantees there are no concurrent mutations.
 *
 * Terminal FAILED logical pages are not handled here: they must
 * update only scene wait histograms using delivered=0.
 */
static inline int vh_audio_returned_page_telemetry_record(
    VhAudioSceneWaits *waits, VhAudioPcmSeams *seams,
    VhAudioComputeWaitJoin *joint, VhAudioListeningMarks *marks,
    const int16_t *pcm, size_t frames, unsigned scene_boundary,
    const VhAudioSubmitTiming *before, const VhAudioSubmitTiming *after,
    uint64_t tick_frequency, unsigned dsp_over_budget) {
    if (!waits || !seams || !joint || !marks || !pcm ||
        !before || !after || scene_boundary>1u || dsp_over_budget>1u ||
        after->calls<=before->calls ||
        vh_audio_last_returned_page_verify(
            seams,marks,seams->delivered_pages))
        return -1;
    VhAudioSceneWaits next_waits=*waits;
    VhAudioPcmSeams next_seams=*seams;
    VhAudioComputeWaitJoin next_joint=*joint;
    if (vh_audio_output_record_scene_page(
            &next_waits,before,after,tick_frequency,frames,
            (int)scene_boundary,1) ||
        vh_audio_output_record_pcm_seam(
            &next_seams,pcm,frames,(int)scene_boundary,
            before,after,tick_frequency) ||
        vh_audio_page_telemetry_record(
            &next_joint,marks,next_seams.last_wait_band,
            scene_boundary,
            (unsigned)(after->calls-before->calls>1u),
            next_seams.last_abs_step,dsp_over_budget))
        return -1;
    *waits=next_waits;
    *seams=next_seams;
    *joint=next_joint;
    return 0;
}
#endif
