/* Host-only tests: NO real HOME, audout or controller input. */
#include <assert.h>
#include <limits.h>
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
    vh_audio_manual_finished_service(&ctl,1,16u);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_WAIT_PCM);
    assert(atomic_load(&ctl.quick_result)==1);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    /* Stale, repeated or earlier PCM counts are never confirmation. */
    vh_audio_manual_returned_pcm(&ctl,16u);
    vh_audio_manual_returned_pcm(&ctl,15u);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_WAIT_PCM);
    assert(atomic_load(&ctl.quick_result)==1);
    /* One genuinely newer returned logical PCM page confirms X. */
    vh_audio_manual_returned_pcm(&ctl,17u);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_CONFIRMED);
    assert(atomic_load(&ctl.quick_result)==2);
    assert(atomic_load(&ctl.reopen_result)==0);
}

static void test_new_manual_command_after_verified_pcm(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_QUICK);
    vh_audio_manual_finished_service(&ctl,1,42u);
    vh_audio_manual_returned_pcm(&ctl,43u);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(atomic_load(&ctl.quick_result)==2);
    assert(atomic_load(&ctl.reopen_result)==1);
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_REOPEN);
    vh_audio_manual_finished_service(&ctl,1,43u);
    assert(atomic_load(&ctl.reopen_result)==1);
    vh_audio_manual_returned_pcm(&ctl,43u);
    assert(atomic_load(&ctl.reopen_result)==1);
    vh_audio_manual_returned_pcm(&ctl,44u);
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
    vh_audio_manual_finished_service(&ctl,0,88u);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    assert(atomic_load(&ctl.reopen_result)==-1);
    vh_audio_manual_returned_pcm(&ctl,89u);
    vh_audio_manual_finished_service(&ctl,1,89u);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
}

static void test_spurious_pcm_without_command_is_not_evidence(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    vh_audio_manual_returned_pcm(&ctl,111u);
    vh_audio_manual_finished_service(&ctl,1,111u);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_IDLE);
    assert(atomic_load(&ctl.quick_result)==0);
    assert(atomic_load(&ctl.reopen_result)==0);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    vh_audio_manual_returned_pcm(&ctl,112u);
    assert(atomic_load(&ctl.quick_result)==1);
}

static void test_pcm_count_wrap_never_confirms(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_QUICK);
    vh_audio_manual_finished_service(&ctl,1,UINT_MAX);
    /* Underlying unsigned counter wrapped: this is NOT proof. */
    vh_audio_manual_returned_pcm(&ctl,0u);
    vh_audio_manual_returned_pcm(&ctl,1u);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_WAIT_PCM);
    assert(atomic_load(&ctl.quick_result)==1);
}

static void test_post_service_evidence_is_not_carried_across_retries(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_REOPEN);
    vh_audio_manual_finished_service(&ctl,1,214u);
    vh_audio_manual_returned_pcm(&ctl,215u);
    assert(atomic_load(&ctl.reopen_result)==2);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_REOPEN);
    assert(atomic_load(&ctl.reopen_result)==1);
    vh_audio_manual_returned_pcm(&ctl,216u);
    assert(atomic_load(&ctl.reopen_result)==1);
    vh_audio_manual_finished_service(&ctl,1,216u);
    vh_audio_manual_returned_pcm(&ctl,216u);
    assert(atomic_load(&ctl.reopen_result)==1);
    vh_audio_manual_returned_pcm(&ctl,217u);
    assert(atomic_load(&ctl.reopen_result)==2);
}

static void test_worker_exit_marks_pending_and_queued_as_failure(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    vh_audio_manual_abort_pending(&ctl);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    assert(atomic_load(&ctl.reopen_result)==-1);
    vh_audio_manual_returned_pcm(&ctl,999u);
    assert(atomic_load(&ctl.reopen_result)==-1);

    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_QUICK);
    vh_audio_manual_finished_service(&ctl,1,50u);
    assert(atomic_load(&ctl.quick_result)==1);
    vh_audio_manual_abort_pending(&ctl);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    assert(atomic_load(&ctl.quick_result)==-1);
    vh_audio_manual_returned_pcm(&ctl,51u);
    assert(atomic_load(&ctl.quick_result)==-1);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
}

static void test_worker_exit_preserves_confirmed_and_idle(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    vh_audio_manual_abort_pending(&ctl);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_STOPPED);
    assert(atomic_load(&ctl.quick_result)==0);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    /* A separate, newly started worker gets a new controller. */
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_QUICK);
    vh_audio_manual_finished_service(&ctl,1,17u);
    vh_audio_manual_returned_pcm(&ctl,18u);
    vh_audio_manual_abort_pending(&ctl);
    assert(atomic_load(&ctl.quick_result)==2);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_STOPPED);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
}

static void test_interrupted_claim_cannot_resurrect_queue(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    /* A main-thread claim may be in progress when worker teardown
     * begins. Shutdown must take precedence over final QUEUED store. */
    atomic_store(&ctl.phase,VH_MANUAL_CLAIMING);
    vh_audio_manual_abort_pending(&ctl);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    int expected=VH_MANUAL_CLAIMING;
    assert(!atomic_compare_exchange_strong(&ctl.phase,&expected,
                                           VH_MANUAL_QUEUED));
    assert(atomic_load(&ctl.phase)==VH_MANUAL_FAILED);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
}

static void test_shutdown_is_terminal_after_prior_success(void) {
    VhAudioManualTransport ctl;
    vh_audio_manual_init(&ctl);
    assert(vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(vh_audio_manual_take(&ctl)==VH_MANUAL_REOPEN);
    vh_audio_manual_finished_service(&ctl,1,100u);
    vh_audio_manual_returned_pcm(&ctl,101u);
    assert(atomic_load(&ctl.reopen_result)==2);
    vh_audio_manual_abort_pending(&ctl);
    vh_audio_manual_abort_pending(&ctl);
    assert(atomic_load(&ctl.phase)==VH_MANUAL_STOPPED);
    assert(atomic_load(&ctl.reopen_result)==2);
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_REOPEN));
    assert(!vh_audio_manual_request(&ctl,VH_MANUAL_QUICK));
}

int main(void) {
    test_requires_real_returned_pcm();
    test_new_manual_command_after_verified_pcm();
    test_failed_service_remains_failed();
    test_spurious_pcm_without_command_is_not_evidence();
    test_pcm_count_wrap_never_confirms();
    test_post_service_evidence_is_not_carried_across_retries();
    test_worker_exit_marks_pending_and_queued_as_failure();
    test_worker_exit_preserves_confirmed_and_idle();
    test_interrupted_claim_cannot_resurrect_queue();
    test_shutdown_is_terminal_after_prior_success();
    puts("manual X/Y audout mailbox: serialized commands and post-service PCM PASS (host fixtures)");
    return 0;
}
