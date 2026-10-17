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
    const unsigned band=duration<VH_AUDOUT_LT25_NS ? 0u
        : duration<VH_AUDOUT_LT40_NS ? 1u
        : duration<VH_AUDOUT_LT50_NS ? 2u : 3u;
    ++t->latency_bins[band];
    ++b->latency_bins[band];
    if(duration>=VH_AUDOUT_LT40_NS) {
        if(t->slow_count<VH_AUDOUT_SLOW_CALL_CAP) {
            VhAudoutSlowCall *entry=&t->slow[t->slow_count++];
            entry->attempt=t->attempts+1u;
            entry->begin_ns=begin_ns;
            entry->end_ns=end_ns;
            entry->returned=returned!=0;
        } else if(t->slow_dropped<UINT64_MAX) ++t->slow_dropped;
    }
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


/* The verifier independently formats each expected CSV row and rejects
 * truncation, appended bytes and reordered windows. Called after the
 * writer has been closed, never from the audio worker. */
int vh_audout_queue_verify_csv(const VhAudoutQueueTelemetry *t,FILE *in) {
    if(!t || !in) return -1;
    char got[400],want[400];
    static const char header[]=
        "scope,second,attempts,returns,failures,max_call_us,"
        "queue_ok,queue_errors,queue_min,queue_max,"
        "overwritten_windows,clock_errors\n";
    if(!fgets(got,sizeof got,in) || strcmp(got,header)!=0) return -1;
    int n=snprintf(want,sizeof want,
        "TOTAL,-1,%llu,%llu,%llu,%llu,%llu,%llu,%u,%u,%llu,%llu\n",
        (unsigned long long)t->attempts,
        (unsigned long long)t->returns,
        (unsigned long long)t->failures,
        (unsigned long long)(t->max_call_ns/UINT64_C(1000)),
        (unsigned long long)t->queue_ok,
        (unsigned long long)t->queue_errors,
        t->queue_min,t->queue_max,
        (unsigned long long)t->overwritten_windows,
        (unsigned long long)t->clock_errors);
    if(n<=0 || (size_t)n>=sizeof want ||
       !fgets(got,sizeof got,in) || strcmp(got,want)!=0) return -1;
    if(t->attempts) {
        const uint64_t first=t->last_second>=VH_AUDOUT_QUEUE_BUCKETS-1u
            ? t->last_second-(VH_AUDOUT_QUEUE_BUCKETS-1u):0u;
        for(uint64_t second=first;second<=t->last_second;second++) {
            const VhAudoutQueueBucket *b=
                &t->bucket[second%VH_AUDOUT_QUEUE_BUCKETS];
            if(!b->valid || b->second!=second) continue;
            n=snprintf(want,sizeof want,
                "SECOND,%llu,%llu,%llu,%llu,%llu,%u,%u,%u,%u,0,0\n",
                (unsigned long long)second,
                (unsigned long long)b->attempts,
                (unsigned long long)b->returns,
                (unsigned long long)b->failures,
                (unsigned long long)(b->max_call_ns/UINT64_C(1000)),
                b->queue_ok,b->queue_errors,b->queue_min,b->queue_max);
            if(n<=0 || (size_t)n>=sizeof want ||
               !fgets(got,sizeof got,in) || strcmp(got,want)!=0)
                return -1;
        }
    }
    return fgetc(in)==EOF && !ferror(in) ? 0 : -1;
}


/* Stage 272 emits a SEPARATE versioned CSV. The Stage-269 queue CSV
 * writer/verifier above remain byte-for-byte unchanged. All work occurs
 * AFTER the worker has joined, never inside audoutPlayBuffer. */
static const char LATENCY_HEADER[]=
    "scope,second,attempts,lt25ms,from25to40ms,from40to50ms,"
    "ge50ms,failures,max_call_us,overwritten_windows,clock_errors\n";

static int latency_row(char *dst,size_t cap,const char *scope,
                       uint64_t second,uint64_t attempts,
                       const uint64_t bins[VH_AUDOUT_LATENCY_BANDS],
                       uint64_t failures,uint64_t max_ns,
                       uint64_t overwritten,uint64_t clock_errors) {
    const int n=snprintf(dst,cap,
        "%s,%s%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu\n",
        scope,scope[0]=='T' ? "-" : "",
        (unsigned long long)second,
        (unsigned long long)attempts,
        (unsigned long long)bins[0],
        (unsigned long long)bins[1],
        (unsigned long long)bins[2],
        (unsigned long long)bins[3],
        (unsigned long long)failures,
        (unsigned long long)(max_ns/UINT64_C(1000)),
        (unsigned long long)overwritten,
        (unsigned long long)clock_errors);
    return n>0 && (size_t)n<cap ? n : -1;
}

int vh_audout_latency_write_csv(const VhAudoutQueueTelemetry *t,FILE *out) {
    if(!t || !out || fputs(LATENCY_HEADER,out)==EOF) return -1;
    char line[400];
    if(latency_row(line,sizeof line,"TOTAL",1,t->attempts,
        t->latency_bins,t->failures,t->max_call_ns,
        t->overwritten_windows,t->clock_errors)<0 ||
       fputs(line,out)==EOF) return -1;
    if(!t->attempts) return ferror(out) ? -1 : 0;
    const uint64_t first=t->last_second>=VH_AUDOUT_QUEUE_BUCKETS-1u
        ? t->last_second-(VH_AUDOUT_QUEUE_BUCKETS-1u):0u;
    int rows=0;
    for(uint64_t second=first;second<=t->last_second;second++) {
        const VhAudoutQueueBucket *b=&t->bucket[second%VH_AUDOUT_QUEUE_BUCKETS];
        if(!b->valid || b->second!=second) continue;
        if(latency_row(line,sizeof line,"SECOND",second,b->attempts,
            b->latency_bins,b->failures,b->max_call_ns,0,0)<0 ||
           fputs(line,out)==EOF) return -1;
        ++rows;
    }
    return ferror(out) ? -1 : rows;
}

int vh_audout_latency_verify_csv(const VhAudoutQueueTelemetry *t,FILE *in) {
    if(!t || !in) return -1;
    char actual[400],expected[400];
    if(!fgets(actual,sizeof actual,in) ||
       strcmp(actual,LATENCY_HEADER)!=0) return -1;
    if(latency_row(expected,sizeof expected,"TOTAL",1,t->attempts,
        t->latency_bins,t->failures,t->max_call_ns,
        t->overwritten_windows,t->clock_errors)<0 ||
       !fgets(actual,sizeof actual,in) || strcmp(actual,expected)!=0)
        return -1;
    if(t->attempts) {
        const uint64_t first=t->last_second>=VH_AUDOUT_QUEUE_BUCKETS-1u
            ? t->last_second-(VH_AUDOUT_QUEUE_BUCKETS-1u):0u;
        for(uint64_t second=first;second<=t->last_second;second++) {
            const VhAudoutQueueBucket *b=&t->bucket[second%VH_AUDOUT_QUEUE_BUCKETS];
            if(!b->valid || b->second!=second) continue;
            if(latency_row(expected,sizeof expected,"SECOND",second,
                b->attempts,b->latency_bins,b->failures,b->max_call_ns,0,0)<0 ||
               !fgets(actual,sizeof actual,in) || strcmp(actual,expected)!=0)
                return -1;
        }
    }
    return fgetc(in)==EOF && !ferror(in) ? 0 : -1;
}


/* Absolute guest clock anchor. Same armTicksToNs timestamp source as
 * vh_audio_scene_trace.c events. Writer runs after audio owner join.
 * Separate from both original queue and duration-band CSV schemas. */
static int clock_row(char *dst,size_t cap,const VhAudoutQueueTelemetry *t) {
    if(!t || !t->attempts || !t->origin_ns || !dst || !cap) return -1;
    const int n=snprintf(dst,cap,
        "vh-audout-guest-clock-origin/v1,%llu,%llu,%llu,%llu\n",
        (unsigned long long)t->origin_ns,
        (unsigned long long)t->attempts,
        (unsigned long long)t->last_second,
        (unsigned long long)t->clock_errors);
    return n>0 && (size_t)n<cap ? n : -1;
}
static const char CLOCK_HEADER[]=
    "schema,origin_ns,attempts,last_second,clock_errors\n";

int vh_audout_clock_write_csv(const VhAudoutQueueTelemetry *t,FILE *out) {
    char line[200];
    if(!out || clock_row(line,sizeof line,t)<0 ||
       fputs(CLOCK_HEADER,out)==EOF || fputs(line,out)==EOF) return -1;
    return ferror(out) ? -1 : 1;
}
int vh_audout_clock_verify_csv(const VhAudoutQueueTelemetry *t,FILE *in) {
    char line[200],expected[200];
    if(!in || clock_row(expected,sizeof expected,t)<0) return -1;
    if(!fgets(line,sizeof line,in) || strcmp(line,CLOCK_HEADER)!=0 ||
       !fgets(line,sizeof line,in) || strcmp(line,expected)!=0) return -1;
    return fgetc(in)==EOF && !ferror(in) ? 0 : -1;
}


/* Stage274: original queue/latency/clock formats stay byte-for-byte
 * unchanged; exact slow-call timestamps are a fourth separate CSV. */
static const char SLOW_HEADER[]=
    "scope,index,attempt,begin_ns,end_ns,duration_ns,returned,"
    "total_slow_calls,dropped_slow_calls\n";

static int slow_summary(char *dst,size_t cap,const VhAudoutQueueTelemetry *t) {
    const uint64_t total=t->latency_bins[2]+t->latency_bins[3];
    const int n=snprintf(dst,cap,"TOTAL,-1,0,0,0,0,0,%llu,%llu\n",
        (unsigned long long)total,(unsigned long long)t->slow_dropped);
    return n>0 && (size_t)n<cap ? n : -1;
}
static int slow_row(char *dst,size_t cap,unsigned index,
                    const VhAudoutSlowCall *entry) {
    const int n=snprintf(dst,cap,
        "CALL,%u,%llu,%llu,%llu,%llu,%u,0,0\n",index,
        (unsigned long long)entry->attempt,
        (unsigned long long)entry->begin_ns,
        (unsigned long long)entry->end_ns,
        (unsigned long long)(entry->end_ns-entry->begin_ns),
        entry->returned);
    return n>0 && (size_t)n<cap ? n : -1;
}
int vh_audout_slow_write_csv(const VhAudoutQueueTelemetry *t,FILE *out) {
    char line[240];
    if(!t || !out || slow_summary(line,sizeof line,t)<0 ||
       fputs(SLOW_HEADER,out)==EOF || fputs(line,out)==EOF) return -1;
    for(unsigned i=0;i<t->slow_count;i++) {
        if(slow_row(line,sizeof line,i,&t->slow[i])<0 ||
           fputs(line,out)==EOF) return -1;
    }
    return ferror(out) ? -1 : (int)t->slow_count;
}
int vh_audout_slow_verify_csv(const VhAudoutQueueTelemetry *t,FILE *in) {
    char got[240],want[240];
    if(!t || !in || !fgets(got,sizeof got,in) ||
       strcmp(got,SLOW_HEADER)!=0 ||
       slow_summary(want,sizeof want,t)<0 ||
       !fgets(got,sizeof got,in) || strcmp(got,want)!=0) return -1;
    for(unsigned i=0;i<t->slow_count;i++) {
        if(slow_row(want,sizeof want,i,&t->slow[i])<0 ||
           !fgets(got,sizeof got,in) || strcmp(got,want)!=0) return -1;
    }
    return fgetc(in)==EOF && !ferror(in) ? 0 : -1;
}
