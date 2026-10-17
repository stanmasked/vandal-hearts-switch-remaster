#ifndef VH_AUDIO_COMPUTE_WAIT_JOIN_H
#define VH_AUDIO_COMPUTE_WAIT_JOIN_H

#include <stdint.h>
#include <limits.h>
#include "vh_audio_compute_timing.h"
#include "vh_audio_output_recovery.h"

/* Joint *returned-page* telemetry: did a slow DSP render and a long
 * blocking audout wait occur on the SAME logical audio page?
 * All observations are counters, not timestamped traces or audio.
 * Concurrence does NOT establish an audible click or causality.
 */
typedef struct {
    uint64_t returned, dsp_over, wait_over_2x, both_over_2x;
    uint64_t wait_over_4x, both_over_4x;
} VhAudioComputeWaitBucket;

typedef struct {
    VhAudioComputeWaitBucket ordinary, first_after_switch;
} VhAudioComputeWaitJoin;

/* Call strictly once AFTER audout returned its descriptor and PCM seam
 * classification succeeded. Not on terminally failed pages.
 * All invalid inputs/overflows are rejected without mutation.
 */
static inline int vh_audio_compute_wait_record(
    VhAudioComputeWaitJoin *j, unsigned scene_boundary,
    unsigned dsp_over_budget, unsigned wait_band) {
    if (!j || scene_boundary>1u || dsp_over_budget>1u ||
        wait_band>=VH_AUDIO_WAIT_BANDS) return -1;
    VhAudioComputeWaitBucket *b=scene_boundary
        ? &j->first_after_switch : &j->ordinary;
    const uint64_t long2=(uint64_t)(wait_band>=2u);
    const uint64_t long4=(uint64_t)(wait_band==3u);
    const uint64_t both2=(uint64_t)(dsp_over_budget && long2);
    const uint64_t both4=(uint64_t)(dsp_over_budget && long4);
    if (b->returned==UINT64_MAX ||
        b->dsp_over>UINT64_MAX-dsp_over_budget ||
        b->wait_over_2x>UINT64_MAX-long2 ||
        b->both_over_2x>UINT64_MAX-both2 ||
        b->wait_over_4x>UINT64_MAX-long4 ||
        b->both_over_4x>UINT64_MAX-both4) return -1;
    ++b->returned;
    b->dsp_over+=dsp_over_budget;
    b->wait_over_2x+=long2;
    b->both_over_2x+=both2;
    b->wait_over_4x+=long4;
    b->both_over_4x+=both4;
    return 0;
}

static inline int vh_audio_compute_wait_bucket_verify(
    const VhAudioComputeWaitBucket *j,
    const VhAudioComputeBucket *compute,
    const VhAudioPageWaitBucket *wait,
    uint64_t returned,
    unsigned last_missing_is_this_group,
    unsigned last_dsp_over) {
    if (!j || !compute || !wait || last_missing_is_this_group>1u ||
        last_dsp_over>1u ||
        wait->pages<wait->failed_pages ||
        wait->wait_le_4pages<wait->failed_in_band[2] ||
        wait->wait_gt_4pages<wait->failed_in_band[3] ||
        wait->wait_le_4pages>UINT64_MAX-wait->wait_gt_4pages ||
        wait->failed_in_band[2]>UINT64_MAX-wait->failed_in_band[3])
        return -1;
    const uint64_t wait2=wait->wait_le_4pages+wait->wait_gt_4pages;
    const uint64_t failed2=wait->failed_in_band[2]+wait->failed_in_band[3];
    if (wait2<failed2 ||
        wait->pages-wait->failed_pages!=returned ||
        compute->rendered_pages<returned ||
        compute->rendered_pages-returned!=last_missing_is_this_group ||
        compute->over_budget<(uint64_t)(last_missing_is_this_group &&
                                        last_dsp_over))
        return -1;
    const uint64_t returned_over=
        compute->over_budget-(uint64_t)(last_missing_is_this_group &&
                                        last_dsp_over);
    const uint64_t returned_wait2=wait2-failed2;
    const uint64_t returned_wait4=
        wait->wait_gt_4pages-wait->failed_in_band[3];
    if (j->returned!=returned || j->dsp_over!=returned_over ||
        j->wait_over_2x!=returned_wait2 ||
        j->wait_over_4x!=returned_wait4 ||
        j->both_over_2x>j->dsp_over ||
        j->both_over_2x>j->wait_over_2x ||
        j->both_over_4x>j->both_over_2x ||
        j->both_over_4x>j->wait_over_4x ||
        j->wait_over_4x>j->wait_over_2x ||
        j->wait_over_2x>returned ||
        j->dsp_over>returned ||
        /* A set intersection cannot be smaller than the excess of
         * DSP overruns over all pages outside the slow-wait set.
         * The >2x-but-not->4x intersection also has a strict cap.
         */
        j->both_over_2x<j->dsp_over-
            (j->dsp_over>returned-j->wait_over_2x
                ? returned-j->wait_over_2x : j->dsp_over) ||
        j->both_over_4x<j->dsp_over-
            (j->dsp_over>returned-j->wait_over_4x
                ? returned-j->wait_over_4x : j->dsp_over) ||
        j->both_over_2x-j->both_over_4x>
            j->wait_over_2x-j->wait_over_4x)
        return -1;
    return 0;
}

/* Exact category and histogram reconciliation. Per-band terminal
 * failure metadata is checked by the separate original audout audit.
 * This cross-checks the new joint counts against those measurements,
 * and subtracts DSP overrun of the one possible undelivered last page.
 */
static inline int vh_audio_compute_wait_verify(
    const VhAudioComputeWaitJoin *j, const VhAudioComputeTiming *compute,
    const VhAudioSceneWaits *wait,
    uint64_t delivered_pages, uint64_t returned_switch_pages) {
    if (!j || !compute || !wait ||
        vh_audio_compute_verify(compute,delivered_pages,
                                returned_switch_pages))
        return -1;
    const unsigned missing=(unsigned)(
        compute->rendered_pages-delivered_pages);
    return vh_audio_compute_wait_bucket_verify(
            &j->ordinary,&compute->ordinary,&wait->ordinary,
            delivered_pages-returned_switch_pages,
            (unsigned)(missing && !compute->last_after_switch),
            compute->last_over_budget) ||
           vh_audio_compute_wait_bucket_verify(
            &j->first_after_switch,&compute->first_after_switch,
            &wait->first_after_switch,returned_switch_pages,
            (unsigned)(missing && compute->last_after_switch),
            compute->last_over_budget) ? -1 : 0;
}
#endif
