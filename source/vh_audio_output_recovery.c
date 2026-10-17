#include "vh_audio_output_recovery.h"
#include "vh_audio_resample.h"

#include <limits.h>

int vh_audio_page_lease_begin(VhAudioPageLease *lease,
                              const void *descriptor) {
    if (!lease || !descriptor || lease->in_flight) return -1;
    lease->in_flight=descriptor;
    return 0;
}

int vh_audio_page_lease_return(VhAudioPageLease *lease,
                               const void *returned_descriptor) {
    if (!lease || !lease->in_flight ||
        lease->in_flight != returned_descriptor) return -1;
    lease->in_flight=NULL;
    return 0;
}

int vh_audio_page_lease_stopped(VhAudioPageLease *lease,
                                 int stop_result) {
    if (!lease || stop_result) return -1;
    /* Only the caller can confirm the backend stop succeeded. */
    lease->in_flight=NULL;
    return 0;
}

int vh_audio_page_lease_ready(const VhAudioPageLease *lease) {
    return lease && !lease->in_flight;
}

int vh_audio_timing_fault_arm(VhAudioTimingFaultInjection *s) {
    if(!s || s->armed || s->injected) return -1;
    s->armed=1u;
    return 0;
}

uint64_t vh_audio_timing_fault_frequency(
    VhAudioTimingFaultInjection *s, int exact_returned,
    uint64_t actual_frequency) {
    /* An undelivered page cannot consume an intentional timing fault.
     * Once a real descriptor is returned, zero Hz is injected only in
     * the timing accumulator; the transport result remains untouched. */
    if(s && s->armed && exact_returned) {
        s->armed=0u;
        s->injected=1u;
        return 0u;
    }
    return actual_frequency;
}

int vh_audio_submit_fault_arm(VhAudioSubmitFaultInjection *s) {
    if (!s || s->armed || s->injected) return -1;
    s->armed=1u;
    return 0;
}

int vh_audio_submit_fault_consume(VhAudioSubmitFaultInjection *s) {
    if (!s || s->armed!=1u || s->injected) return 0;
    s->armed=0u;
    s->injected=1u;
    return 1;
}

/* The fake failure is a wrapper attempt, never audoutPlayBuffer. */
int vh_audio_output_record_synthetic_submit_failure(
    VhAudioSubmitTiming *timing, uint64_t frequency, size_t frames) {
    if (!timing || timing->synthetic_failed_submissions==UINT64_MAX)
        return -1;
    VhAudioSubmitTiming next=*timing;
    if (vh_audio_output_record_submit_timing(
            &next,0u,frequency,frames,0))
        return -1;
    ++next.synthetic_failed_submissions;
    *timing=next;
    return 0;
}

int vh_audio_output_verify_submit_injection(
    const VhAudioSubmitFaultInjection *s,
    const VhAudioSubmitTiming *timing,
    const VhAudioOutputRecovery *recovery) {
    if (!s || !timing || !recovery || s->armed>1u ||
        s->injected>1u || (s->armed && s->injected) ||
        timing->synthetic_failed_submissions!=s->injected ||
        timing->synthetic_failed_submissions>timing->failed_submissions ||
        timing->synthetic_failed_submissions>timing->calls ||
        timing->failed_submissions!=recovery->submit_failures)
        return -1;
    /* A consumed fake failure alone is not a recovered PCM page.
     * Independently reconcile ALL wrapper-level attempts: one accepted
     * exact descriptor per successful logical page, every other attempt
     * a reported failure (including the explicitly marked virtual one).
     * A bad ZL clock must not be mistaken for a valid ZR recovery. */
    if (s->injected) {
        if (!recovery->restart_attempts || !recovery->recoveries ||
            !recovery->pages_submitted ||
            recovery->recoveries>recovery->restart_attempts ||
            timing->calls<timing->failed_submissions ||
            timing->calls-timing->failed_submissions!=
                recovery->pages_submitted)
            return -1;
        return 2;
    }
    return s->armed ? 1 : 0;
}

int vh_audio_output_transport_outcome(
    int descriptor_returned, int timing_result,
    VhAudioTransportTimingHealth *health) {
    /* A rejected timing sample is NOT a rejected audout descriptor.
     * Saturate the diagnostic count, never wrap or force a replay. */
    if(timing_result && health) {
        health->timing_fault=1u;
        if(descriptor_returned &&
           health->delivered_without_timing!=UINT64_MAX)
            ++health->delivered_without_timing;
    }
    return descriptor_returned ? 0 : -1;
}

int vh_audio_output_verify_transport_health(
    const VhAudioTransportTimingHealth *health,
    const VhAudioOutputRecovery *recovery) {
    if(!health || !recovery || health->timing_fault>1u ||
       (health->delivered_without_timing && !health->timing_fault) ||
       health->delivered_without_timing>recovery->pages_submitted)
        return -1;
    return health->timing_fault ? 1 : 0;
}

int vh_audio_output_verify_timing_injection(
    const VhAudioTimingFaultInjection *injection,
    const VhAudioTransportTimingHealth *health,
    const VhAudioOutputRecovery *recovery) {
    if (!injection || !health || !recovery ||
        injection->armed>1u || injection->injected>1u ||
        (injection->armed && injection->injected) ||
        vh_audio_output_verify_transport_health(health,recovery)<0)
        return -1;
    /* A requested bad clock is consumed ONLY on an exact PCM return.
     * The rejected timing result must therefore be visible as a
     * successfully submitted page with a sticky diagnostic fault. */
    if (injection->injected) {
        if (!health->timing_fault || !health->delivered_without_timing)
            return -1;
        return 2;
    }
    return injection->armed ? 1 : 0;
}

uint64_t vh_audio_output_ticks_to_us(uint64_t ticks,
                                     uint64_t tick_frequency) {
    if (!tick_frequency) return 0;
    const uint64_t seconds=ticks/tick_frequency;
    const uint64_t remainder=ticks%tick_frequency;
    /* Expected Switch tick rates are orders of magnitude smaller
     * than UINT64_MAX/1,000,000. Guard atypical synthetic inputs. */
    if (seconds>UINT64_MAX/UINT64_C(1000000) ||
        remainder>UINT64_MAX/UINT64_C(1000000))
        return UINT64_MAX;
    const uint64_t whole=seconds*UINT64_C(1000000);
    const uint64_t fraction=remainder*UINT64_C(1000000)/tick_frequency;
    if (fraction>UINT64_MAX-whole) return UINT64_MAX;
    return whole+fraction;
}

int vh_audio_output_record_submit_timing(
    VhAudioSubmitTiming *timing, uint64_t elapsed_ticks,
    uint64_t tick_frequency, size_t frames, int accepted) {
    if (!timing || !tick_frequency || !frames ||
        frames>VH_AUDIO_RESAMPLE_MAX_FRAMES ||
        tick_frequency>UINT64_MAX/frames ||
        timing->calls==UINT64_MAX ||
        timing->total_ticks>UINT64_MAX-elapsed_ticks)
        return -1;
    const uint64_t page_ticks=(uint64_t)frames*tick_frequency/
                              VH_NATIVE_AUDOUT_RATE;
    const int slow=elapsed_ticks>page_ticks;
    const int failed=!accepted;
    if ((slow && timing->waits_longer_than_page==UINT64_MAX) ||
        (failed && timing->failed_submissions==UINT64_MAX))
        return -1;
    ++timing->calls;
    timing->total_ticks+=elapsed_ticks;
    if (elapsed_ticks>timing->max_ticks)
        timing->max_ticks=elapsed_ticks;
    timing->waits_longer_than_page+=(unsigned)slow;
    timing->failed_submissions+=(unsigned)failed;
    return 0;
}

int vh_audio_output_record_scene_page(
    VhAudioSceneWaits *groups,
    const VhAudioSubmitTiming *before, const VhAudioSubmitTiming *after,
    uint64_t tick_frequency, size_t frames, int first_after_switch,
    int delivered) {
    if (!groups || !before || !after || !frames ||
        frames>VH_AUDIO_RESAMPLE_MAX_FRAMES || !tick_frequency ||
        tick_frequency>UINT64_MAX/frames ||
        after->calls<=before->calls ||
        after->total_ticks<before->total_ticks ||
        after->waits_longer_than_page<before->waits_longer_than_page ||
        after->failed_submissions<before->failed_submissions)
        return -1;

    const uint64_t attempts=after->calls-before->calls;
    const uint64_t failures=
        after->failed_submissions-before->failed_submissions;
    const uint64_t slow_calls=
        after->waits_longer_than_page-before->waits_longer_than_page;
    const uint64_t ticks=after->total_ticks-before->total_ticks;
    /* On a delivered page the recovery helper accepts exactly one
     * backend invocation. On terminal failure every observed raw
     * invocation must be a failure. Stop/open itself is not timed.
     */
    if (attempts>VH_AUDIO_OUTPUT_RESTART_LIMIT+1u ||
        failures>attempts || slow_calls>attempts ||
        attempts-failures!=(delivered ? 1u : 0u))
        return -1;

    VhAudioPageWaitBucket *bucket=first_after_switch
        ? &groups->first_after_switch : &groups->ordinary;
    const uint64_t was_slow=(slow_calls!=0);
    const uint64_t retried=(attempts>1u);
    const uint64_t failed=(!delivered);
    /* Compare the logical page's total backend wait with its own PCM
     * duration, not a fixed 512/44100 estimate. Guard x2 and x4
     * thresholds before multiplying. Exactly ONE histogram bin wins.
     */
    const uint64_t nominal=(uint64_t)frames*tick_frequency/
                           VH_NATIVE_AUDOUT_RATE;
    const unsigned wait_bin=
        ticks<=nominal ? 0u :
        nominal>UINT64_MAX/2u || ticks<=nominal*2u ? 1u :
        nominal>UINT64_MAX/4u || ticks<=nominal*4u ? 2u : 3u;
    uint64_t *const bins[]={
        &bucket->wait_le_page,&bucket->wait_le_2pages,
        &bucket->wait_le_4pages,&bucket->wait_gt_4pages
    };
    if (*bins[wait_bin]==UINT64_MAX ||
        (failed && bucket->failed_in_band[wait_bin]==UINT64_MAX) ||
        bucket->pages==UINT64_MAX ||
        bucket->total_ticks>UINT64_MAX-ticks ||
        bucket->slow_pages>UINT64_MAX-was_slow ||
        bucket->retried_pages>UINT64_MAX-retried ||
        bucket->failed_pages>UINT64_MAX-failed)
        return -1;
    ++bucket->pages;
    bucket->total_ticks+=ticks;
    if (ticks>bucket->peak_page_ticks) bucket->peak_page_ticks=ticks;
    bucket->slow_pages+=was_slow;
    bucket->retried_pages+=retried;
    bucket->failed_pages+=failed;
    bucket->failed_in_band[wait_bin]+=failed;
    ++*bins[wait_bin];
    return 0;
}

/* Reuse the inclusive four-bin classification used by page telemetry.
 * Caller validates tick_frequency*frames before this calculation. */
static unsigned pcm_seam_wait_band(uint64_t waited, uint64_t nominal) {
    return waited<=nominal ? 0u :
           nominal>UINT64_MAX/2u || waited<=nominal*2u ? 1u :
           nominal>UINT64_MAX/4u || waited<=nominal*4u ? 2u : 3u;
}

int vh_audio_output_record_pcm_seam(
    VhAudioPcmSeams *stats, const int16_t *stereo, size_t frames,
    int first_after_switch, const VhAudioSubmitTiming *before,
    const VhAudioSubmitTiming *after, uint64_t tick_frequency) {
    if (!stats || !stereo || !before || !after || !frames ||
        frames>VH_AUDIO_RESAMPLE_MAX_FRAMES || !tick_frequency ||
        tick_frequency>UINT64_MAX/frames ||
        (first_after_switch!=0 && first_after_switch!=1) ||
        after->calls<=before->calls ||
        after->total_ticks<before->total_ticks ||
        after->failed_submissions<before->failed_submissions ||
        stats->delivered_pages==UINT64_MAX ||
        (stats->has_previous!=0 && stats->has_previous!=1) ||
        (stats->has_previous!=(stats->delivered_pages!=0)) ||
        (first_after_switch && !stats->has_previous))
        return -1;
    const uint64_t attempts=after->calls-before->calls;
    const uint64_t failures=
        after->failed_submissions-before->failed_submissions;
    if (attempts>VH_AUDIO_OUTPUT_RESTART_LIMIT+1u ||
        failures>=attempts || attempts-failures!=1u)
        return -1;
    const uint64_t nominal=(uint64_t)frames*tick_frequency/
                           VH_NATIVE_AUDOUT_RATE;
    const unsigned band=pcm_seam_wait_band(
        after->total_ticks-before->total_ticks,nominal);
    VhAudioPcmSeamBucket *bucket=first_after_switch
        ? &stats->first_after_switch : &stats->ordinary;
    uint32_t jump=0u;
    if (stats->has_previous) {
        if (bucket->count[band]==UINT64_MAX) return -1;
        int32_t dl=(int32_t)stereo[0]-(int32_t)stats->last_l;
        int32_t dr=(int32_t)stereo[1]-(int32_t)stats->last_r;
        if (dl<0) dl=-dl;
        if (dr<0) dr=-dr;
        jump=(uint32_t)(dl>dr ? dl : dr);
    }
    if (stats->has_previous) {
        ++bucket->count[band];
        if (jump>bucket->peak_abs_step[band])
            bucket->peak_abs_step[band]=jump;
    }
    stats->last_l=stereo[2u*(frames-1u)];
    stats->last_r=stereo[2u*(frames-1u)+1u];
    if (!stats->has_previous)
        stats->first_wait_band=band;
    stats->has_previous=1;
    stats->last_abs_step=jump;
    stats->last_wait_band=band;
    ++stats->delivered_pages;
    return 0;
}

static int bucket_distribution_valid(const VhAudioPageWaitBucket *b);

int vh_audio_output_verify_pcm_seams(
    const VhAudioPcmSeams *stats, const VhAudioSceneWaits *waits,
    uint64_t completed_pages) {
    if (!stats || !waits || stats->delivered_pages!=completed_pages ||
        stats->has_previous!=(completed_pages!=0) ||
        stats->last_wait_band>=VH_PCM_SEAM_BANDS ||
        stats->first_wait_band>=VH_PCM_SEAM_BANDS ||
        stats->last_abs_step>65535u ||
        (!completed_pages && (stats->first_wait_band!=0u ||
                              stats->last_wait_band!=0u))) return -1;
    const VhAudioPcmSeamBucket *const buckets[]={
        &stats->ordinary, &stats->first_after_switch
    };
    const VhAudioPageWaitBucket *const groups[]={
        &waits->ordinary, &waits->first_after_switch
    };
    const uint64_t failures[2][VH_PCM_SEAM_BANDS]={
        {waits->ordinary.failed_in_band[0],
         waits->ordinary.failed_in_band[1],
         waits->ordinary.failed_in_band[2],
         waits->ordinary.failed_in_band[3]},
        {waits->first_after_switch.failed_in_band[0],
         waits->first_after_switch.failed_in_band[1],
         waits->first_after_switch.failed_in_band[2],
         waits->first_after_switch.failed_in_band[3]}
    };
    const uint64_t page_counts[2][VH_PCM_SEAM_BANDS]={
        {waits->ordinary.wait_le_page,waits->ordinary.wait_le_2pages,
         waits->ordinary.wait_le_4pages,waits->ordinary.wait_gt_4pages},
        {waits->first_after_switch.wait_le_page,
         waits->first_after_switch.wait_le_2pages,
         waits->first_after_switch.wait_le_4pages,
         waits->first_after_switch.wait_gt_4pages}
    };
    uint64_t all=0;
    for (unsigned group=0;group<2u;group++) {
        const VhAudioPageWaitBucket *const pages=groups[group];
        if (!bucket_distribution_valid(pages) ||
            pages->failed_pages>pages->pages) return -1;
        uint64_t expected=pages->pages-pages->failed_pages;
        if (!group && completed_pages) {
            if (!expected) return -1;
            --expected; /* first returned PCM page has no prior tail */
        }
        uint64_t seen=0;
        for (unsigned bin=0;bin<VH_PCM_SEAM_BANDS;bin++) {
            const uint64_t count=buckets[group]->count[bin];
            const uint32_t peak=buckets[group]->peak_abs_step[bin];
            /* First subtract non-delivered pages from this exact
             * wait bin, then exclude the first successful page
             * only from the bin in which it was actually timed. */
            const uint64_t failed=failures[group][bin];
            if (failed>page_counts[group][bin]) return -1;
            uint64_t expected_bin=page_counts[group][bin]-failed;
            if (completed_pages && group==0u &&
                bin==stats->first_wait_band) {
                if (!expected_bin) return -1;
                --expected_bin;
            }
            if (count!=expected_bin ||
                (count==0u && peak!=0u) || peak>65535u ||
                seen>UINT64_MAX-count) return -1;
            seen+=count;
        }
        if (seen!=expected || all>UINT64_MAX-seen) return -1;
        all+=seen;
    }
    return all==(completed_pages ? completed_pages-1u : 0u)
           ? 0 : -1;
}

static int bucket_distribution_valid(const VhAudioPageWaitBucket *b) {
    if (b->wait_le_page>UINT64_MAX-b->wait_le_2pages) return 0;
    const uint64_t first=b->wait_le_page+b->wait_le_2pages;
    if (first>UINT64_MAX-b->wait_le_4pages) return 0;
    const uint64_t third=first+b->wait_le_4pages;
    if (third>UINT64_MAX-b->wait_gt_4pages) return 0;
    if (third+b->wait_gt_4pages!=b->pages) return 0;
    const uint64_t limits[VH_AUDIO_WAIT_BANDS]={
        b->wait_le_page,b->wait_le_2pages,
        b->wait_le_4pages,b->wait_gt_4pages
    };
    uint64_t failures=0;
    for (unsigned i=0;i<VH_AUDIO_WAIT_BANDS;i++) {
        const uint64_t count=b->failed_in_band[i];
        if (count>limits[i] || failures>UINT64_MAX-count) return 0;
        failures+=count;
    }
    return failures==b->failed_pages;
}

int vh_audio_output_verify_run(
    const VhAudioSceneWaits *groups,
    const VhAudioOutputRecovery *recovery,
    const VhAudioSubmitTiming *timing,
    uint64_t completed_pages, uint64_t completed_fixture_switches,
    uint64_t expected_pages, uint64_t fixture_switch_period_pages,
    int finished_without_error) {
    if (!groups || !recovery || !timing || !expected_pages ||
        completed_pages>expected_pages)
        return -1;
    const VhAudioPageWaitBucket *steady=&groups->ordinary;
    const VhAudioPageWaitBucket *boundary=&groups->first_after_switch;
    if (!bucket_distribution_valid(steady) ||
        !bucket_distribution_valid(boundary) ||
        steady->pages<steady->failed_pages ||
        boundary->pages<boundary->failed_pages ||
        steady->slow_pages>steady->pages ||
        boundary->slow_pages>boundary->pages ||
        steady->retried_pages>steady->pages ||
        boundary->retried_pages>boundary->pages ||
        steady->total_ticks<steady->peak_page_ticks ||
        boundary->total_ticks<boundary->peak_page_ticks ||
        steady->pages>UINT64_MAX-boundary->pages ||
        steady->total_ticks>UINT64_MAX-boundary->total_ticks ||
        steady->failed_pages>UINT64_MAX-boundary->failed_pages ||
        steady->retried_pages>UINT64_MAX-boundary->retried_pages)
        return -1;

    const uint64_t logical_pages=steady->pages+boundary->pages;
    const uint64_t failed_pages=
        steady->failed_pages+boundary->failed_pages;
    const uint64_t returned_pages=logical_pages-failed_pages;
    const uint64_t boundary_returned=
        boundary->pages-boundary->failed_pages;
    const uint64_t retry_pages=
        steady->retried_pages+boundary->retried_pages;
    const uint64_t expected_switches=
        !fixture_switch_period_pages || !completed_pages
        ? 0u : (completed_pages-1u)/fixture_switch_period_pages;
    if (returned_pages!=completed_pages ||
        boundary_returned!=completed_fixture_switches ||
        completed_fixture_switches!=expected_switches ||
        (!fixture_switch_period_pages && boundary->pages!=0u) ||
        recovery->pages_submitted!=completed_pages ||
        timing->synthetic_failed_submissions>timing->failed_submissions ||
        recovery->submit_failures!=timing->failed_submissions ||
        recovery->recoveries>retry_pages ||
        recovery->recoveries>completed_pages ||
        recovery->restart_attempts<recovery->recoveries ||
        recovery->restart_attempts>recovery->submit_failures ||
        /* Session restarts never return PCM pages. A recovery can
         * occur only after one counted session restart, separately
         * from a regular audout page-retry recovery. */
        recovery->resume_recoveries>recovery->resume_restarts ||
        retry_pages>timing->failed_submissions ||
        /* Every page retried then delivered increments recoveries
         * exactly once. A retried page not recovered must be a
         * terminally failed logical page. This prevents concealed
         * "missing recovery" counts even when raw calls balance. */
        retry_pages-recovery->recoveries>failed_pages ||
        /* Every raw audout call either failed or accepted exactly
         * one logical PCM page. A >= check could silently accept
         * extra unaccounted backend calls. Compare by subtraction
         * to avoid overflowing completed_pages+failed_submissions. */
        timing->calls<timing->failed_submissions ||
        timing->calls-timing->failed_submissions!=completed_pages ||
        timing->waits_longer_than_page>timing->calls ||
        timing->max_ticks>timing->total_ticks ||
        /* A raw service call cannot take more time than the whole
         * logical PCM page (which includes the raw call and retries).
         * Peak-page aggregates provide a strict upper bound. */
        (timing->max_ticks>steady->peak_page_ticks &&
         timing->max_ticks>boundary->peak_page_ticks) ||
        timing->total_ticks!=steady->total_ticks+boundary->total_ticks)
        return -1;
    return finished_without_error && completed_pages==expected_pages &&
           failed_pages==0u ? 1 : 0;
}

int vh_audio_output_page_returned(const void *submitted,
                                  const void *released) {
    return submitted != NULL && released == submitted;
}

int vh_audio_output_submit_recover(
    const VhAudioOutputOps *ops, VhAudioOutputRecovery *stats,
    const int16_t *stereo, size_t frames) {
    if (!ops || !stats || !stereo || !frames ||
        frames > VH_AUDIO_RESAMPLE_MAX_FRAMES ||
        !ops->submit || !ops->stop || !ops->close ||
        !ops->open || !ops->start ||
        stats->pages_submitted == UINT64_MAX ||
        stats->frames_submitted > UINT64_MAX - frames ||
        /* A submission can fail even when the backend eventually
         * returns the descriptor. Refuse ANY new call if a counter
         * needed to represent a retry is already saturated. */
        stats->submit_failures==UINT_MAX ||
        stats->restart_attempts==UINT_MAX ||
        stats->recoveries==UINT_MAX ||
        stats->recoveries>stats->restart_attempts ||
        stats->restart_attempts>stats->submit_failures)
        return -1;

    if (ops->submit(ops->context, stereo, frames) == 0) {
        ++stats->pages_submitted;
        stats->frames_submitted += frames;
        return 0;
    }
    ++stats->submit_failures;

    for (unsigned attempt = 0; attempt < VH_AUDIO_OUTPUT_RESTART_LIMIT;
         ++attempt) {
        /* A previous submit may have partially reached the device.
         * Reuse the caller's page ONLY after stopping and closing
         * that session; never advance any musical clocks here.
         */
        /* If the first failed attempt already saturated the error
         * counter, do not restart into a callback whose outcome
         * could not be counted. Earlier failures remain recorded. */
        if (stats->submit_failures==UINT_MAX ||
            stats->restart_attempts==UINT_MAX ||
            stats->recoveries==UINT_MAX)
            return -1;
        if (ops->stop(ops->context)) return -1;
        ops->close(ops->context);
        ++stats->restart_attempts;
        if (ops->open(ops->context) || ops->start(ops->context))
            return -1;
        if (ops->submit(ops->context, stereo, frames) == 0) {
            ++stats->recoveries;
            ++stats->pages_submitted;
            stats->frames_submitted += frames;
            return 0;
        }
        ++stats->submit_failures;
    }
    return -1;
}

int vh_audio_output_stop_close(const VhAudioOutputOps *ops) {
    if (!ops || !ops->stop || !ops->close) return -1;
    if (ops->stop(ops->context)) return -1;
    ops->close(ops->context);
    return 0;
}

int vh_audio_output_resume_recover(
    const VhAudioOutputOps *ops, VhAudioOutputRecovery *stats,
    int force_reopen) {
    if (!ops || !stats || !ops->stop || !ops->close ||
        !ops->open || !ops->start ||
        stats->resume_recoveries>stats->resume_restarts)
        return -1;

    /* On a saturated counter, refuse to begin a callback which
     * could require incrementing it afterwards. A rejected session
     * must never silently wrap an unsigned diagnostic counter. */
    if (!force_reopen) {
        if (stats->resume_failures==UINT_MAX) return -1;
        /* The focus-only fast path does not open a new session and
         * must preserve every submitted PCM/page/music counter. */
        if (!ops->start(ops->context)) return 0;
        ++stats->resume_failures;
    }

    /* HOME/sleep may invalidate audout handles. A stopped and
     * closed session may be reopened at most RESTART_LIMIT times.
     * Never touch music state or count a returned PCM page. */
    for (unsigned attempt=0;attempt<VH_AUDIO_OUTPUT_RESTART_LIMIT;
         ++attempt) {
        if (stats->resume_restarts==UINT_MAX ||
            stats->resume_failures==UINT_MAX ||
            stats->resume_recoveries==UINT_MAX)
            return -1;
        if (ops->stop(ops->context)) return -1;
        ops->close(ops->context);
        ++stats->resume_restarts;
        if (!ops->open(ops->context) &&
            !ops->start(ops->context)) {
            ++stats->resume_recoveries;
            return 0;
        }
        ++stats->resume_failures;
    }
    return -1;
}
