#ifndef VH_AUDIO_EXIT_TAIL_REASON_STAGE351_H
#define VH_AUDIO_EXIT_TAIL_REASON_STAGE351_H

/* Stage351: worker-owned classification of optional normal-exit tail.
 * This is strictly a SOFTWARE service/lease outcome, never a DAC,
 * queue-drain, speaker, audio-quality or physical Switch observation.
 * No clock reads, syscalls, allocations, waits or I/O in the recording
 * function. The sole writer is the audio worker; read only after join.
 */
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include "vh_audio_diagnostics.h"
#include "vh_audio_exit_output_witness.h"

typedef enum {
    VH_TAIL_NOT_ATTEMPTED = 0,
    VH_TAIL_PRECONDITION_FAILED = 1,
    VH_TAIL_LEASE_BUSY = 2,
    VH_TAIL_APPEND_FAILED = 3,
    VH_TAIL_WAIT_FAILED = 4,
    VH_TAIL_WAIT_EMPTY = 5,
    VH_TAIL_RELEASE_MISMATCH = 6,
    VH_TAIL_RETURN_CONFIRMED = 7
} VhAudioTailReasonCode;

typedef struct {
    atomic_uint code;
} VhAudioExitTailReason;

static inline void vh_audio_tail_reason_reset(VhAudioExitTailReason *w) {
    if (w) atomic_store_explicit(&w->code,VH_TAIL_NOT_ATTEMPTED,
                                 memory_order_relaxed);
}
static inline void vh_audio_tail_reason_record(
        VhAudioExitTailReason *w,VhAudioTailReasonCode code) {
    if (w) atomic_store_explicit(&w->code,(unsigned)code,memory_order_release);
}
static inline unsigned vh_audio_tail_reason_read(
        const VhAudioExitTailReason *w) {
    return w ? atomic_load_explicit(&w->code,memory_order_acquire) :
               VH_TAIL_NOT_ATTEMPTED;
}

/* The new guest file is independent from existing Stage313/347 CSVs.
 * Fail closed unless the original Stage313 tail witnesses and final
 * Stage347 descriptor conservation agree with this exit classification.
 * Eight numeric rows after the unchanged scope,value header.
 */
static inline int vh_audio_tail_reason_write_csv(
        const VhAudioExitTailReason *reason,
        const VhAudioExitOutputWitness *old_tail,
        const VhAudioDiagnostics *final,
        FILE *out) {
    if (!reason || !old_tail || !final || !out) return -1;
    const unsigned code=vh_audio_tail_reason_read(reason);
    if (code>VH_TAIL_RETURN_CONFIRMED) return -1;
    const uint64_t old_attempt=vh_audio_exit_output_read(
        &old_tail->tail_attempt_guest_ns);
    const uint64_t old_success=vh_audio_exit_output_read(
        &old_tail->tail_success_return_guest_ns);
    const unsigned attempted=code!=VH_TAIL_NOT_ATTEMPTED;
    const unsigned returned=code==VH_TAIL_RETURN_CONFIRMED;
    const unsigned owned_during_tail=
        code>=VH_TAIL_APPEND_FAILED && code<=VH_TAIL_RETURN_CONFIRMED;
    if ((old_attempt!=0)!=attempted || (old_success!=0)!=returned ||
        (returned && old_success<old_attempt) ||
        !final->lease_pages_acquired ||
        final->lease_pages_acquired==UINT64_MAX ||
        final->lease_pages_released==UINT64_MAX ||
        final->abandoned_sessions==UINT32_MAX ||
        final->lease_pages_released>final->lease_pages_acquired ||
        final->lease_pages_acquired-final->lease_pages_released!=
            (uint64_t)final->abandoned_sessions ||
        final->pages_submitted>final->lease_pages_released ||
        (owned_during_tail && !returned && !final->abandoned_sessions))
        return -1;
    if (fprintf(out,
        "scope,value\n"
        "software_exit_tail_reason_only,1\n"
        "tail_reason_code,%u\n"
        "tail_attempted,%u\n"
        "tail_descriptor_return_confirmed,%u\n"
        "tail_lease_acquired,%u\n"
        "lease_pages_acquired,%llu\n"
        "lease_pages_released,%llu\n"
        "abandoned_sessions,%u\n",
        code,attempted,returned,owned_during_tail,
        (unsigned long long)final->lease_pages_acquired,
        (unsigned long long)final->lease_pages_released,
        final->abandoned_sessions)<0) return -1;
    return 8;
}
#endif
