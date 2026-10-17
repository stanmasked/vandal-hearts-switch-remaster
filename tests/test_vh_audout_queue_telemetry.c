#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audout_queue_telemetry.h"

int main(void) {
    VhAudoutQueueTelemetry t;
    vh_audout_queue_reset(&t);
    assert(vh_audout_queue_probe_due(&t));
    const uint64_t base=UINT64_C(10000000000);
    for(unsigned i=0;i<300;i++) {
        const uint64_t start=base+(uint64_t)(i/100)*UINT64_C(1000000000)+i*1000u;
        const int probe=vh_audout_queue_probe_due(&t);
        vh_audout_queue_record(&t,start,start+UINT64_C(24000000),
                               i!=123, probe ? 1:-1, i%3);
    }
    assert(t.attempts==300 && t.returns==299 && t.failures==1);
    assert(t.queue_ok==19 && t.queue_errors==0);
    assert(t.queue_min==0 && t.queue_max==2);
    assert(t.last_second==2 && t.max_call_ns==UINT64_C(24000000));
    assert(t.bucket[1].failures==1 && t.bucket[0].attempts==100);
    vh_audout_queue_record(&t,base+UINT64_C(129000000000),
        base+UINT64_C(129001000000),0,0,0);
    assert(t.attempts==301 && t.failures==2 && t.queue_errors==1);
    assert(t.overwritten_windows==1 && t.bucket[1].second==129);
    assert(t.bucket[1].attempts==1 && t.bucket[1].queue_errors==1);
    const uint64_t old=t.attempts;
    vh_audout_queue_record(&t,base+10u,base+9u,1,1,10);
    assert(t.clock_errors==1 && t.attempts==old);
    assert(vh_audout_queue_probe_due(NULL)==0);
    vh_audout_queue_record(NULL,1,2,1,1,0);
    FILE *f=tmpfile();
    assert(f);
    const int rows=vh_audout_queue_write_csv(&t,f);
    assert(rows==2); /* old second 0 evicted; second 2, 129 retained */
    assert(!fflush(f) && !fseek(f,0,SEEK_SET));
    char line[400];
    assert(fgets(line,sizeof line,f) && strstr(line,"overwritten_windows"));
    assert(fgets(line,sizeof line,f) && strstr(line,"TOTAL,-1,301,299,2"));
    assert(fgets(line,sizeof line,f) && strstr(line,"SECOND,2,100"));
    assert(fgets(line,sizeof line,f) && strstr(line,"SECOND,129,1"));
    assert(fgetc(f)==EOF && !ferror(f));
    fclose(f);
    /* Stage 272: test exact 25/40/50 ms boundaries in nanoseconds.
     * The original queue CSV must still use its unchanged schema. */
    VhAudoutQueueTelemetry q;
    vh_audout_queue_reset(&q);
    const uint64_t b0=UINT64_C(2000000000);
    const uint64_t durations[]={
        UINT64_C(24999999), UINT64_C(25000000),
        UINT64_C(40000000), UINT64_C(50000000)
    };
    for(unsigned i=0;i<4;i++) {
        const uint64_t begin=b0+(uint64_t)i*UINT64_C(100000000);
        vh_audout_queue_record(&q,begin,begin+durations[i],1,-1,0);
    }
    assert(q.latency_bins[0]==1 && q.latency_bins[1]==1
        && q.latency_bins[2]==1 && q.latency_bins[3]==1);
    assert(q.bucket[0].latency_bins[0]==1 &&
        q.bucket[0].latency_bins[3]==1 && q.attempts==4);
    f=tmpfile();
    assert(f && vh_audout_latency_write_csv(&q,f)==1);
    assert(!fflush(f) && !fseek(f,0,SEEK_SET));
    assert(fgets(line,sizeof line,f) &&
        strstr(line,"lt25ms,from25to40ms,from40to50ms,ge50ms"));
    assert(fgets(line,sizeof line,f) &&
        strstr(line,"TOTAL,-1,4,1,1,1,1,0,50000,0,0"));
    assert(fgets(line,sizeof line,f) &&
        strstr(line,"SECOND,0,4,1,1,1,1,0,50000,0,0"));
    assert(fgetc(f)==EOF && !ferror(f));
    rewind(f);
    assert(vh_audout_latency_verify_csv(&q,f)==0);
    assert(!fseek(f,0,SEEK_END) && fputc('X',f)!=EOF);
    rewind(f);
    assert(vh_audout_latency_verify_csv(&q,f)==-1);
    fclose(f);
    f=tmpfile();
    assert(f && vh_audout_queue_write_csv(&q,f)==1);
    rewind(f);
    assert(fgets(line,sizeof line,f) &&
        strstr(line,"queue_ok,queue_errors,queue_min,queue_max"));
    rewind(f);
    assert(vh_audout_queue_verify_csv(&q,f)==0);
    fclose(f);
    puts("bounded audout full-session telemetry PASS");
    return 0;
}
