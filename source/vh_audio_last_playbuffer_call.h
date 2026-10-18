#ifndef VH_AUDIO_LAST_PLAYBUFFER_CALL_H
#define VH_AUDIO_LAST_PLAYBUFFER_CALL_H

/* Stage320: owner-only diagnostic witness. Reuse the ALREADY measured
 * begin/end ns around each audoutPlayBuffer. No new clock read, no
 * allocations/locks/I/O and no change to the service invocation.
 * Success means an exact buffer descriptor lease was returned, not
 * a final DAC or audible speaker sample.
 */
#include <stdint.h>
#include <stdio.h>

typedef struct {
    uint64_t attempts;
    uint64_t successes;
    uint64_t failures;
    uint64_t last_success_begin_guest_ns;
    uint64_t last_success_end_guest_ns;
    uint64_t last_success_attempt;
    unsigned nonmonotonic_rejected;
} VhAudioLastPlayBufferCall;

static inline void vh_audio_last_playbuffer_reset(VhAudioLastPlayBufferCall *w) {
    if (w) *w=(VhAudioLastPlayBufferCall){0};
}

/* Record only the successful final service/lease call on a guest
 * software clock. Errors do not replace an earlier valid success.
 * Bad clock inputs fail closed, with an explicit error tally. */
static inline int vh_audio_last_playbuffer_record(
        VhAudioLastPlayBufferCall *w, uint64_t begin_ns,
        uint64_t end_ns, int exact_lease_returned) {
    if (!w || (exact_lease_returned!=0 && exact_lease_returned!=1))
        return -1;
    if (!begin_ns || end_ns<begin_ns || w->attempts==UINT64_MAX ||
            (w->successes &&
             begin_ns<w->last_success_end_guest_ns)) {
        if (w->nonmonotonic_rejected<UINT32_MAX)
            w->nonmonotonic_rejected++;
        return -1;
    }
    w->attempts++;
    if (!exact_lease_returned) {
        w->failures++;
        return 0;
    }
    w->successes++;
    w->last_success_begin_guest_ns=begin_ns;
    w->last_success_end_guest_ns=end_ns;
    w->last_success_attempt=w->attempts;
    return 1;
}

/* Called only after the audout owner has joined. The canonical
 * Stage307/313/317 original CSVs remain byte-identical. */
static inline int vh_audio_last_playbuffer_write_csv(
        const VhAudioLastPlayBufferCall *w,FILE *f) {
    if (!w || !f) return -1;
    return fprintf(f,
        "event,value\n"
        "attempts,%llu\n"
        "successes,%llu\n"
        "failures,%llu\n"
        "last_success_attempt,%llu\n"
        "last_success_begin_guest_ns,%llu\n"
        "last_success_end_guest_ns,%llu\n"
        "nonmonotonic_rejected,%u\n",
        (unsigned long long)w->attempts,
        (unsigned long long)w->successes,
        (unsigned long long)w->failures,
        (unsigned long long)w->last_success_attempt,
        (unsigned long long)w->last_success_begin_guest_ns,
        (unsigned long long)w->last_success_end_guest_ns,
        w->nonmonotonic_rejected)<0 ? -1 : 7;
}
#endif
