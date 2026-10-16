#ifndef VH_AUDIO_INPUT_POLL_H
#define VH_AUDIO_INPUT_POLL_H
#include <stdint.h>
#include <limits.h>

/* Input sampling coverage, not audio latency or acoustic-glitch proof.
 * A short A-button tap between samples may be missed. No events/PCM
 * or per-sample timestamps are exported.
 */
typedef struct {
    uint64_t samples, last_tick, max_gap_ticks;
    uint64_t gaps_over_page, gaps_over_4pages;
} VhAudioInputPoll;

/* Sample exactly once after each returned PCM page. The first sample
 * has no predecessor. Reject bad tick order/overflow without mutation.
 */
static inline int vh_audio_input_poll_record(
    VhAudioInputPoll *s, uint64_t tick, uint64_t nominal_ticks) {
    if (!s || !nominal_ticks || s->samples==UINT64_MAX ||
        (s->samples && tick<s->last_tick)) return -1;
    if (s->samples) {
        const uint64_t gap=tick-s->last_tick;
        const unsigned slow=(unsigned)(gap>nominal_ticks);
        const unsigned huge=(unsigned)(
            nominal_ticks<=UINT64_MAX/4u && gap>4u*nominal_ticks);
        if ((slow && s->gaps_over_page==UINT64_MAX) ||
            (huge && s->gaps_over_4pages==UINT64_MAX))
            return -1;
        s->gaps_over_page+=slow;
        s->gaps_over_4pages+=huge;
        if (gap>s->max_gap_ticks) s->max_gap_ticks=gap;
    }
    s->last_tick=tick;
    ++s->samples;
    return 0;
}

/* Exactly one poll per returned page and N-1 measured intervals. */
static inline int vh_audio_input_poll_verify(
    const VhAudioInputPoll *s, uint64_t returned_pages) {
    return (!s || s->samples!=returned_pages ||
        s->gaps_over_page>(s->samples?s->samples-1u:0u) ||
        s->gaps_over_4pages>s->gaps_over_page ||
        (s->samples<2u && s->max_gap_ticks) ||
        (!s->samples && s->last_tick)) ? -1 : 0;
}
#endif
