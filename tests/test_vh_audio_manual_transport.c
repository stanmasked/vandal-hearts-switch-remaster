/* Host-only tests: NO real HOME, audout or controller input. */
#include <assert.h>
#include <stdio.h>
#include <stdatomic.h>
#include "vh_audio_manual_transport.h"

static void test_requires_real_returned_pcm(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_NONE));
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_QUICK);
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_NONE);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    vh_audio_manual_finished_service(&ctl,1);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_WAIT_PCM);
    assert(atomic_load(&ctl.quick_result)==1);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    /* Calling returned PCM is mandatory before success can be shown. */
    vh_audio_manual_returned_pcm(&ctl);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_CONFIRMED);
    assert(atomic_load(&ctl.quick_result)==2);
    assert(atomic_load(&ctl.reopen_result)==0);
}

static void test_new_manual_command_after_verified_pcm(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_QUICK);
    vh_audio_manual_finished_service(&ctl,1);
    vh_audio_manual_returned_pcm(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(atomic_load(&ctl.quick_result)==2);
    assert(atomic_load(&ctl.reopen_result)==1);
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_REOPEN);
    vh_audio_manual_finished_service(&ctl,1);
    assert(atomic_load(&ctl.reopen_result)==1);
    vh_audio_manual_returned_pcm(&ctl);
    assert(atomic_load(&ctl.reopen_result)==2);
    /* Repeated input after completion is permitted, but never replayed. */
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_QUICK);
    assert(atomic_load(&ctl.quick_result)==1);
}

static void test_failed_service_remains_failed(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_REOPEN);
    vh_audio_manual_finished_service(&ctl,0);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    assert(atomic_load(&ctl.reopen_result)==-1);
    vh_audio_manual_returned_pcm(&ctl);
    vh_audio_manual_finished_service(&ctl,1);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
}

static void test_spurious_pcm_without_command_is_not_evidence(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    vh_audio_manual_returned_pcm(&ctl);
    vh_audio_manual_finished_service(&ctl,1);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_IDLE);
    assert(atomic_load(&ctl.quick_result)==0);
    assert(atomic_load(&ctl.reopen_result)==0);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    vh_audio_manual_returned_pcm(&ctl);
    assert(atomic_load(&ctl.quick_result)==1);
}

int main(void) {
    test_requires_real_returned_pcm();
    test_new_manual_command_after_verified_pcm();
    test_failed_service_remains_failed();
    test_spurious_pcm_without_command_is_not_evidence();
    puts("manual X/Y audout mailbox: serialized commands and post-service PCM PASS (host fixtures)");
    return 0;
}
