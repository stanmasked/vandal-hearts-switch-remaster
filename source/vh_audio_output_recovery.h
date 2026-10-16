#ifndef VH_AUDIO_OUTPUT_RECOVERY_H
#define VH_AUDIO_OUTPUT_RECOVERY_H

#include <stddef.h>
#include <stdint.h>

/* Portable, bounded recovery of a failed *output submission*.
 * The caller must serialize all operations with the audio producer.
 * PCM has already been synthesized: never re-run SEQ/SPU/resampler
 * when resending this page, or music time will skip ahead.
 */
#define VH_AUDIO_OUTPUT_RESTART_LIMIT 2u

typedef struct {
    void *context;
    int (*submit)(void *context, const int16_t *stereo, size_t frames);
    int (*stop)(void *context); /* 0 if output safely stopped */
    void (*close)(void *context);
    int (*open)(void *context); /* 0 if output format is correct */
    int (*start)(void *context);
} VhAudioOutputOps;

typedef struct {
    uint64_t pages_submitted;
    uint64_t frames_submitted;
    unsigned submit_failures, restart_attempts, recoveries;
    unsigned resume_failures, resume_restarts, resume_recoveries;
} VhAudioOutputRecovery;

/* Raw backend submission wait, measured on the owning audio thread.
 * Calls include retries: a blocking audoutPlayBuffer may legitimately
 * wait for its page duration. Slow calls are diagnostics, not dropouts.
 * No clock, SEQ, SPU, or PCM state is touched by this accumulator.
 */
typedef struct {
    uint64_t calls, total_ticks, max_ticks;
    uint64_t waits_longer_than_page, failed_submissions;
} VhAudioSubmitTiming;

/* Reject invalid frame sizes, a zero frequency and counter overflow
 * without mutating stats. A successful record counts exactly one
 * backend invocation (including rejected/wrong-descriptor returns).
 */
int vh_audio_output_record_submit_timing(
    VhAudioSubmitTiming *timing, uint64_t elapsed_ticks,
    uint64_t tick_frequency, size_t frames, int accepted);

/* Saturating conversion for readable logs, never used for scheduling.
 * Returns UINT64_MAX on arithmetic overflow, 0 for invalid frequency.
 */
uint64_t vh_audio_output_ticks_to_us(uint64_t ticks,
                                     uint64_t tick_frequency);

/* Compare audout waiting on the first PCM page after a scene switch
 * with the ordinary PCM pages. Only successful pages are needed to
 * compare running delays; terminal failures have a separate count.
 * "slow_pages" counts pages containing at least one *raw* service
 * call longer than that page's 48-kHz duration. Retry time is included
 * in total_ticks but reopening time is not. This is observation only.
 */
typedef struct {
    uint64_t pages, total_ticks, peak_page_ticks;
    uint64_t slow_pages, retried_pages, failed_pages;
} VhAudioPageWaitBucket;
typedef struct {
    VhAudioPageWaitBucket ordinary, first_after_switch;
} VhAudioSceneWaits;

/* Record one logical PCM page AFTER submit_recover, using the raw
 * timing accumulator copied before and read after that call.
 * A snapshot must contain 1..RESTART_LIMIT+1 new service calls.
 * Rejected counters or inconsistent snapshots leave *groups unchanged.
 */
int vh_audio_output_record_scene_page(
    VhAudioSceneWaits *groups,
    const VhAudioSubmitTiming *before, const VhAudioSubmitTiming *after,
    uint64_t tick_frequency, size_t frames, int first_after_switch,
    int delivered);

/* A single reusable audout PCM page is safe to overwrite only when
 * libnx reports that the identical AudioOutBuffer descriptor was released.
 * Call after a successful audoutPlayBuffer; another pointer (or NULL)
 * is a backend submission failure, not permission to reuse the page.
 * Pure pointer identity: callers need not dereference foreign pointers.
 */
int vh_audio_output_page_returned(const void *submitted,
                                  const void *released);

/* Return 0 after ONE successful device submission, -1 on terminal
 * failure. Once submit fails, stop/close/reinitialize and re-send
 * the exact same PCM page at most RESTART_LIMIT times.
 *
 * Device callbacks must return 0 on success, and maintain their
 * backend open/playing flags so the caller can always clean up after
 * a failed restart. The device must drain/discard queued buffers
 * before the caller may reuse or free the backing PCM memory.
 */
int vh_audio_output_submit_recover(
    const VhAudioOutputOps *ops, VhAudioOutputRecovery *stats,
    const int16_t *stereo, size_t frames);

/* Start a paused output session without rendering any new PCM.
 * force_reopen is true after a HOME/sleep resume serial changes:
 * stop/close any stale audout service, then open/start fresh.
 * Otherwise first try start() on the existing stopped session and
 * recreate it if the start fails. At most RESTART_LIMIT fresh
 * sessions are attempted. Return -1 after an exhausted/unsafe
 * stop; never change SEQ/SPU/PCM clocks or caller-owned music banks.
 */
int vh_audio_output_resume_recover(
    const VhAudioOutputOps *ops, VhAudioOutputRecovery *stats,
    int force_reopen);

#endif
