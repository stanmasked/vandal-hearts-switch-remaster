#ifndef VH_AUDIO_LISTENER_INPUT_H
#define VH_AUDIO_LISTENER_INPUT_H

#include "vh_audio_mark_buttons.h"
#include "vh_audio_listening_marks.h"

/* Commit a single controller sample and its optional A/B observation
 * as one transaction. Called AFTER exactly one successful PCM page
 * was inserted into marks, never for failed audout attempts.
 *
 * Stage the small gate (not the 32-page PCM metadata ring), then
 * validate/commit the listening annotation. If either operation
 * rejects the input, BOTH objects stay bit-for-bit unchanged.
 *
 * A failed annotation must never increment the gate's accepted-A/B
 * counters and create a contradictory partial final report.
 * No audio API, samples, heap allocation or file IO.
 */
static inline int vh_audio_listener_input_page(
    VhAudioMarkButtons *gate, VhAudioListeningMarks *marks,
    unsigned held) {
    if (!gate || !marks || !marks->returned_pages ||
        gate->polls!=marks->returned_pages-1u)
        return -1;
    VhAudioMarkButtons next=*gate;
    unsigned event=0u;
    if (vh_audio_mark_buttons_sample(&next,held,&event))
        return -1;
    if (event && vh_audio_listening_mark_kind(
            marks,(unsigned)(event==VH_AUDIO_MARK_B)))
        return -1;
    *gate=next;
    return 0;
}

#endif
