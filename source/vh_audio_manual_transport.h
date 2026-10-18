#ifndef VH_AUDIO_MANUAL_TRANSPORT_H
#define VH_AUDIO_MANUAL_TRANSPORT_H

/* Buttons may enqueue a transport operation; ONLY the audio producer
 * executes it after the preceding PCM descriptor has returned.
 * This mailbox is host-testable and deliberately separate from HOME hooks.
 * A "confirmed" X/Y indication requires the NEXT returned PCM page.
 */
#include <stdatomic.h>

typedef enum {
    VH_MANUAL_NONE = 0,
    VH_MANUAL_QUICK = 1,
    VH_MANUAL_REOPEN = 2
} VhAudioManualAction;

typedef enum {
    VH_MANUAL_FAILED = -1,
    VH_MANUAL_IDLE = 0,
    VH_MANUAL_CLAIMING = 1,
    VH_MANUAL_QUEUED = 2,
    VH_MANUAL_EXECUTING = 3,
    VH_MANUAL_WAIT_PCM = 4,
    VH_MANUAL_CONFIRMED = 5
} VhAudioManualPhase;

typedef struct {
    atomic_int phase;
    atomic_int action;
    atomic_int quick_result;  /* 0 untouched, 1 pending, 2 PCM returned, -1 error */
    atomic_int reopen_result;
    /* Logical count of REAL returned audout pages at service completion.
     * A stale PCM notification cannot certify a manual X/Y action. */
    atomic_uint returned_pages_at_service;
} VhAudioManualTransport;

static inline void vh_audio_manual_init(VhAudioManualTransport *ctl) {
    atomic_init(&ctl->phase, VH_MANUAL_IDLE);
    atomic_init(&ctl->action, VH_MANUAL_NONE);
    atomic_init(&ctl->quick_result, 0);
    atomic_init(&ctl->reopen_result, 0);
    atomic_init(&ctl->returned_pages_at_service, 0u);
}

/* Caller supplies real controller input; rejecting an overlapping input
 * MUST NOT replace the outstanding action. No locks or device calls here. */
static inline int vh_audio_manual_request(VhAudioManualTransport *ctl,
                                          VhAudioManualAction action) {
    if(action!=VH_MANUAL_QUICK && action!=VH_MANUAL_REOPEN) return 0;
    int phase=VH_MANUAL_IDLE;
    if(!atomic_compare_exchange_strong(&ctl->phase,&phase,
                                       VH_MANUAL_CLAIMING)) {
        phase=VH_MANUAL_CONFIRMED;
        if(!atomic_compare_exchange_strong(&ctl->phase,&phase,
                                           VH_MANUAL_CLAIMING)) return 0;
    }
    atomic_store(&ctl->action,action);
    atomic_store(action==VH_MANUAL_QUICK ?
                 &ctl->quick_result : &ctl->reopen_result,1);
    atomic_store(&ctl->phase,VH_MANUAL_QUEUED);
    return 1;
}

static inline VhAudioManualAction vh_audio_manual_take(
    VhAudioManualTransport *ctl) {
    int expected=VH_MANUAL_QUEUED;
    if(!atomic_compare_exchange_strong(&ctl->phase,&expected,
                                       VH_MANUAL_EXECUTING)) return VH_MANUAL_NONE;
    return (VhAudioManualAction)atomic_load(&ctl->action);
}

static inline void vh_audio_manual_finished_service(
    VhAudioManualTransport *ctl,int success,unsigned returned_pcm_pages) {
    if(atomic_load(&ctl->phase)!=VH_MANUAL_EXECUTING) return;
    if(!success) {
        const int action=atomic_load(&ctl->action);
        atomic_store(action==VH_MANUAL_QUICK ?
                     &ctl->quick_result : &ctl->reopen_result,-1);
        atomic_store(&ctl->phase,VH_MANUAL_FAILED);
    } else {
        atomic_store(&ctl->returned_pages_at_service,returned_pcm_pages);
        atomic_store(&ctl->phase,VH_MANUAL_WAIT_PCM);
    }
}

/* The worker supplies the logical audout return count AFTER a confirmed
 * descriptor return, not a mere generated PCM block or service restart.
 * Strict monotonicity also rejects stale, duplicate and wrapped counters. */
static inline void vh_audio_manual_returned_pcm(
    VhAudioManualTransport *ctl,unsigned returned_pcm_pages) {
    if(atomic_load(&ctl->phase)!=VH_MANUAL_WAIT_PCM ||
       returned_pcm_pages<=atomic_load(&ctl->returned_pages_at_service))
        return;
    const int action=atomic_load(&ctl->action);
    atomic_store(action==VH_MANUAL_QUICK ?
                 &ctl->quick_result : &ctl->reopen_result,2);
    atomic_store(&ctl->phase,VH_MANUAL_CONFIRMED);
}
#endif
