/* Portable main-thread/game-input -> music-scene mailbox regression.
 * Concurrency uses C11 atomics and no libnx/audio device dependency.
 */
#include <assert.h>
#include <stdatomic.h>
#include <stdio.h>
#include "vh_game_music_mailbox.h"
#include "platform_input.h"

static void test_input_events_are_music_events(void) {
    VhGameState state = {1,2,1,2,6,3,0};
    VhGameMusicMailbox box;
    vh_game_music_mailbox_init(&box, vh_game_music_for_state(&state));
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_FIELD);
    assert(vh_game_music_mailbox_running(&box));

    /* Ordinary cursor movement does not select a unit or change music. */
    assert(!vh_process_input(&state,VH_INPUT_RIGHT,8,6,2));
    assert(vh_game_music_for_state(&state)==VH_GAME_MUSIC_FIELD);
    state.cursor_x=state.hero_x;
    state.cursor_y=state.hero_y;
    assert(!vh_process_input(&state,VH_INPUT_CONFIRM,8,6,2));
    assert(vh_game_music_for_state(&state)==VH_GAME_MUSIC_HERO_SELECTED);
    vh_game_music_mailbox_post(&box, vh_game_music_for_state(&state));
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_HERO_SELECTED);

    /* Cursor movement while selected leaves the music stable. */
    assert(!vh_process_input(&state,VH_INPUT_RIGHT,8,6,2));
    assert(vh_game_music_for_state(&state)==VH_GAME_MUSIC_HERO_SELECTED);

    /* Successful destination confirms end of selection. */
    assert(!vh_process_input(&state,VH_INPUT_CONFIRM,8,6,2));
    assert(state.hero_selected==0 && state.hero_x==2);
    vh_game_music_mailbox_post(&box, vh_game_music_for_state(&state));
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_FIELD);

    /* Cancel also returns to field music. */
    state.hero_selected=1;
    assert(!vh_process_input(&state,VH_INPUT_CANCEL,8,6,2));
    vh_game_music_mailbox_post(&box,vh_game_music_for_state(&state));
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_FIELD);
    vh_game_music_mailbox_stop(&box);
    assert(!vh_game_music_mailbox_running(&box));
}
static void test_last_request_wins_without_waiting(void) {
    VhGameMusicMailbox box;
    vh_game_music_mailbox_init(&box, VH_GAME_MUSIC_FIELD);
    for(unsigned i=0;i<100000u;i++) {
        const unsigned requested=(i & 1u)
            ? VH_GAME_MUSIC_HERO_SELECTED : VH_GAME_MUSIC_FIELD;
        vh_game_music_mailbox_post(&box,requested);
        assert(vh_game_music_mailbox_read(&box)==requested);
    }
    vh_game_music_mailbox_post(&box,99u); /* impossible scene rejected */
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_HERO_SELECTED);
    vh_game_music_mailbox_post(&box,VH_GAME_MUSIC_SILENT);
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_SILENT);
    vh_game_music_mailbox_stop(&box);
    assert(!vh_game_music_mailbox_running(&box));
    assert(vh_game_music_for_state(NULL)==VH_GAME_MUSIC_SILENT);
    assert(vh_game_music_mailbox_read(NULL)==VH_GAME_MUSIC_SILENT);
}

int main(void) {
    test_input_events_are_music_events();
    test_last_request_wins_without_waiting();
    puts("tactical input to nonblocking music scene mailbox: PASS");
    return 0;
}
