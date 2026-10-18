#ifndef VH_AUDIO_EXIT_OUTPUT_WITNESS_H
#define VH_AUDIO_EXIT_OUTPUT_WITNESS_H

/* Stage313, diagnostic-only: the last RELEASED audout page and optional
 * normal-exit taper, stamped in the SAME guest software time domain as
 * the Stage307 Plus/stop/cleanup/join events.
 *
 * A successful page return releases a buffer lease; it is NOT a DAC,
 * speaker sound, audible sample, or successful original soundtrack.
 * No malloc, I/O or waiting is added to the audio owner hot loop.
 */
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>

typedef struct {
    atomic_uint_fast64_t page_count;
    atomic_uint_fast64_t last_page_return_guest_ns;
    atomic_uint_fast64_t last_page_frames;
    atomic_uint_fast64_t tail_attempt_guest_ns;
    atomic_uint_fast64_t tail_success_return_guest_ns;
} VhAudioExitOutputWitness;

static inline void vh_audio_exit_output_reset(VhAudioExitOutputWitness *w) {
    if (!w) return;
    atomic_store_explicit(&w->page_count,0,memory_order_relaxed);
    atomic_store_explicit(&w->last_page_return_guest_ns,0,memory_order_relaxed);
    atomic_store_explicit(&w->last_page_frames,0,memory_order_relaxed);
    atomic_store_explicit(&w->tail_attempt_guest_ns,0,memory_order_relaxed);
    atomic_store_explicit(&w->tail_success_return_guest_ns,0,memory_order_relaxed);
}

/* Called by one audout owner AFTER vh_audio_output_submit_recover
 * succeeded for this original PCM page. Not a count of lower-level
 * audoutPlayBuffer retries and never a measured speaker frame. */
static inline int vh_audio_exit_output_page_returned(
        VhAudioExitOutputWitness *w,uint64_t now_ns,uint64_t page_frames) {
    if (!w || !now_ns || !page_frames || page_frames>4096) return -1;
    const uint64_t previous=(uint64_t)atomic_load_explicit(
        &w->last_page_return_guest_ns,memory_order_relaxed);
    if (previous>now_ns) return -1;
    atomic_store_explicit(&w->last_page_frames,page_frames,memory_order_relaxed);
    atomic_store_explicit(&w->last_page_return_guest_ns,now_ns,memory_order_release);
    atomic_fetch_add_explicit(&w->page_count,1,memory_order_release);
    return 1;
}

/* Optional exit taper attempt and its bounded RELEASE confirmation.
 * A failed bounded attempt records no successful return timestamp.
 * Not invoked for HOME/focus loss; never claims sound or DAC drain. */
static inline int vh_audio_exit_output_tail(
        VhAudioExitOutputWitness *w,uint64_t began_ns,
        uint64_t ended_ns,int returned) {
    if (!w || !began_ns || ended_ns<began_ns || (returned!=0 && returned!=1))
        return -1;
    uint_fast64_t zero=0;
    if (!atomic_compare_exchange_strong_explicit(
            &w->tail_attempt_guest_ns,&zero,began_ns,
            memory_order_release,memory_order_relaxed))
        return -1;
    if (returned)
        atomic_store_explicit(&w->tail_success_return_guest_ns,
                              ended_ns,memory_order_release);
    return 1;
}
static inline uint64_t vh_audio_exit_output_read(
        const atomic_uint_fast64_t *field) {
    return (uint64_t)atomic_load_explicit(field,memory_order_acquire);
}

/* Post-join only; exact canonical guest source is a new separate CSV
 * so the five-row Stage307 original receipt is byte-for-byte unchanged.
 */
static inline int vh_audio_exit_output_write_csv(
        const VhAudioExitOutputWitness *w, FILE *out) {
    if (!w || !out || fputs("event,value\n",out)<0) return -1;
    const char *const labels[]={
        "page_return_count", "last_page_return_guest_ns", "last_page_frames",
        "tail_attempt_guest_ns", "tail_success_return_guest_ns"
    };
    const atomic_uint_fast64_t *const fields[]={
        &w->page_count, &w->last_page_return_guest_ns, &w->last_page_frames,
        &w->tail_attempt_guest_ns, &w->tail_success_return_guest_ns
    };
    for (unsigned i=0;i<5u;i++)
        if (fprintf(out,"%s,%llu\n",labels[i],
            (unsigned long long)vh_audio_exit_output_read(fields[i]))<0)
            return -1;
    return 5;
}
#endif
