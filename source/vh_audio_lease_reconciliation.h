#ifndef VH_AUDIO_LEASE_RECONCILIATION_H
#define VH_AUDIO_LEASE_RECONCILIATION_H
/* Stage347: software-only PCM descriptor lifecycle reconciliation.
 * Only call after the owner thread joined. No DAC, device queue or
 * acoustic sample timing can be inferred from these counters.
 */
#include "vh_audio_diagnostics.h"
#include <stdint.h>
#include <stdio.h>

static inline int vh_audio_lease_reconciliation_valid(
        const VhAudioDiagnostics *s) {
    if (!s || !s->lease_pages_acquired
        || s->lease_pages_acquired==UINT64_MAX
        || s->lease_pages_released==UINT64_MAX
        || s->abandoned_sessions==UINT32_MAX
        || s->lease_pages_released>s->lease_pages_acquired
        || s->lease_pages_acquired-s->lease_pages_released!=
            (uint64_t)s->abandoned_sessions
        || s->pages_submitted>s->lease_pages_released)
        return -1;
    return 0;
}
/* Eight canonical source-only data rows after header. Do not emit
 * absolute guest/host timestamps or raw PCM. Invalid source emits
 * nothing and cannot be misclassified as accepted evidence.
 */
static inline int vh_audio_lease_reconciliation_write(
        const VhAudioDiagnostics *s, FILE *out) {
    if (!out || vh_audio_lease_reconciliation_valid(s)) return -1;
    if (fprintf(out,
            "scope,value\n"
            "software_lease_only,1\n"
            "lease_pages_acquired,%llu\n"
            "lease_pages_released,%llu\n"
            "abandoned_sessions,%u\n"
            "busy_begin_rejections,%u\n"
            "mismatched_releases,%u\n"
            "accepted_pages_submitted,%llu\n"
            "submit_failures,%u\n",
            (unsigned long long)s->lease_pages_acquired,
            (unsigned long long)s->lease_pages_released,
            s->abandoned_sessions,s->lease_busy_begin_rejections,
            s->lease_mismatches,
            (unsigned long long)s->pages_submitted,s->submit_failures)<0)
        return -1;
    return 8;
}
#endif
