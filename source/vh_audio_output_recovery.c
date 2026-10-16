#include "vh_audio_output_recovery.h"
#include "vh_audio_resample.h"

#include <limits.h>

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
