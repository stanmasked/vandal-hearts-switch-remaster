#include "vh_audio_output_recovery.h"
#include "vh_audio_resample.h"

#include <limits.h>

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
        stats->frames_submitted > UINT64_MAX - frames)
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

int vh_audio_output_resume_recover(
    const VhAudioOutputOps *ops, VhAudioOutputRecovery *stats,
    int force_reopen) {
    if (!ops || !stats || !ops->stop || !ops->close ||
        !ops->open || !ops->start) return -1;

    /* Fast focus-only resume: preserve the already initialized
     * session if audout can start it again without a fresh open. */
    if (!force_reopen) {
        if (!ops->start(ops->context)) return 0;
        ++stats->resume_failures;
    }

    /* HOME/sleep may invalidate audout handles despite a successful
     * stop. Force the old service to close before opening a fresh one
     * after any explicit resume serial; never touch the music state.
     */
    for (unsigned attempt=0;attempt<VH_AUDIO_OUTPUT_RESTART_LIMIT;
         ++attempt) {
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
