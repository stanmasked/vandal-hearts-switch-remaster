#ifndef VH_AUDIO_EXIT_PROBE_CONTEXT_STAGE360_H
#define VH_AUDIO_EXIT_PROBE_CONTEXT_STAGE360_H

/* Stage360: one NORMAL EXIT context snapshot using existing clocks and
 * already collected normal PlayBuffer pre-submit SERVICE probes only.
 * The last pre-submit probe is NOT an audout queue measurement at exit.
 * No new service request, clock query, allocation, lock or PCM operation.
 * Single audio-worker writer, main-thread reader only after thread join.
 */
#include <stdint.h>
#include <stdio.h>
#include "vh_audout_queue_telemetry.h"
#include "vh_audio_exit_tail_reason_stage351.h"

typedef struct {
    unsigned captured;
    unsigned last_probe_available;
    unsigned last_probe_queue_status; /* 1=service query OK, 0=query failed */
    uint32_t last_probe_queue_count;   /* zero if query failed/absent */
    uint64_t tail_begin_ns,tail_end_ns;
    uint64_t normal_submit_attempts;
    uint64_t last_probe_attempt;
    uint64_t last_probe_age_ns; /* from pre-submit timestamp, NOT query time */
    uint64_t probe_dropped;
} VhTailProbeContext360;

static inline void vh_tail360_reset(VhTailProbeContext360 *w) {
    if(w) *w=(VhTailProbeContext360){0};
}

static inline int vh_tail360_capture(
        VhTailProbeContext360 *w,const VhAudoutQueueTelemetry *telemetry,
        uint64_t begin_ns,uint64_t end_ns) {
    if(!w || !telemetry || w->captured || !begin_ns || end_ns<begin_ns
       || telemetry->probe_count>VH_AUDOUT_PROBE_CAP)
        return -1;
    VhTailProbeContext360 temp={0};
    temp.captured=1u;
    temp.tail_begin_ns=begin_ns;
    temp.tail_end_ns=end_ns;
    temp.normal_submit_attempts=telemetry->attempts;
    temp.probe_dropped=telemetry->probe_dropped;
    /* Snap the most recent RETAINED, chronologically coherent probe.
     * A zero queue count is NOT meaningful when queue_status was 0.
     * An old retained probe may be VERY stale after the fixed cap.
     */
    for(unsigned i=telemetry->probe_count;i>0;i--) {
        const VhAudoutProbeSample *p=&telemetry->probe[i-1u];
        if((p->queue_status!=0 && p->queue_status!=1)
           || !p->attempt || p->attempt>telemetry->attempts
           || !p->submit_begin_ns || p->submit_begin_ns>begin_ns)
            continue;
        temp.last_probe_available=1u;
        temp.last_probe_queue_status=(unsigned)p->queue_status;
        temp.last_probe_queue_count=p->queue_status==1 ? p->queue_count:0u;
        temp.last_probe_attempt=p->attempt;
        temp.last_probe_age_ns=begin_ns-p->submit_begin_ns;
        break;
    }
    *w=temp;
    return 0;
}

/* Exactly 12 numerical rows after scope,value, emitted only after join.
 * A missing tail/probe is explicit; never synthesize a shutdown queue.
 */
static inline int vh_tail360_write_csv(
        const VhTailProbeContext360 *w,
        const VhAudioExitTailReason *reason,FILE *stream) {
    if(!w || !reason || !stream) return -1;
    const unsigned code=vh_audio_tail_reason_read(reason);
    if(code>VH_TAIL_RETURN_CONFIRMED || w->captured>1u
       || w->last_probe_available>1u
       || (w->captured!=(unsigned)(code!=VH_TAIL_NOT_ATTEMPTED))
       || (w->captured &&
           (!w->tail_begin_ns || w->tail_end_ns<w->tail_begin_ns))
       || (!w->captured &&
           (w->tail_begin_ns || w->tail_end_ns || w->normal_submit_attempts
            || w->last_probe_available || w->probe_dropped))
       || (w->last_probe_available &&
           (!w->captured || !w->last_probe_attempt
             || w->last_probe_attempt>w->normal_submit_attempts
             || w->last_probe_queue_status>1u))
       || (!w->last_probe_available &&
           (w->last_probe_attempt || w->last_probe_age_ns
             || w->last_probe_queue_status || w->last_probe_queue_count))
       || (w->last_probe_available && !w->last_probe_queue_status
           && w->last_probe_queue_count))
        return -1;
    if(fprintf(stream,
        "scope,value\n"
        "software_exit_probe_context_only,1\n"
        "tail_observed,%u\n"
        "tail_begin_guest_ns,%llu\n"
        "tail_end_guest_ns,%llu\n"
        "tail_elapsed_ns,%llu\n"
        "normal_submit_attempts_at_tail,%llu\n"
        "last_pre_submit_probe_observed,%u\n"
        "last_pre_submit_probe_attempt,%llu\n"
        "last_pre_submit_probe_queue_status,%u\n"
        "last_pre_submit_probe_queue_count,%u\n"
        "last_pre_submit_probe_age_ns,%llu\n"
        "last_pre_submit_probe_dropped_count,%llu\n"
        "stage351_tail_reason_code,%u\n",
        w->captured,(unsigned long long)w->tail_begin_ns,
        (unsigned long long)w->tail_end_ns,
        (unsigned long long)(w->tail_end_ns-w->tail_begin_ns),
        (unsigned long long)w->normal_submit_attempts,
        w->last_probe_available,
        (unsigned long long)w->last_probe_attempt,
        w->last_probe_queue_status,w->last_probe_queue_count,
        (unsigned long long)w->last_probe_age_ns,
        (unsigned long long)w->probe_dropped,code)<0)
        return -1;
    return 13;
}
#endif
