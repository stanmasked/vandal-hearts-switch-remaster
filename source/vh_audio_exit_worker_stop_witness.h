#ifndef VH_AUDIO_EXIT_WORKER_STOP_WITNESS_H
#define VH_AUDIO_EXIT_WORKER_STOP_WITNESS_H

/* Stage317: one-shot guest SOFTWARE observation of running==0 at
 * the audio worker's existing loop boundary. Recording this does NOT
 * mean a DAC, queued sound or speaker stopped playing.
 * Never add waits, allocations or IO in the audout/audio owner.
 */
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>

typedef struct {
    atomic_uint_fast64_t stop_observed_guest_ns;
} VhAudioExitWorkerStopWitness;

static inline void vh_audio_exit_worker_stop_reset(
        VhAudioExitWorkerStopWitness *w) {
    if (w)
        atomic_store_explicit(&w->stop_observed_guest_ns,
                              0,memory_order_relaxed);
}

/* Only the audio worker calls this when its SINGLE existing mailbox
 * running() read has ALREADY returned false. 0 means unobserved,
 * including early audio initialization error or an unrelated break.
 */
static inline int vh_audio_exit_worker_stop_mark(
        VhAudioExitWorkerStopWitness *w,uint64_t guest_ns) {
    if (!w || !guest_ns) return -1;
    uint_fast64_t unset=0;
    return atomic_compare_exchange_strong_explicit(
        &w->stop_observed_guest_ns,&unset,(uint_fast64_t)guest_ns,
        memory_order_release,memory_order_relaxed) ? 1 : 0;
}
static inline uint64_t vh_audio_exit_worker_stop_read(
        const VhAudioExitWorkerStopWitness *w) {
    return w ? (uint64_t)atomic_load_explicit(
        &w->stop_observed_guest_ns,memory_order_acquire) : 0;
}

/* Call strictly after threadWaitForExit and threadClose.
 * Kept separate from Stage307/313 canonical original guest CSV files.
 */
static inline int vh_audio_exit_worker_stop_write_csv(
        const VhAudioExitWorkerStopWitness *w,FILE *f) {
    if (!w || !f || fprintf(f,
        "event,guest_monotonic_ns\n"
        "worker_stop_observed,%llu\n",
        (unsigned long long)vh_audio_exit_worker_stop_read(w))<0)
        return -1;
    return 1;
}
#endif
