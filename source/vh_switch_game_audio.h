#ifndef VH_SWITCH_GAME_AUDIO_H
#define VH_SWITCH_GAME_AUDIO_H

#include "vh_game_music_mailbox.h"
#include "vh_audio_scene_trace_export.h"
#include "vh_audout_queue_export.h"
#include "software_renderer.h"
#include "vh_audio_diagnostics.h"
#include <stdint.h>
#include <stdio.h>

/* Main tactical NRO uses this separate libnx audout worker. The
 * framebuffer/input loop never blocks on audoutPlayBuffer.
 * Audio fixtures are synthesized in memory; no copyrighted assets.
 */
int vh_switch_game_audio_start(unsigned initial_scene);
void vh_switch_game_audio_post(unsigned desired_scene);
/* Timestamp is the moment the game loop OBSERVED the A/B press,
 * in the armGetSystemTick-derived monotonic ns domain. Not the HID
 * sampling instant or DAC playback time. Records only on scene change.
 */
void vh_switch_game_audio_post_at(unsigned desired_scene,
                                  uint64_t game_input_observed_ns);
/* Print a bounded witness only after vh_switch_game_audio_stop()
 * has joined the producer thread. No filesystem I/O in audout paths.
 * CSV serial=0 means startup or unstable concurrent mailbox receipt. */
int vh_switch_game_audio_trace_dump(FILE *stream);
/* Guest-internal per-page audout measurements, separate from scene
 * events; only callable after joining. No measured speaker underruns. */
int vh_switch_game_audio_queue_dump(FILE *stream);
VhAudoutQueueExportResult vh_switch_game_audio_queue_export(
    char *committed_path,size_t capacity);
/* Separate per-call latency band CSV, only after worker join. */
VhAudoutQueueExportResult vh_switch_game_audio_slow_export(
    char *committed_path,size_t capacity);
VhAudoutQueueExportResult vh_switch_game_audio_clock_export(
    char *committed_path,size_t capacity);
VhAudoutQueueExportResult vh_switch_game_audio_probe_export(
    char *committed_path,size_t capacity);
VhAudoutQueueExportResult vh_switch_game_audio_latency_export(
    char *committed_path,size_t capacity);
/* Export numbered, readback-verified SD CSV ONLY after the audio
 * thread is joined. Return precise storage status to the main thread.
 * The output path is empty on error. Does not change audio clocks. */
VhSceneExportResult vh_switch_game_audio_trace_export(
    char *committed_path, size_t capacity);
/* Experimental diagnostic-only framebuffer receipt. Must only be
 * called after vh_switch_game_audio_stop() has joined the producer.
 * No guest file system or stdout transport is required. */
int vh_switch_game_audio_trace_render(VhCanvas *canvas,
    uint32_t black,uint32_t white,uint32_t marker);
/* Forward libnx AppletHookType_OnFocusState/OnResume transitions
 * from the main thread. Does not wait for the audio worker.
 */
void vh_switch_game_audio_set_focus(int in_focus);
/* Explicit libnx OnResume: restart audout even if an automatic system
 * suspension prevented the worker from observing focus loss first.
 */
void vh_switch_game_audio_on_resume(int in_focus);
/* Stage307: guest-exact software clock when the input loop first OBSERVES Plus.
 * This is NOT the keyboard/HID sampling instant. Nonblocking, no I/O. */
void vh_switch_game_audio_exit_note_plus(void);
/* Emit immutable guest shutdown event times only after worker join.
 * Returns 5 rows, or negative if unavailable / still running. */
int vh_switch_game_audio_exit_dump(FILE *stream);
/* Stage313: after join only, separate bounded software buffer-release witness.
 * Does not assert DAC/speaker playback or change Stage307 original CSV. */
int vh_switch_game_audio_exit_output_dump(FILE *stream);
/* Stage317: one-shot worker observation of stop flag, post-join only.
 * Does not rewrite Stage307/313 original CSV evidence. */
int vh_switch_game_audio_worker_stop_dump(FILE *stream);
/* Stage320: original last audoutPlayBuffer service begin/end, post-join only. */
int vh_switch_game_audio_last_playbuffer_dump(FILE *stream);
void vh_switch_game_audio_stop(void);
/* 0 starting/stopped, 1 playing, 2 paused, negative means audio failed.
 * Main gameplay can continue silently if the device is unavailable.
 */
int vh_switch_game_audio_status(void);
/* Number of first-pass notes played with a VH fallback or not
 * resolved at preload. Read atomically on the game thread; nonzero
 * means potential timbre mismatch, not an audio-device failure.
 */
unsigned vh_switch_game_audio_bank_warnings(void);
/* Observational diagnostics; zero until a resumed session has
 * completed its first PCM page. Measured from the audout start
 * attempt to confirmation of the first returned AudioOutBuffer;
 * NOT equivalent to actual audible-onset latency at the speaker.
 * Safe to query from the gameplay thread without blocking.
 */
unsigned vh_switch_game_audio_resume_latency_samples(void);
uint64_t vh_switch_game_audio_resume_worst_confirmed_us(void);
/* Inexpensive, read-only diagnostic snapshot for the optional on-screen
 * hardware testing overlay. Does not acquire locks or call audout.
 * Individual counters can span adjacent audio-owner turns.
 */
void vh_switch_game_audio_diagnostics(VhAudioDiagnostics *out);

#endif
