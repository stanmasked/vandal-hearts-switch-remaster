#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "vh_audout_queue_export.h"

int main(void) {
    char dir[]="/tmp/vh-audout-telemetry-XXXXXX";
    assert(mkdtemp(dir));
    VhAudoutQueueTelemetry t={0};
    vh_audout_queue_record(&t,100,26000100,1,1,0);
    vh_audout_queue_record(&t,1000000200,1025000200,0,0,0);
    char first[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP],second[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    assert(vh_audout_queue_export(&t,dir,first,sizeof first)==0);
    assert(strstr(first,"audio-audout-queue-0000.csv"));
    FILE *f=fopen(first,"rb");
    assert(f && vh_audout_queue_verify_csv(&t,f)==0);
    fclose(f);
    assert(vh_audout_queue_export(&t,dir,second,sizeof second)==0);
    assert(strcmp(first,second)!=0);
    assert(strstr(second,"audio-audout-queue-0001.csv"));
    char temp[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    snprintf(temp,sizeof temp,"%s/audio-audout-queue-0002.tmp",dir);
    f=fopen(temp,"wb");
    assert(f && fputs("unfinished",f)>0 && fclose(f)==0);
    assert(vh_audout_queue_export(&t,dir,second,sizeof second)==0);
    assert(strstr(second,"audio-audout-queue-0003.csv"));
    f=fopen(first,"ab");
    assert(f && fputc('X',f)!=EOF && fclose(f)==0);
    f=fopen(first,"rb");
    assert(f && vh_audout_queue_verify_csv(&t,f)==-1);
    fclose(f);
    assert(vh_audout_queue_export(&t,dir,second,2)==VH_AUDOUT_QUEUE_EXPORT_PATH);
    /* Separate latency CSV must never claim/replace queue series. */
    char latency[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    assert(vh_audout_latency_export(&t,dir,latency,sizeof latency)==0);
    assert(strstr(latency,"audio-audout-latency-0000.csv"));
    f=fopen(latency,"rb");
    assert(f && vh_audout_latency_verify_csv(&t,f)==0);
    fclose(f);
    assert(vh_audout_latency_export(&t,dir,second,sizeof second)==0);
    assert(strstr(second,"audio-audout-latency-0001.csv"));
    assert(unlink(second)==0);
    assert(unlink(latency)==0);
    char clock[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    assert(vh_audout_clock_export(&t,dir,clock,sizeof clock)==0);
    assert(strstr(clock,"audio-audout-clock-0000.csv"));
    f=fopen(clock,"rb");
    assert(f && vh_audout_clock_verify_csv(&t,f)==0);
    fclose(f);
    assert(vh_audout_clock_export(&t,dir,second,sizeof second)==0);
    assert(strstr(second,"audio-audout-clock-0001.csv"));
    assert(unlink(second)==0 && unlink(clock)==0);
    char slow[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    assert(vh_audout_slow_export(&t,dir,slow,sizeof slow)==0);
    assert(strstr(slow,"audio-audout-slow-0000.csv"));
    f=fopen(slow,"rb");
    assert(f && vh_audout_slow_verify_csv(&t,f)==0);
    fclose(f);
    assert(vh_audout_slow_export(&t,dir,second,sizeof second)==0);
    assert(strstr(second,"audio-audout-slow-0001.csv"));
    assert(unlink(second)==0 && unlink(slow)==0);
    /* Separate, exclusive, byte-readback checked Stage289 probe CSV.
     * Never overwrite the prior queue, clock, latency or slow files. */
    char probe[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    assert(vh_audout_probe_export(&t,dir,probe,sizeof probe)==0);
    assert(strstr(probe,"audio-audout-probe-0000.csv"));
    f=fopen(probe,"rb");
    assert(f && vh_audout_probe_verify_csv(&t,f)==0);
    fclose(f);
    assert(vh_audout_probe_export(&t,dir,second,sizeof second)==0);
    assert(strstr(second,"audio-audout-probe-0001.csv"));
    assert(unlink(second)==0 && unlink(probe)==0);
    assert(unlink(first)==0);
    char path[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    snprintf(path,sizeof path,"%s/audio-audout-queue-0001.csv",dir);
    assert(unlink(path)==0);
    snprintf(path,sizeof path,"%s/audio-audout-queue-0003.csv",dir);
    assert(unlink(path)==0);
    assert(unlink(temp)==0 && rmdir(dir)==0);
    puts("audout telemetry exclusive staged SD/readback export PASS");
    return 0;
}
