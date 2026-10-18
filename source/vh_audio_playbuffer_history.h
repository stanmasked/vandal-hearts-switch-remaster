#ifndef VH_AUDIO_PLAYBUFFER_HISTORY_H
#define VH_AUDIO_PLAYBUFFER_HISTORY_H

/* Stage322: keep only the last 16 REAL normal audoutPlayBuffer calls.
 * One audio owner thread writes; main thread reads only AFTER join.
 * Reuses Stage320's ALREADY captured begin/end timestamps. This does
 * add a bounded in-memory diagnostic write, never another clock, lock,
 * allocation, filesystem operation, service call or PCM modification.
 * Buffer lease return is NOT proof of speaker/DAC sample playback.
 */
#include <stdint.h>
#include <stdio.h>
#define VH_PLAYBUFFER_HISTORY_CAP 16u

typedef struct {
    uint64_t sequence;
    uint64_t begin_guest_ns;
    uint64_t end_guest_ns;
    unsigned lease_returned;
} VhPlayBufferHistoryEntry;

typedef struct {
    uint64_t total_attempts;
    uint64_t previous_end_guest_ns;
    unsigned rejected_clock_pairs;
    VhPlayBufferHistoryEntry last[VH_PLAYBUFFER_HISTORY_CAP];
} VhPlayBufferHistory;

static inline void vh_playbuffer_history_reset(VhPlayBufferHistory *h) {
    if (h) *h=(VhPlayBufferHistory){0};
}

static inline int vh_playbuffer_history_record(
        VhPlayBufferHistory *h, uint64_t begin, uint64_t end,
        int returned) {
    if (!h || (returned!=0 && returned!=1)) return -1;
    if (!begin || end<begin || h->total_attempts==UINT64_MAX ||
        (h->total_attempts && begin<h->previous_end_guest_ns)) {
        if (h->rejected_clock_pairs<UINT32_MAX)
            h->rejected_clock_pairs++;
        return -1;
    }
    const uint64_t seq=++h->total_attempts;
    const unsigned slot=(unsigned)((seq-1u)%VH_PLAYBUFFER_HISTORY_CAP);
    h->last[slot]=(VhPlayBufferHistoryEntry){
        seq,begin,end,(unsigned)returned
    };
    h->previous_end_guest_ns=end;
    return 1;
}

/* After joining the audio owner. Header and all rows contain the
 * total original call count, so wrapped ring windows are verifiable.
 * Zero actual calls writes a header ONLY, not synthetic samples. */
static inline int vh_playbuffer_history_write_csv(
        const VhPlayBufferHistory *h,FILE *f) {
    if (!h || !f || h->rejected_clock_pairs ||
        fputs("total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned\n",f)<0)
        return -1;
    const uint64_t retained=h->total_attempts<VH_PLAYBUFFER_HISTORY_CAP ?
        h->total_attempts : VH_PLAYBUFFER_HISTORY_CAP;
    const uint64_t first=h->total_attempts-retained+1;
    for (uint64_t seq=first;seq<=h->total_attempts && retained;seq++) {
        const VhPlayBufferHistoryEntry *e=
            &h->last[(unsigned)((seq-1)%VH_PLAYBUFFER_HISTORY_CAP)];
        if (e->sequence!=seq || e->end_guest_ns<e->begin_guest_ns ||
            fprintf(f,"%llu,%llu,%llu,%llu,%u\n",
                (unsigned long long)h->total_attempts,
                (unsigned long long)e->sequence,
                (unsigned long long)e->begin_guest_ns,
                (unsigned long long)e->end_guest_ns,
                e->lease_returned)<0)
            return -1;
    }
    return (int)retained;
}
#endif
