#ifndef VH_AUDIO_FOCUS_TRACE_H
#define VH_AUDIO_FOCUS_TRACE_H

/* Host-testable observation of actual libnx focus notifications.
 * No audout calls, playback decisions, simulated inputs or HOME events.
 * A focus cycle is Background -> InFocus. Duplicate notifications do
 * not create additional cycles. All fields are atomic because painting
 * and the audio producer may run on different threads.
 */
#include <limits.h>
#include <stdatomic.h>

enum {
    VH_FOCUS_NONE = 0u,
    VH_FOCUS_BACKGROUND = 1u,
    VH_FOCUS_RETURNED = 2u
};

typedef struct {
    atomic_uint phase;
    atomic_uint backgrounds;
    atomic_uint foreground_returns;
    atomic_uint resumes;
    atomic_uint pages_at_return;
} VhAudioFocusTrace;

typedef struct {
    unsigned phase;
    unsigned backgrounds;
    unsigned foreground_returns;
    unsigned resumes;
    unsigned pages_at_return;
    int post_return_pcm;
} VhAudioFocusObservation;

static inline void vh_audio_focus_trace_init(VhAudioFocusTrace *trace) {
    atomic_init(&trace->phase, VH_FOCUS_NONE);
    atomic_init(&trace->backgrounds, 0u);
    atomic_init(&trace->foreground_returns, 0u);
    atomic_init(&trace->resumes, 0u);
    atomic_init(&trace->pages_at_return, 0u);
}

/* Saturate instead of wrapping counts displayed as evidence. */
static inline void vh_audio_focus_trace_increment(atomic_uint *counter) {
    unsigned value=atomic_load_explicit(counter,memory_order_relaxed);
    while(value!=UINT_MAX &&
          !atomic_compare_exchange_weak_explicit(
              counter,&value,value+1u,memory_order_relaxed,
              memory_order_relaxed)) {}
}

static inline void vh_audio_focus_trace_background(VhAudioFocusTrace *trace) {
    if(atomic_load_explicit(&trace->phase,memory_order_acquire)
       ==VH_FOCUS_BACKGROUND) return;
    vh_audio_focus_trace_increment(&trace->backgrounds);
    atomic_store_explicit(&trace->phase,VH_FOCUS_BACKGROUND,
                          memory_order_release);
}

static inline void vh_audio_focus_trace_foreground(
    VhAudioFocusTrace *trace,unsigned returned_pcm_pages) {
    if(atomic_load_explicit(&trace->phase,memory_order_acquire)
       !=VH_FOCUS_BACKGROUND) return;
    /* Reset the baseline on EVERY genuine return, so a previous
     * completed cycle cannot satisfy the PCM marker for this cycle.
     * Publishing phase last makes the baseline visible to snapshots. */
    atomic_store_explicit(&trace->pages_at_return,returned_pcm_pages,
                          memory_order_relaxed);
    vh_audio_focus_trace_increment(&trace->foreground_returns);
    atomic_store_explicit(&trace->phase,VH_FOCUS_RETURNED,
                          memory_order_release);
}

static inline void vh_audio_focus_trace_resume(VhAudioFocusTrace *trace) {
    vh_audio_focus_trace_increment(&trace->resumes);
}

static inline VhAudioFocusObservation vh_audio_focus_trace_observe(
    const VhAudioFocusTrace *trace,unsigned returned_pcm_pages) {
    VhAudioFocusObservation result;
    const unsigned first_phase=atomic_load_explicit(
        &trace->phase,memory_order_acquire);
    result.backgrounds=atomic_load_explicit(
        &trace->backgrounds,memory_order_relaxed);
    result.foreground_returns=atomic_load_explicit(
        &trace->foreground_returns,memory_order_relaxed);
    result.resumes=atomic_load_explicit(
        &trace->resumes,memory_order_relaxed);
    result.pages_at_return=atomic_load_explicit(
        &trace->pages_at_return,memory_order_relaxed);
    result.phase=atomic_load_explicit(&trace->phase,memory_order_acquire);
    /* If focus changed while painting, fail closed for this frame.
     * Do not accept uint32 PCM counter wrap as proof of progress. */
    result.post_return_pcm=(first_phase==VH_FOCUS_RETURNED &&
                            result.phase==VH_FOCUS_RETURNED &&
                            result.foreground_returns>0u &&
                            returned_pcm_pages>result.pages_at_return);
    return result;
}

#endif
