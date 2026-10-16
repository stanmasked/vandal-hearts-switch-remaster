#ifndef VH_SWITCH_GAME_AUDIO_H
#define VH_SWITCH_GAME_AUDIO_H

#include "vh_game_music_mailbox.h"
#include "vh_audio_diagnostics.h"
#include <stdint.h>

/* Main tactical NRO uses this separate libnx audout worker. The
 * framebuffer/input loop never blocks on audoutPlayBuffer.
 * Audio fixtures are synthesized in memory; no copyrighted assets.
 */
int vh_switch_game_audio_start(unsigned initial_scene);
void vh_switch_game_audio_post(unsigned desired_scene);
/* Forward libnx AppletHookType_OnFocusState/OnResume transitions
 * from the main thread. Does not wait for the audio worker.
 */
void vh_switch_game_audio_set_focus(int in_focus);
/* Explicit libnx OnResume: restart audout even if an automatic system
 * suspension prevented the worker from observing focus loss first.
 */
void vh_switch_game_audio_on_resume(int in_focus);
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
