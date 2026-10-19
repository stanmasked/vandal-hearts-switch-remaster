#ifndef VH_AUDIO_EXIT_TAIL_WAIT_RESULT_STAGE357_H
#define VH_AUDIO_EXIT_TAIL_WAIT_RESULT_STAGE357_H

/* Stage357: raw software Result from the already-existing *single*
 * bounded exit-tail audoutWaitPlayFinish call. The writer is the audio
 * worker, and the reader is the main thread strictly AFTER join.
 * No extra waits, clocks, heap, I/O or service calls on the audio path.
 * This value identifies the service API result, not an audible glitch,
 * DAC delivery, original soundtrack sample or physical Switch test.
 */
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include "vh_audio_exit_tail_reason_stage351.h"

typedef struct {
    atomic_uint observed;
    atomic_uint raw_result;
} VhAudioTailWaitResult357;

static inline void vh_tail357_reset(VhAudioTailWaitResult357 *w) {
    if (!w) return;
    atomic_store_explicit(&w->observed,0u,memory_order_relaxed);
    atomic_store_explicit(&w->raw_result,0u,memory_order_relaxed);
}

static inline void vh_tail357_record(
    VhAudioTailWaitResult357 *w,uint32_t result
) {
    if (!w) return;
    atomic_store_explicit(&w->raw_result,(unsigned)result,memory_order_relaxed);
    atomic_store_explicit(&w->observed,1u,memory_order_release);
}

/* Canonical four numeric data rows after scope,value.
 * A valid Stage351 wait_failed code MUST have one observed nonzero Result.
 * A successfully returned or emptied wait had a zero Result. No wait
 * may be recorded on precondition/lease/append errors or no attempt.
 */
static inline int vh_tail357_write_csv(
    const VhAudioTailWaitResult357 *w,
    const VhAudioExitTailReason *reason,FILE *out
) {
    if (!w || !reason || !out) return -1;
    const unsigned seen=atomic_load_explicit(&w->observed,memory_order_acquire);
    const unsigned raw=atomic_load_explicit(&w->raw_result,memory_order_acquire);
    const unsigned code=vh_audio_tail_reason_read(reason);
    if (code>VH_TAIL_RETURN_CONFIRMED || seen>1u ||
        (code<=VH_TAIL_APPEND_FAILED && (seen || raw)) ||
        (code>=VH_TAIL_WAIT_FAILED && !seen) ||
        (code==VH_TAIL_WAIT_FAILED && !raw) ||
        (code>=VH_TAIL_WAIT_EMPTY && raw))
        return -1;
    if (fprintf(out,
        "scope,value\n"
        "software_wait_result_only,1\n"
        "wait_result_observed,%u\n"
        "audout_wait_result_raw,%u\n"
        "stage351_tail_reason_code,%u\n",
        seen,raw,code)<0) return -1;
    return 4;
}
#endif
