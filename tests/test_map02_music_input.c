/* Asset-free executable contract between the MAP02 input loop and music. */
#include <assert.h>
#include <stdio.h>
#include "platform_input.h"
#include "vh_game_music_mailbox.h"

static unsigned apply(VhGameState *state, VhGameMusicMailbox *box,
                      unsigned action, unsigned *posts) {
    const unsigned before = vh_game_music_for_state(state);
    const int exited = vh_process_input(state, action, 8, 6, 2);
    if (exited) return before;
    const unsigned after = vh_game_music_for_state(state);
    if (after != before) {
        vh_game_music_mailbox_post(box, after);
        ++*posts;
    }
    return after;
}

int main(void) {
    VhGameState state = {1,2,1,2,6,3,0};
    VhGameMusicMailbox box;
    unsigned posts = 0;
    assert(vh_game_music_for_state(&state) == VH_GAME_MUSIC_FIELD);
    vh_game_music_mailbox_init(&box, vh_game_music_for_state(&state));
    assert(vh_game_music_mailbox_read(&box) == VH_GAME_MUSIC_FIELD);

    /* Cursor motion does not restart field music. */
    assert(apply(&state, &box, VH_INPUT_RIGHT, &posts) == VH_GAME_MUSIC_FIELD);
    assert(apply(&state, &box, VH_INPUT_LEFT, &posts) == VH_GAME_MUSIC_FIELD);
    assert(posts == 0);

    /* A selects the hero; B cancels. */
    assert(apply(&state, &box, VH_INPUT_CONFIRM, &posts) ==
           VH_GAME_MUSIC_HERO_SELECTED);
    assert(posts == 1);
    assert(vh_game_music_mailbox_read(&box) == VH_GAME_MUSIC_HERO_SELECTED);
    assert(apply(&state, &box, VH_INPUT_CANCEL, &posts) == VH_GAME_MUSIC_FIELD);
    assert(posts == 2);

    /* A then Right and A moves the hero, returning to field music. */
    assert(apply(&state, &box, VH_INPUT_CONFIRM, &posts) ==
           VH_GAME_MUSIC_HERO_SELECTED);
    assert(posts == 3);
    assert(apply(&state, &box, VH_INPUT_RIGHT, &posts) ==
           VH_GAME_MUSIC_HERO_SELECTED);
    assert(posts == 3);
    assert(apply(&state, &box, VH_INPUT_CONFIRM, &posts) == VH_GAME_MUSIC_FIELD);
    assert(state.hero_x == 2 && state.hero_y == 2 && !state.hero_selected);
    assert(posts == 4);
    assert(vh_game_music_mailbox_read(&box) == VH_GAME_MUSIC_FIELD);

    /* The main game exit path does not post a new music cue. */
    assert(vh_process_input(&state, VH_INPUT_QUIT, 8, 6, 2) == 1);
    assert(vh_game_music_for_state(&state) == VH_GAME_MUSIC_FIELD);
    assert(posts == 4);
    vh_game_music_mailbox_stop(&box);
    assert(!vh_game_music_mailbox_running(&box));
    puts("PASS: MAP02 A/B/cursor/movement -> music scenes (four posts)");
    return 0;
}
