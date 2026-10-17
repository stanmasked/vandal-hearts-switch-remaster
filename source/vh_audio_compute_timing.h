#ifndef VH_AUDIO_COMPUTE_TIMING_H
#define VH_AUDIO_COMPUTE_TIMING_H
#include <stdint.h>
#include <limits.h>

/* CPU time for SEQ + SPU + sample-rate conversion, not blocking
 * audoutPlayBuffer or console updates. The synthetic scene-switch
 * call belongs to its FIRST newly rendered page. Each failed final
 * audout submission can leave one rendered-but-undelivered page.
 */
typedef struct {
    uint64_t rendered_pages, total_ticks, max_ticks, over_budget;
} VhAudioComputeBucket;

typedef struct {
    uint64_t rendered_pages, total_ticks, max_ticks, over_budget;
    VhAudioComputeBucket ordinary, first_after_switch;
    unsigned last_after_switch; /* class of the final rendered page */
} VhAudioComputeTiming;

/* Increment the overall accumulator and exactly one category.
 * The same budget classification is applied to both. Reject all
 * invalid inputs and overflows before changing either bucket.
 */
static inline int vh_audio_compute_record(
    VhAudioComputeTiming *s, uint64_t elapsed, uint64_t nominal,
    unsigned first_after_switch) {
    if (!s || !nominal || first_after_switch>1u) return -1;
    VhAudioComputeBucket *b=first_after_switch
        ? &s->first_after_switch : &s->ordinary;
    const uint64_t slow=(uint64_t)(elapsed>nominal);
    if (s->rendered_pages==UINT64_MAX ||
        b->rendered_pages==UINT64_MAX ||
        s->total_ticks>UINT64_MAX-elapsed ||
        b->total_ticks>UINT64_MAX-elapsed ||
        s->over_budget>UINT64_MAX-slow ||
        b->over_budget>UINT64_MAX-slow) return -1;
    ++s->rendered_pages;
    s->total_ticks+=elapsed;
    if (elapsed>s->max_ticks) s->max_ticks=elapsed;
    s->over_budget+=slow;
    ++b->rendered_pages;
    b->total_ticks+=elapsed;
    if (elapsed>b->max_ticks) b->max_ticks=elapsed;
    b->over_budget+=slow;
    s->last_after_switch=first_after_switch;
    return 0;
}

static inline int vh_audio_compute_bucket_valid(
    const VhAudioComputeBucket *b) {
    return b->over_budget<=b->rendered_pages &&
           b->max_ticks<=b->total_ticks &&
           (b->rendered_pages || (!b->total_ticks && !b->max_ticks &&
                                  !b->over_budget));
}

/* Correlate compute groups with actually returned ordinary and
 * first-after-switch PCM pages. A failed final audio submission
 * may leave at most ONE synthesized page without a return, in
 * either group. No silent compensating category error is accepted.
 */
static inline int vh_audio_compute_verify(
    const VhAudioComputeTiming *s, uint64_t returned_pages,
    uint64_t returned_switch_pages) {
    if (!s || s->last_after_switch>1u ||
        (!s->rendered_pages && s->last_after_switch) ||
        returned_switch_pages>returned_pages ||
        s->rendered_pages<returned_pages ||
        s->rendered_pages-returned_pages>1u ||
        !vh_audio_compute_bucket_valid(&s->ordinary) ||
        !vh_audio_compute_bucket_valid(&s->first_after_switch) ||
        s->ordinary.rendered_pages>UINT64_MAX-
            s->first_after_switch.rendered_pages ||
        s->ordinary.total_ticks>UINT64_MAX-
            s->first_after_switch.total_ticks ||
        s->ordinary.over_budget>UINT64_MAX-
            s->first_after_switch.over_budget) return -1;
    if (s->ordinary.rendered_pages+
            s->first_after_switch.rendered_pages!=s->rendered_pages ||
        s->ordinary.total_ticks+
            s->first_after_switch.total_ticks!=s->total_ticks ||
        s->ordinary.over_budget+
            s->first_after_switch.over_budget!=s->over_budget ||
        s->max_ticks!=(s->ordinary.max_ticks>s->first_after_switch.max_ticks
            ? s->ordinary.max_ticks : s->first_after_switch.max_ticks))
        return -1;
    const uint64_t ordinary_returned=returned_pages-returned_switch_pages;
    if (s->ordinary.rendered_pages<ordinary_returned ||
        s->first_after_switch.rendered_pages<returned_switch_pages ||
        s->ordinary.rendered_pages-ordinary_returned>1u ||
        s->first_after_switch.rendered_pages-returned_switch_pages>1u)
        return -1;
    const uint64_t missing_ordinary=
        s->ordinary.rendered_pages-ordinary_returned;
    const uint64_t missing_switch=
        s->first_after_switch.rendered_pages-returned_switch_pages;
    if (missing_ordinary+missing_switch!=
        s->rendered_pages-returned_pages) return -1;
    /* A terminally failed submission cannot prevent an earlier page
     * from returning while a later rendered page is already delivered.
     * The single outstanding page must belong to the last render. */
    if (missing_ordinary+missing_switch==1u &&
        s->last_after_switch!=(unsigned)(missing_switch==1u))
        return -1;
    return 0;
}
#endif
