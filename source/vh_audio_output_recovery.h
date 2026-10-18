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
