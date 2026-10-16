#ifndef VH_SWITCH_GAME_AUDIO_H
#define VH_SWITCH_GAME_AUDIO_H

#include "vh_game_music_mailbox.h"

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
void vh_switch_game_audio_stop(void);
/* 0 starting/stopped, 1 playing, 2 paused, negative means audio failed.
 * Main gameplay can continue silently if the device is unavailable.
 */
int vh_switch_game_audio_status(void);

#endif
