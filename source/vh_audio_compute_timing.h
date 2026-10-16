#ifndef VH_AUDIO_COMPUTE_TIMING_H
#define VH_AUDIO_COMPUTE_TIMING_H
#include <stdint.h>
#include <limits.h>

/* Native SEQ + SPU + sample-rate conversion wall-clock compute time.
 * This excludes the blocking audoutPlayBuffer and report redraws.
 * A successfully rendered page can remain undelivered after a failed
 * output submission. No music state or PCM buffers are retained.
 */
typedef struct {
    uint64_t rendered_pages, total_ticks, max_ticks, over_budget;
} VhAudioComputeTiming;

/* Exactly one observation for each newly synthesized PCM page,
 * before passing it to the audio service. Any error is non-mutating. */
static inline int vh_audio_compute_record(
    VhAudioComputeTiming *s, uint64_t elapsed, uint64_t nominal) {
    if (!s || !nominal || s->rendered_pages==UINT64_MAX ||
        s->total_ticks>UINT64_MAX-elapsed ||
        (elapsed>nominal && s->over_budget==UINT64_MAX))
        return -1;
    ++s->rendered_pages;
    s->total_ticks+=elapsed;
    if (elapsed>s->max_ticks) s->max_ticks=elapsed;
    s->over_budget+=(unsigned)(elapsed>nominal);
    return 0;
}

/* A page may render, then fail or abort during its audout submission.
 * Therefore exactly delivered_pages or delivered_pages+1 pages
 * should have been synthesized; partial runs are not auto-invalid
 * merely because the final rendered page could not be delivered.
 * Any other mismatch prevents a FULL integrity verdict.
 */
static inline int vh_audio_compute_verify(
    const VhAudioComputeTiming *s, uint64_t delivered_pages) {
    if (!s || s->rendered_pages<delivered_pages ||
        s->rendered_pages-delivered_pages>1u ||
        s->over_budget>s->rendered_pages ||
        s->max_ticks>s->total_ticks ||
        (!s->rendered_pages && (s->total_ticks || s->max_ticks ||
                                s->over_budget)))
        return -1;
    return 0;
}
#endif
