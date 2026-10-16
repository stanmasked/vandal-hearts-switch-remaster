#ifndef VH_AUDIO_MARK_BUTTONS_H
#define VH_AUDIO_MARK_BUTTONS_H
#include <stdint.h>
#include <limits.h>

/* A held button and an opposite newly pressed button must not create
 * contradictory listening annotations. Poll current held A/B states.
 * The first neutral sample arms this gate; every mark/chord disarms it
 * until a later poll where BOTH buttons are released. Input only.
 */
#define VH_AUDIO_MARK_A 1u
#define VH_AUDIO_MARK_B 2u
#define VH_AUDIO_MARK_CHORD 3u
typedef struct {
    uint64_t polls, marks_a, marks_b, rejected_chords;
    unsigned armed;
} VhAudioMarkButtons;

/* event: 0, VH_AUDIO_MARK_A or VH_AUDIO_MARK_B.
 * Invalid inputs/counter overflow must leave state and event unchanged.
 */
static inline int vh_audio_mark_buttons_sample(
    VhAudioMarkButtons *s, unsigned held, unsigned *event) {
    if (!s || !event || held>VH_AUDIO_MARK_CHORD || s->armed>1u ||
        s->polls==UINT64_MAX) return -1;
    unsigned next=0u;
    if (s->armed) {
        if (held==VH_AUDIO_MARK_A) next=VH_AUDIO_MARK_A;
        if (held==VH_AUDIO_MARK_B) next=VH_AUDIO_MARK_B;
        if ((next==VH_AUDIO_MARK_A && s->marks_a==UINT64_MAX) ||
            (next==VH_AUDIO_MARK_B && s->marks_b==UINT64_MAX) ||
            (held==VH_AUDIO_MARK_CHORD &&
             s->rejected_chords==UINT64_MAX)) return -1;
    }
    if (held==0u) s->armed=1u;
    else if (s->armed) {
        s->armed=0u;
        if (next==VH_AUDIO_MARK_A) ++s->marks_a;
        else if (next==VH_AUDIO_MARK_B) ++s->marks_b;
        else ++s->rejected_chords;
    }
    ++s->polls;
    *event=next;
    return 0;
}

/* Counts must reconcile with successfully returned logical PCM pages,
 * operator A/B counters and mutually exclusive mark/chord samples.
 */
static inline int vh_audio_mark_buttons_verify(
    const VhAudioMarkButtons *s, uint64_t pages,
    uint64_t actual_a, uint64_t actual_b) {
    if (!s || s->armed>1u || s->polls!=pages ||
        s->marks_a!=actual_a || s->marks_b!=actual_b ||
        s->marks_a>pages ||
        s->marks_b>pages-s->marks_a ||
        s->rejected_chords>pages-s->marks_a-s->marks_b ||
        (!pages && s->armed)) return -1;
    return 0;
}
#endif
