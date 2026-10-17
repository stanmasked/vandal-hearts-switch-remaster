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

/* Keep audout transport separate from optional elapsed-time telemetry.
 * Once the EXACT descriptor has returned, a failed timing accumulator
 * must NEVER masquerade as a failed backend submit: a recovery attempt
 * could replay a page already accepted by the device.
 *
 * On a failed measurement, timing_fault becomes a sticky flag. Count
 * only the exact returned descriptors that lack valid timing data;
 * saturate the count to avoid wrap. This is a count of confirmed
 * descriptor returns, NOT proof of audible PCM or dropped audio.
 *
 * The return value reflects ONLY transport (0 delivered, -1 not
 * delivered). An invalid timing result must make final telemetry
 * evidence INVALID, but must not force transport restart/replay.
 */
typedef struct {
    unsigned timing_fault;
    uint64_t delivered_without_timing;
} VhAudioTransportTimingHealth;

int vh_audio_output_transport_outcome(
    int descriptor_returned, int timing_result,
    VhAudioTransportTimingHealth *health);

/* Optional one-shot user-requested timing fault injection. This does
 * not touch PCM, audout, or the genuine transport result. A ZL request
 * arms a single synthetic zero-frequency timing observation for the
 * NEXT exact returned descriptor. Real backend failures leave it armed.
 * On a valid descriptor the injector consumes its request once; the
 * producer must end with INVALID timing evidence (never replay PCM).
 * A NULL pointer or repeat arm fails closed; no accidental injects.
 */
typedef struct {
    unsigned armed, injected;
} VhAudioTimingFaultInjection;

int vh_audio_timing_fault_arm(VhAudioTimingFaultInjection *state);
uint64_t vh_audio_timing_fault_frequency(
    VhAudioTimingFaultInjection *state, int exact_returned,
    uint64_t actual_frequency);

/* Final integrity check: the number of untimed returned PCM pages
 * cannot exceed the number of successful logical output pages.
 * A nonzero count without the sticky fault flag is contradictory.
 * Return 0 for clean timing, 1 for rejected timing, -1 for impossible
 * bookkeeping. Neither a 0 nor a 1 proves actual audible playback.
 */
int vh_audio_output_verify_transport_health(
    const VhAudioTransportTimingHealth *health,
    const VhAudioOutputRecovery *recovery);

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
/* One common classification for audout waits and PCM seams. */
#define VH_AUDIO_WAIT_BANDS 4u
typedef struct {
    uint64_t pages, total_ticks, peak_page_ticks;
    uint64_t slow_pages, retried_pages, failed_pages;
    /* Mutually exclusive, normalized to each page's actual 48-kHz
     * duration. Sum of bins must equal pages, including failed pages.
     * Retried pages classify the sum of their raw service waits;
     * stop/reopen overhead is intentionally excluded.
     */
    uint64_t wait_le_page, wait_le_2pages;
    uint64_t wait_le_4pages, wait_gt_4pages;
    /* Failed pages are included in the four wait histogram bins
     * but have no returned PCM and therefore no inter-page seam.
     * Track their exact bins so the seam audit can subtract them.
     */
    uint64_t failed_in_band[VH_AUDIO_WAIT_BANDS];
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

/* Aggregate the inter-page PCM16 stereo step, grouped by the same
 * 48-kHz audout wait bands and synthetic scene-boundary classification.
 * A PCM seam is NOT proof of an audible click or service underrun.
 * The last L/R samples are held in memory only, never exported.
 */
#define VH_PCM_SEAM_BANDS VH_AUDIO_WAIT_BANDS
typedef struct {
    uint64_t count[VH_PCM_SEAM_BANDS];
    uint32_t peak_abs_step[VH_PCM_SEAM_BANDS];
} VhAudioPcmSeamBucket;
typedef struct {
    VhAudioPcmSeamBucket ordinary, first_after_switch;
    uint64_t delivered_pages;
    int16_t last_l, last_r;
    int has_previous;
    /* Last successfully returned page; no PCM sample material here. */
    uint32_t last_abs_step;
    unsigned last_wait_band;
    /* First delivered PCM page has no predecessor; remember its
     * actual wait bin rather than always assuming the <=1x band.
     */
    unsigned first_wait_band;
} VhAudioPcmSeams;

/* Only call after the exact PCM descriptor was returned. The first
 * successful page has no predecessor. All input errors are atomic.
 * Pass exactly the same raw timing snapshots as record_scene_page.
 */
int vh_audio_output_record_pcm_seam(
    VhAudioPcmSeams *stats, const int16_t *stereo, size_t frames,
    int first_after_switch, const VhAudioSubmitTiming *before,
    const VhAudioSubmitTiming *after, uint64_t tick_frequency);

/* Returns 0 only if EVERY per-category wait bin has exactly the
 * delivered-page count minus failed pages in that same wait bin,
 * minus the single first page in its actual wait bin. This prevents
 * compensating count corruption that totals-only checks can miss.
 */
int vh_audio_output_verify_pcm_seams(
    const VhAudioPcmSeams *stats, const VhAudioSceneWaits *waits,
    uint64_t completed_pages);

/* Reconcile the final on-device evidence with actual returned pages.
 *  1: full run reached expected_pages with all counters consistent
 *  0: internally consistent, but interrupted/failed/incomplete run
 * -1: contradictory or overflowing counters (never claim proof)
 * Every timed backend invocation must be accounted for by EXACTLY one
 * returned PCM page or one failed submission, including recovered
 * retries and the final undelivered page. Peak/tick invariants also
 * reject impossible backend latency metadata. Never infer audible
 * quality from this integrity status.
 * Only accepted first-after-switch pages count as completed switches.
 * Pass fixture_switch_period_pages=0 for user-owned SD music, which
 * must never be automatically switched. Other values set the precise
 * frequency for generated-fixture scenes.
 */
int vh_audio_output_verify_run(
    const VhAudioSceneWaits *groups,
    const VhAudioOutputRecovery *recovery,
    const VhAudioSubmitTiming *timing,
    uint64_t completed_pages, uint64_t completed_fixture_switches,
    uint64_t expected_pages, uint64_t fixture_switch_period_pages,
    int finished_without_error);

/* An audout descriptor may be backed by a reusable, caller-owned PCM page.
 * Even a failed submit can leave that memory in use until the backend
 * releases the EXACT descriptor or a successful stop drains the service.
 * All calls belong on the same serialized producer thread; these functions
 * are NOT locks. Zero-initialize before the first submission.
 *
 * While in_flight is non-NULL, do not rerender/overwrite its PCM storage,
 * switch away from borrowed source banks, or close the output service.
 */
typedef struct {
    const void *in_flight;
} VhAudioPageLease;

/* Reserve a descriptor before calling audoutPlayBuffer; reject a second
 * submission while the first page might still be held by the service.
 * Failure does not change state. */
int vh_audio_page_lease_begin(VhAudioPageLease *lease,
                              const void *descriptor);
/* Only the identical descriptor returned by the service unlocks its page.
 * A NULL or foreign pointer must leave the lease outstanding. */
int vh_audio_page_lease_return(VhAudioPageLease *lease,
                               const void *returned_descriptor);
/* Clear a possibly outstanding descriptor only when the actual backend
 * stop callback returned 0. Pass that same result unchanged; a failed
 * stop may still own the PCM and must leave the lease untouched. */
int vh_audio_page_lease_stopped(VhAudioPageLease *lease, int stop_result);
/* True if it is safe to reuse PCM backing and change music scene. */
int vh_audio_page_lease_ready(const VhAudioPageLease *lease);

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
 * a failed restart. The caller's page and music clock never advance
 * on retry. Submit/restart/recovery counters are overflow-checked
 * before a backend call could cause an uncounted raw attempt.
 * The device must drain/discard queued buffers before the caller
 * may reuse or free the backing PCM memory.
 */
int vh_audio_output_submit_recover(
    const VhAudioOutputOps *ops, VhAudioOutputRecovery *stats,
    const int16_t *stereo, size_t frames);

/* Start a paused output session without rendering any new PCM.
 * force_reopen is true after a HOME/sleep resume serial changes:
 * stop/close any stale audout service, then open/start fresh.
 * Otherwise first try start() on the existing stopped session and
 * recreate it if the start fails. At most RESTART_LIMIT fresh
 * sessions are attempted. Resume counters reject unsigned overflow
 * before any callback that might require a new count; recovery counts
 * may never exceed restart attempts. Return -1 after an exhausted/
 * unsafe stop; never change SEQ/SPU/PCM clocks, already-submitted
 * page/frames accounting, or caller-owned music banks.
 */
int vh_audio_output_resume_recover(
    const VhAudioOutputOps *ops, VhAudioOutputRecovery *stats,
    int force_reopen);

/* Final teardown for synchronous audout and any outstanding PCM page.
 * Never close a backend whose stop callback failed: its last
 * AudioOutBuffer may still be owned by the service. The caller must
 * keep that backing PCM page alive until process teardown or another
 * confirmed stop. A clean stop always closes exactly once.
 *
 * No raw PCM submission, music advance, resume attempt or diagnostic
 * counter mutation occurs here. Return 0 if stopped AND closed,
 * -1 on invalid ops or failed stop, leaving close UNCALLED.
 */
int vh_audio_output_stop_close(const VhAudioOutputOps *ops);

#endif
