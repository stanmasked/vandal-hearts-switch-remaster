#ifndef VH_AUDIO_EXIT_TIMELINE_H
#define VH_AUDIO_EXIT_TIMELINE_H

/* Stage307: optional guest-monotonic lifecycle facts only.
 * Same armGetSystemTick() -> ns timebase is supplied by callers.
 * One-shot atomic slots avoid allocations, mutexes and IO in the audio
 * worker, game loop, output close, and stop request path.
 * Consumers may dump only after the audio worker is joined.
 * These are guest SOFTWARE event times, never host keydown, DAC or sound.
 */
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>

enum {
    VH_EXIT_PLUS_OBSERVED=0,
    VH_EXIT_STOP_REQUESTED=1,
    VH_EXIT_WORKER_CLEANUP_ENTERED=2,
    VH_EXIT_AUDOUT_CLOSED=3,
    VH_EXIT_WORKER_JOINED=4,
    VH_EXIT_EVENT_COUNT=5,
};
typedef struct {
    atomic_uint_fast64_t monotonic_ns[VH_EXIT_EVENT_COUNT];
} VhAudioExitTimeline;

static inline void vh_audio_exit_timeline_reset(VhAudioExitTimeline *t) {
    if (!t) return;
    for (unsigned i=0; i<VH_EXIT_EVENT_COUNT; i++)
        atomic_store_explicit(&t->monotonic_ns[i],0,memory_order_relaxed);
}

/* Nonzero unique timestamp, first writer wins, no cross-thread wait. */
static inline int vh_audio_exit_timeline_mark(VhAudioExitTimeline *t,
                                               unsigned event,
                                               uint64_t guest_ns) {
    if (!t || event>=VH_EXIT_EVENT_COUNT || !guest_ns) return -1;
    uint_fast64_t zero=0;
    return atomic_compare_exchange_strong_explicit(
        &t->monotonic_ns[event], &zero, (uint_fast64_t)guest_ns,
        memory_order_release,memory_order_relaxed) ? 1 : 0;
}

static inline uint64_t vh_audio_exit_timeline_get(
        const VhAudioExitTimeline *t, unsigned event) {
    if (!t || event>=VH_EXIT_EVENT_COUNT) return 0;
    return (uint64_t)atomic_load_explicit(
        &t->monotonic_ns[event],memory_order_acquire);
}

/* Post-join only: no write during worker playback or app input.
 * Missing event = 0, e.g. fatal worker cleanup before a Plus exit.
 * Do not sort by timestamps: event names define distinct control sites.
 */
static inline int vh_audio_exit_timeline_write_csv(
        const VhAudioExitTimeline *t, FILE *out) {
    static const char *const names[VH_EXIT_EVENT_COUNT]={
        "plus_observed", "stop_requested", "worker_cleanup_entered",
        "audout_closed", "worker_joined"
    };
    if (!t || !out || fputs("event,guest_monotonic_ns\n",out)<0) return -1;
    for (unsigned i=0;i<VH_EXIT_EVENT_COUNT;i++)
        if (fprintf(out,"%s,%llu\n",names[i],
                    (unsigned long long)vh_audio_exit_timeline_get(t,i))<0)
            return -1;
    return VH_EXIT_EVENT_COUNT;
}
#endif
