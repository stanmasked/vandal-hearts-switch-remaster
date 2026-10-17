#include "vh_audout_queue_telemetry.h"
#include <limits.h>
#include <string.h>

void vh_audout_queue_reset(VhAudoutQueueTelemetry *t) {
    if(t) memset(t,0,sizeof *t);
}
int vh_audout_queue_probe_due(const VhAudoutQueueTelemetry *t) {
    return t && t->attempts % VH_AUDOUT_QUEUE_SAMPLE_EVERY == 0;
}
void vh_audout_queue_record(VhAudoutQueueTelemetry *t,
                            uint64_t begin_ns, uint64_t end_ns,
                            int returned, int queue_status,
                            uint32_t queue_count) {
    if(!t) return;
    if(!t->attempts) t->origin_ns=begin_ns;
    /* Backwards ticks are counted, not silently turned into giant
     * unsigned durations or bucket numbers. */
    if(begin_ns<t->origin_ns || end_ns<begin_ns) {
        if(t->clock_errors<UINT64_MAX) ++t->clock_errors;
        return;
    }
    const uint64_t second=(begin_ns-t->origin_ns)/UINT64_C(1000000000);
    VhAudoutQueueBucket *b=&t->bucket[second%VH_AUDOUT_QUEUE_BUCKETS];
    if(b->valid && b->second!=second) {
        if(t->overwritten_windows<UINT64_MAX) ++t->overwritten_windows;
        memset(b,0,sizeof *b);
    }
    if(!b->valid) {b->valid=1;b->second=second;}
    t->last_second=second;
    const uint64_t duration=end_ns-begin_ns;
    ++t->attempts; ++b->attempts;
    if(returned) {++t->returns;++b->returns;}
    else {++t->failures;++b->failures;}
    if(duration>t->max_call_ns) t->max_call_ns=duration;
    if(duration>b->max_call_ns) b->max_call_ns=duration;
    if(queue_status==1) {
        if(!t->queue_ok || queue_count<t->queue_min)
            t->queue_min=queue_count;
        if(!t->queue_ok || queue_count>t->queue_max)
            t->queue_max=queue_count;
        if(!b->queue_ok || queue_count<b->queue_min)
            b->queue_min=queue_count;
        if(!b->queue_ok || queue_count>b->queue_max)
            b->queue_max=queue_count;
        ++t->queue_ok; ++b->queue_ok;
    } else if(queue_status==0) {
        ++t->queue_errors; ++b->queue_errors;
    }
}

int vh_audout_queue_write_csv(const VhAudoutQueueTelemetry *t,FILE *out) {
    if(!t || !out) return -1;
    if(fputs("scope,second,attempts,returns,failures,max_call_us,"
             "queue_ok,queue_errors,queue_min,queue_max,"
             "overwritten_windows,clock_errors\n",out)==EOF) return -1;
    if(fprintf(out,"TOTAL,-1,%llu,%llu,%llu,%llu,%llu,%llu,%u,%u,%llu,%llu\n",
            (unsigned long long)t->attempts,
            (unsigned long long)t->returns,
            (unsigned long long)t->failures,
            (unsigned long long)(t->max_call_ns/UINT64_C(1000)),
            (unsigned long long)t->queue_ok,
            (unsigned long long)t->queue_errors,
            t->queue_min,t->queue_max,
            (unsigned long long)t->overwritten_windows,
            (unsigned long long)t->clock_errors)<0) return -1;
    if(!t->attempts) return ferror(out) ? -1 : 0;
    const uint64_t first=t->last_second >= VH_AUDOUT_QUEUE_BUCKETS-1u
        ? t->last_second-(VH_AUDOUT_QUEUE_BUCKETS-1u):0u;
    int rows=0;
    for(uint64_t second=first;second<=t->last_second;second++) {
        const VhAudoutQueueBucket *b=
            &t->bucket[second%VH_AUDOUT_QUEUE_BUCKETS];
        if(!b->valid || b->second!=second) continue;
        if(fprintf(out,
             "SECOND,%llu,%llu,%llu,%llu,%llu,%u,%u,%u,%u,0,0\n",
             (unsigned long long)second,
             (unsigned long long)b->attempts,
             (unsigned long long)b->returns,
             (unsigned long long)b->failures,
             (unsigned long long)(b->max_call_ns/UINT64_C(1000)),
             b->queue_ok,b->queue_errors,b->queue_min,b->queue_max)<0)
            return -1;
        ++rows;
    }
    return ferror(out) ? -1 : rows;
}
