#ifndef VH_GAME_MUSIC_MAILBOX_H
#define VH_GAME_MUSIC_MAILBOX_H

#include <stdatomic.h>
#include <stdint.h>
#include "game_state.h"

/* Portable, last-request-wins bridge from the tactical input/render
 * thread to a dedicated native audio producer. No audio-service calls,
 * allocations or waiting occur on the gameplay thread.
 * Only the audio owner calls vh_music_scene_request/render.
 */
enum {
    VH_GAME_MUSIC_SILENT = 0,
    VH_GAME_MUSIC_FIELD = 1,
    VH_GAME_MUSIC_HERO_SELECTED = 2
};

typedef struct {
    atomic_uint desired_scene;
    atomic_int running;
    atomic_int focused; /* 1=in focus; 0=suspended/background */
    atomic_uint resume_serial; /* explicit OnResume forces audout reopen */
} VhGameMusicMailbox;

void vh_game_music_mailbox_init(VhGameMusicMailbox *box, unsigned scene);
void vh_game_music_mailbox_post(VhGameMusicMailbox *box, unsigned scene);
unsigned vh_game_music_mailbox_read(const VhGameMusicMailbox *box);
/* Scene requests persist while paused: latest desired scene is applied
 * on the first audio block after resume, without changing SEQ time.
 */
void vh_game_music_mailbox_set_focus(VhGameMusicMailbox *box, int focused);
int vh_game_music_mailbox_focused(const VhGameMusicMailbox *box);
/* applet OnResume is not necessarily preceded by a processed focus-loss
 * notification when libnx automatically suspends all user threads.
 * Only an actual resume event increments this serial; repeated focus
 * sampling each gameplay frame must not restart audout.
 */
void vh_game_music_mailbox_on_resume(VhGameMusicMailbox *box, int focused);
unsigned vh_game_music_mailbox_resume_serial(
    const VhGameMusicMailbox *box);
void vh_game_music_mailbox_stop(VhGameMusicMailbox *box);
int vh_game_music_mailbox_running(const VhGameMusicMailbox *box);

/* These correspond to the two actual modes of the present tactical
 * prototype. Victory/menu/combat-entry events don't exist yet.
 */
unsigned vh_game_music_for_state(const VhGameState *state);

#endif
