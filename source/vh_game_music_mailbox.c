#include "vh_game_music_mailbox.h"

void vh_game_music_mailbox_init(VhGameMusicMailbox *box, unsigned scene) {
    if (!box) return;
    atomic_init(&box->desired_scene, scene);
    atomic_init(&box->running, 1);
    atomic_init(&box->focused, 1);
    atomic_init(&box->resume_serial, 0u);
}

void vh_game_music_mailbox_post(VhGameMusicMailbox *box, unsigned scene) {
    if (box && scene <= VH_GAME_MUSIC_HERO_SELECTED)
        atomic_store_explicit(&box->desired_scene, scene, memory_order_release);
}

unsigned vh_game_music_mailbox_read(const VhGameMusicMailbox *box) {
    return box ? atomic_load_explicit(&box->desired_scene,
                                      memory_order_acquire)
               : VH_GAME_MUSIC_SILENT;
}

void vh_game_music_mailbox_set_focus(VhGameMusicMailbox *box,
                                    int focused) {
    if (box)
        atomic_store_explicit(&box->focused, focused ? 1 : 0,
                              memory_order_release);
}

int vh_game_music_mailbox_focused(const VhGameMusicMailbox *box) {
    return box ? atomic_load_explicit(&box->focused,
                                      memory_order_acquire) : 0;
}

void vh_game_music_mailbox_on_resume(VhGameMusicMailbox *box,
                                     int focused) {
    if (!box) return;
    vh_game_music_mailbox_set_focus(box, focused);
    atomic_fetch_add_explicit(&box->resume_serial, 1u,
                              memory_order_release);
}

unsigned vh_game_music_mailbox_resume_serial(
    const VhGameMusicMailbox *box) {
    return box ? atomic_load_explicit(&box->resume_serial,
                                      memory_order_acquire) : 0u;
}

void vh_game_music_mailbox_stop(VhGameMusicMailbox *box) {
    if (box) atomic_store_explicit(&box->running, 0, memory_order_release);
}

int vh_game_music_mailbox_running(const VhGameMusicMailbox *box) {
    return box ? atomic_load_explicit(&box->running, memory_order_acquire) : 0;
}

unsigned vh_game_music_for_state(const VhGameState *state) {
    if (!state) return VH_GAME_MUSIC_SILENT;
    return state->hero_selected ? VH_GAME_MUSIC_HERO_SELECTED
                                : VH_GAME_MUSIC_FIELD;
}
