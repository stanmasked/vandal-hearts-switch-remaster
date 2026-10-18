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
    /* Stage 273 clock anchor has the same absolute guest nanoseconds
     * used at the first audout call; changing a byte fails reread. */
    f=tmpfile();
    assert(f && vh_audout_clock_write_csv(&q,f)==1);
    rewind(f);
    assert(fgets(line,sizeof line,f) &&
        strstr(line,"schema,origin_ns,attempts,last_second,clock_errors"));
    assert(fgets(line,sizeof line,f) &&
        strstr(line,"vh-audout-guest-clock-origin/v1,2000000000,4,0,0"));
    rewind(f);
    assert(vh_audout_clock_verify_csv(&q,f)==0);
    assert(!fseek(f,0,SEEK_END) && fputc('X',f)!=EOF);
    rewind(f);
    assert(vh_audout_clock_verify_csv(&q,f)==-1);
    fclose(f);
    /* Stage289: pre-submit service probes use the exact timestamp
     * already taken at the audout submit boundary. No extra query. */
    VhAudoutQueueTelemetry probes;
    vh_audout_queue_reset(&probes);
    const uint64_t pc=UINT64_C(3000000000);
    for(unsigned i=0;i<34;i++) {
        const int due=vh_audout_queue_probe_due(&probes);
        const uint64_t begin=pc+(uint64_t)i*UINT64_C(20000000);
        vh_audout_queue_record(&probes,begin,begin+UINT64_C(1000000),
                              1,due ? (i==16 ? 0 : 1) : -1,
                              due && i!=16 ? i%4 : 0);
    }
    assert(probes.probe_count==3 && probes.probe_dropped==0);
    assert(probes.probe[0].attempt==1u &&
           probes.probe[1].attempt==17u &&
           probes.probe[2].attempt==33u);
    assert(probes.probe[0].submit_begin_ns==pc);
    assert(probes.probe[1].queue_count==0 &&
           probes.probe[1].queue_status==0);
    assert(probes.queue_ok==2 && probes.queue_errors==1);
    f=tmpfile();
    assert(f && vh_audout_probe_write_csv(&probes,f)==3);
    rewind(f);
    assert(vh_audout_probe_verify_csv(&probes,f)==0);
    assert(!fseek(f,0,SEEK_END) && fputc('X',f)!=EOF);
    rewind(f);
    assert(vh_audout_probe_verify_csv(&probes,f)==-1);
    fclose(f);
    /* More than 256 probes: fail closed in the Python auditor and
     * never silently overwrite the first 256 measurements. */
    VhAudoutQueueTelemetry probe_overflow;
    vh_audout_queue_reset(&probe_overflow);
    for(unsigned i=0;i<VH_AUDOUT_PROBE_CAP*16u+1u;i++) {
        const int due=vh_audout_queue_probe_due(&probe_overflow);
        const uint64_t begin=pc+(uint64_t)i*UINT64_C(1000000);
        vh_audout_queue_record(&probe_overflow,begin,begin+UINT64_C(1000),
                              1,due ? 1:-1,0);
    }
    assert(probe_overflow.probe_count==VH_AUDOUT_PROBE_CAP &&
           probe_overflow.probe_dropped==1 &&
           probe_overflow.probe[0].attempt==1 &&
           probe_overflow.probe[VH_AUDOUT_PROBE_CAP-1].attempt==
                1u+16u*(VH_AUDOUT_PROBE_CAP-1u));
    /* Stage294: the alternative phase is programmed before the first
     * attempt. The query cadence stays exactly 1 per 16 attempts. */
    VhAudoutQueueTelemetry phased;
    vh_audout_queue_reset(&phased);
    assert(phased.probe_phase==0u);
    assert(vh_audout_queue_set_probe_phase(NULL,8u)==-1);
    assert(vh_audout_queue_set_probe_phase(&phased,16u)==-1);
    assert(vh_audout_queue_set_probe_phase(&phased,8u)==0);
    assert(phased.probe_phase==8u);
    for(unsigned i=0;i<36;i++) {
        const int due=vh_audout_queue_probe_due(&phased);
        assert(due==(i==8 || i==24));
        vh_audout_queue_record(&phased,pc+(uint64_t)i*UINT64_C(20000000),
            pc+(uint64_t)i*UINT64_C(20000000)+UINT64_C(1000000),
            1,due ? 1:-1,due ? 2u:0u);
    }
    assert(phased.probe_count==2u && phased.queue_ok==2u);
    assert(phased.probe[0].attempt==9u && phased.probe[1].attempt==25u);
    assert(vh_audout_queue_set_probe_phase(&phased,0u)==-1);
    f=tmpfile();
    assert(f && vh_audout_probe_write_csv(&phased,f)==2);
    rewind(f);
    assert(vh_audout_probe_verify_csv(&phased,f)==0);
    fclose(f);
    vh_audout_queue_reset(&phased);
    assert(phased.probe_phase==0u && vh_audout_queue_probe_due(&phased));
    VhAudoutQueueTelemetry empty;
    vh_audout_queue_reset(&empty);
    f=tmpfile();
    assert(f && vh_audout_clock_write_csv(&empty,f)==-1);
    fclose(f);
    assert(q.slow_count==2 && q.slow_dropped==0);
    assert(q.slow[0].attempt==3 && q.slow[1].attempt==4);
    assert(q.slow[0].begin_ns==b0+UINT64_C(200000000));
    assert(q.slow[0].end_ns-q.slow[0].begin_ns==VH_AUDOUT_LT40_NS);
    assert(q.slow[1].end_ns-q.slow[1].begin_ns==VH_AUDOUT_LT50_NS);
    f=tmpfile();
    assert(f && vh_audout_slow_write_csv(&q,f)==2);
    rewind(f);
    assert(fgets(line,sizeof line,f) && strstr(line,"total_slow_calls"));
    assert(fgets(line,sizeof line,f) && strstr(line,"TOTAL,-1,0,0,0,0,0,2,0"));
    rewind(f);
    assert(vh_audout_slow_verify_csv(&q,f)==0);
    assert(!fseek(f,0,SEEK_END) && fputc('X',f)!=EOF);
    rewind(f);
    assert(vh_audout_slow_verify_csv(&q,f)==-1);
    fclose(f);
    VhAudoutQueueTelemetry overflow;
    vh_audout_queue_reset(&overflow);
    for(unsigned i=0;i<129;i++) {
        const uint64_t start=b0+(uint64_t)i*UINT64_C(1000000);
        vh_audout_queue_record(&overflow,start,start+VH_AUDOUT_LT50_NS,
                               1,-1,0);
    }
    assert(overflow.slow_count==VH_AUDOUT_SLOW_CALL_CAP);
    assert(overflow.slow_dropped==1);
    assert(overflow.latency_bins[3]==129 && overflow.attempts==129);
    f=tmpfile();
    assert(f && vh_audout_slow_write_csv(&overflow,f)==128);
    rewind(f);
    assert(vh_audout_slow_verify_csv(&overflow,f)==0);
    fclose(f);
    puts("bounded audout full-session telemetry PASS");
    return 0;
}
