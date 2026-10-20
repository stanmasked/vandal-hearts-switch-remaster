#ifndef VH_AUDIO_EXIT_TAIL_CHECKS_STAGE353_H
#define VH_AUDIO_EXIT_TAIL_CHECKS_STAGE353_H

/* Stage353: portable post-service decision rules for the EXISTING bounded
 * audout exit-tail path. Audio owner only; C11, no syscall, wait, clock,
 * memory allocation, file/PCM access or GPU work. Caller continues to
 * invoke the ORIGINAL libnx append and wait exactly once each. The
 * service return and exact descriptor lease semantics are unchanged.
 *
 * Synthetic host fault injection may call these SAME decision helpers,
 * including foreign/NULL descriptors, while the normal production code
 * passes actual libnx service results. Neither proves audible playback.
 */
#include "vh_audio_buffer_lease.h"
#include "vh_audio_exit_tail_reason_stage351.h"

/* 0 means continue to original bounded wait, -1 preserve lease until
 * the whole service session is exited. Only records software reason. */
static inline int vh_audio_tail_stage353_append_checked(
        VhAudioExitTailReason *reason, int append_failed) {
    if (append_failed) {
        vh_audio_tail_reason_record(reason,VH_TAIL_APPEND_FAILED);
        return -1;
    }
    return 0;
}

/* Called after the unchanged 12ms maximum wait exactly once. Failed
 * service return or empty release list MUST NOT return lease ownership.
 * On a released descriptor, ask the existing exact-token lease checker.
 */
static inline int vh_audio_tail_stage353_wait_checked(
        VhAudioExitTailReason *reason,
        VhAudioBufferLease *lease,
        int wait_failed,
        unsigned released_count,
        const void *released) {
    if (wait_failed) {
        vh_audio_tail_reason_record(reason,VH_TAIL_WAIT_FAILED);
        return -1;
    }
    if (!released_count) {
        vh_audio_tail_reason_record(reason,VH_TAIL_WAIT_EMPTY);
        return -1;
    }
    if (vh_audio_buffer_lease_release(lease,released)) {
        vh_audio_tail_reason_record(reason,VH_TAIL_RELEASE_MISMATCH);
        return -1;
    }
    vh_audio_tail_reason_record(reason,VH_TAIL_RETURN_CONFIRMED);
    return 0;
}

#endif
