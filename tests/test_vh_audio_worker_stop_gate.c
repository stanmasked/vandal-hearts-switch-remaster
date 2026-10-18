#include "vh_audio_worker_stop_gate.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static unsigned clock_calls;
static uint64_t synthetic_now=1000000;
static uint64_t counted_now(void) {
    clock_calls++;
    return synthetic_now;
}

static void test_audio_running_has_no_clock_or_witness_writes(void) {
    VhGameMusicMailbox mailbox={0};
    VhAudioExitWorkerStopWitness witness={0};
    vh_game_music_mailbox_init(&mailbox,VH_GAME_MUSIC_FIELD);
    vh_audio_exit_worker_stop_reset(&witness);
    clock_calls=0;
    for (unsigned n=0;n<100000u;n++) {
        assert(vh_audio_worker_stop_gate_continue(
                   &mailbox,&witness,counted_now)==1);
        assert(clock_calls==0u);
        assert(vh_audio_exit_worker_stop_read(&witness)==0);
    }
    /* Scene changes have no effect on running-flag stop gate. */
    vh_game_music_mailbox_post(&mailbox,VH_GAME_MUSIC_HERO_SELECTED);
    assert(vh_audio_worker_stop_gate_continue(
               &mailbox,&witness,counted_now)==1);
    assert(clock_calls==0u);
}
static void test_stop_marks_once_and_leaves_loop(void) {
    VhGameMusicMailbox box={0};
    VhAudioExitWorkerStopWitness w={0};
    vh_game_music_mailbox_init(&box,VH_GAME_MUSIC_FIELD);
    vh_audio_exit_worker_stop_reset(&w);
    clock_calls=0;
    assert(vh_audio_worker_stop_gate_continue(
               &box,&w,counted_now)==1);
    assert(clock_calls==0u);
    vh_game_music_mailbox_stop(&box);
    assert(vh_audio_worker_stop_gate_continue(
               &box,&w,counted_now)==0);
    assert(clock_calls==1u);
    assert(vh_audio_exit_worker_stop_read(&w)==1000000u);
    synthetic_now=1005000;
    assert(vh_audio_worker_stop_gate_continue(
               &box,&w,counted_now)==0);
    assert(clock_calls==1u);
    assert(vh_audio_exit_worker_stop_read(&w)==1000000u);
}
static void test_missing_clock_or_witness_still_stops(void) {
    VhGameMusicMailbox box={0};
    VhAudioExitWorkerStopWitness w={0};
    vh_game_music_mailbox_init(&box,VH_GAME_MUSIC_FIELD);
    vh_audio_exit_worker_stop_reset(&w);
    vh_game_music_mailbox_stop(&box);
    clock_calls=0;
    assert(vh_audio_worker_stop_gate_continue(&box,&w,NULL)==0);
    assert(vh_audio_exit_worker_stop_read(&w)==0);
    assert(clock_calls==0u);
    assert(vh_audio_worker_stop_gate_continue(&box,NULL,counted_now)==0);
    assert(clock_calls==0u);
    synthetic_now=0;
    assert(vh_audio_worker_stop_gate_continue(&box,&w,counted_now)==0);
    assert(clock_calls==1u);
    assert(vh_audio_exit_worker_stop_read(&w)==0);
}
static void test_null_mailbox_fails_closed(void) {
    VhAudioExitWorkerStopWitness w={0};
    vh_audio_exit_worker_stop_reset(&w);
    clock_calls=0;
    synthetic_now=333;
    assert(vh_audio_worker_stop_gate_continue(NULL,&w,counted_now)==0);
    /* A nonexistent mailbox is NOT an observed running->stopped
     * transition, so never manufacture a source timestamp. */
    assert(clock_calls==0u);
    assert(vh_audio_exit_worker_stop_read(&w)==0);
}
int main(void) {
    test_audio_running_has_no_clock_or_witness_writes();
    test_stop_marks_once_and_leaves_loop();
    test_missing_clock_or_witness_still_stops();
    test_null_mailbox_fails_closed();
    puts("Stage319 worker stop gate single read, zero running clock and fail-closed tests passed");
    return 0;
}
