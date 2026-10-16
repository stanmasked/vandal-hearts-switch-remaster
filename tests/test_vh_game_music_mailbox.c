/* Portable main-thread/game-input -> music-scene mailbox regression.
 * Concurrency uses C11 atomics and no libnx/audio device dependency.
 */
#include <assert.h>
#include <stdatomic.h>
#include <threads.h>
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
static void test_suspend_resume_preserves_latest_scene(void) {
    VhGameMusicMailbox box;
    vh_game_music_mailbox_init(&box,VH_GAME_MUSIC_FIELD);
    assert(vh_game_music_mailbox_focused(&box));
    assert(vh_game_music_mailbox_running(&box));
    vh_game_music_mailbox_set_focus(&box,0);
    assert(!vh_game_music_mailbox_focused(&box));
    /* Main input events continue to overwrite the desired cue, while
     * the audio producer should not render/advance sample clocks.
     */
    vh_game_music_mailbox_post(&box,VH_GAME_MUSIC_HERO_SELECTED);
    vh_game_music_mailbox_post(&box,VH_GAME_MUSIC_FIELD);
    vh_game_music_mailbox_post(&box,VH_GAME_MUSIC_HERO_SELECTED);
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_HERO_SELECTED);
    assert(!vh_game_music_mailbox_focused(&box));
    vh_game_music_mailbox_set_focus(&box,2);
    assert(vh_game_music_mailbox_focused(&box));
    assert(vh_game_music_mailbox_read(&box)==VH_GAME_MUSIC_HERO_SELECTED);
    vh_game_music_mailbox_set_focus(&box,-4);
    assert(vh_game_music_mailbox_focused(&box));
    vh_game_music_mailbox_set_focus(&box,0);
    vh_game_music_mailbox_stop(&box);
    assert(!vh_game_music_mailbox_running(&box));
    assert(!vh_game_music_mailbox_focused(&box));
    assert(!vh_game_music_mailbox_focused(NULL));
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

typedef struct {
    VhGameMusicMailbox *mailbox;
    atomic_int finished;
    atomic_uint observations;
} MusicStress;

static int stress_writer(void *arg) {
    MusicStress *test = arg;
    for (unsigned i=0;i<50000u;i++) {
        const unsigned scene = (i & 1u)
            ? VH_GAME_MUSIC_FIELD : VH_GAME_MUSIC_HERO_SELECTED;
        vh_game_music_mailbox_post(test->mailbox, scene);
    }
    vh_game_music_mailbox_set_focus(test->mailbox,0);
    vh_game_music_mailbox_post(
        test->mailbox, VH_GAME_MUSIC_HERO_SELECTED);
    vh_game_music_mailbox_set_focus(test->mailbox,1);
    atomic_store_explicit(&test->finished, 1, memory_order_release);
    return 0;
}

static int stress_reader(void *arg) {
    MusicStress *test = arg;
    do {
        const unsigned observed =
            vh_game_music_mailbox_read(test->mailbox);
        assert(observed==VH_GAME_MUSIC_FIELD ||
               observed==VH_GAME_MUSIC_HERO_SELECTED);
        const int focused=vh_game_music_mailbox_focused(test->mailbox);
        assert(focused==0 || focused==1);
        atomic_fetch_add_explicit(&test->observations,1,
                                  memory_order_relaxed);
    } while (!atomic_load_explicit(&test->finished,
                                  memory_order_acquire));
    assert(vh_game_music_mailbox_read(test->mailbox) ==
           VH_GAME_MUSIC_HERO_SELECTED);
    assert(vh_game_music_mailbox_focused(test->mailbox));
    return 0;
}

static void test_concurrent_last_request_wins(void) {
    VhGameMusicMailbox box;
    vh_game_music_mailbox_init(&box, VH_GAME_MUSIC_FIELD);
    MusicStress stress = { .mailbox=&box };
    atomic_init(&stress.finished,0);
    atomic_init(&stress.observations,0);
    thrd_t writer,reader;
    assert(thrd_create(&reader,stress_reader,&stress)==thrd_success);
    assert(thrd_create(&writer,stress_writer,&stress)==thrd_success);
    int status=-1;
    assert(thrd_join(writer,&status)==thrd_success && status==0);
    assert(thrd_join(reader,&status)==thrd_success && status==0);
    assert(atomic_load_explicit(&stress.observations,
                                memory_order_relaxed)>0);
    vh_game_music_mailbox_stop(&box);
    assert(!vh_game_music_mailbox_running(&box));
}

int main(void) {
    test_input_events_are_music_events();
    test_last_request_wins_without_waiting();
    test_suspend_resume_preserves_latest_scene();
    test_concurrent_last_request_wins();
    puts("tactical input to nonblocking music scene mailbox: PASS");
    return 0;
}
