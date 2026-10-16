/* 100000-snapshot host stress for bounded on-console audio CSV journal.
 * Synthetic data only: never reads copyrighted files or PCM audio.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vh_audio_diag_journal.h"

static VhAudioDiagJournal log_state;

static void test_event_selection(void) {
    VhAudioDiagnostics s={.status=1};
    vh_audio_diag_journal_reset(&log_state);
    assert(vh_audio_diag_journal_sample(NULL,0,&s)==-1);
    assert(vh_audio_diag_journal_sample(&log_state,0,NULL)==-1);
    assert(vh_audio_diag_journal_sample(&log_state,0,&s)==1);
    assert(log_state.entries[0].event==VH_AUDIO_DIAG_EVENT_START);
    assert(vh_audio_diag_journal_sample(&log_state,4999,&s)==0);
    assert(vh_audio_diag_journal_sample(&log_state,5000,&s)==1);
    assert(log_state.entries[1].event==VH_AUDIO_DIAG_EVENT_PERIODIC);
    s.resume_events=1u;
    assert(vh_audio_diag_journal_sample(&log_state,5001,&s)==1);
    assert(log_state.entries[2].event==VH_AUDIO_DIAG_EVENT_RESUME);
    s.confirmed_resumes=1u;
    assert(vh_audio_diag_journal_sample(&log_state,5002,&s)==1);
    assert(log_state.entries[3].event==VH_AUDIO_DIAG_EVENT_RESUME);
    s.submit_failures=1u;
    assert(vh_audio_diag_journal_sample(&log_state,5003,&s)==1);
    assert(log_state.entries[4].event==VH_AUDIO_DIAG_EVENT_ERROR);
    s.status=2;
    assert(vh_audio_diag_journal_sample(&log_state,5004,&s)==1);
    assert(log_state.entries[5].event==VH_AUDIO_DIAG_EVENT_STATE);
    s.status=-8;
    assert(vh_audio_diag_journal_sample(&log_state,5005,&s)==1);
    assert(log_state.entries[6].event==VH_AUDIO_DIAG_EVENT_ERROR);
    assert(vh_audio_diag_journal_sample(&log_state,4,&s)==1);
    assert(log_state.entries[7].event==VH_AUDIO_DIAG_EVENT_CLOCK);
    assert(vh_audio_diag_journal_finish(&log_state,5,&s)==1);
    assert(log_state.entries[8].event==VH_AUDIO_DIAG_EVENT_EXIT);
    assert(log_state.count==9u && log_state.total==9u);
}

static void test_long_session_rollover_and_csv(void) {
    vh_audio_diag_journal_reset(&log_state);
    VhAudioDiagnostics s={.status=1};
    enum { ITERATIONS=100000 };
    for(unsigned i=0;i<ITERATIONS;i++) {
        /* One snapshot attempt every 20 ms for 33 simulated minutes.
         * Periodic sampling is throttled, but intermittent device
         * recovery events are recorded immediately. */
        s.pages_submitted=i;
        s.frames_submitted=(uint64_t)i*557u;
        if(i && i%1024u==0u) {
            ++s.resume_events;
            ++s.confirmed_resumes;
            s.last_confirmed_us=12000u+i;
            if(s.last_confirmed_us>s.worst_confirmed_us)
                s.worst_confirmed_us=s.last_confirmed_us;
        }
        if(i && i%997u==0u) {
            ++s.submit_failures;
            ++s.restart_attempts;
            ++s.recoveries;
        }
        int rc=vh_audio_diag_journal_sample(
            &log_state,(uint64_t)i*20u,&s);
        assert(rc==0 || rc==1);
    }
    assert(log_state.count==VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    assert(log_state.total>VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    const uint64_t earliest=log_state.entries[log_state.head].elapsed_ms;
    const uint32_t last=(log_state.head+VH_AUDIO_DIAG_JOURNAL_CAPACITY-1u)
                         %VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    assert(earliest<log_state.entries[last].elapsed_ms);
    assert(log_state.entries[last].snapshot.pages_submitted<=ITERATIONS-1u);
    const uint64_t total_before=log_state.total;
    assert(vh_audio_diag_journal_finish(
        &log_state,(uint64_t)ITERATIONS*20u,&s)==1);
    assert(log_state.total==total_before+1u);
    assert(log_state.count==VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    const uint32_t after=(log_state.head+VH_AUDIO_DIAG_JOURNAL_CAPACITY-1u)
                         %VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    assert(log_state.entries[after].event==VH_AUDIO_DIAG_EVENT_EXIT);

    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_diag_journal_write_csv(NULL,f)==-1);
    assert(vh_audio_diag_journal_write_csv(&log_state,NULL)==-1);
    assert(vh_audio_diag_journal_write_csv(&log_state,f)==
           VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    rewind(f);
    char line[1024];
    assert(fgets(line,sizeof line,f));
    assert(!strncmp(line,"elapsed_ms,event,status,home_resumes,",
                    strlen("elapsed_ms,event,status,home_resumes,")));
    assert(fgets(line,sizeof line,f));
    assert(strstr(line,",START,")!=NULL);
    assert(!strncmp(line,"0,START,",8));
    assert(fgets(line,sizeof line,f));
    assert(strstr(line,",GAP,")!=NULL);
    const unsigned long long gap_ms=strtoull(line,NULL,10);
    assert(gap_ms>0u);
    rewind(f);
    assert(fgets(line,sizeof line,f)); /* skip header again */
    uint64_t previous=0;
    unsigned rows=0,found_exit=0;
    while(fgets(line,sizeof line,f)) {
        unsigned long long ms=0;
        char event[16]={0};
        const int count=sscanf(line,"%llu,%15[^,],",&ms,event);
        assert(count==2);
        if(rows)assert((uint64_t)ms>=previous);
        previous=(uint64_t)ms;
        if(!strcmp(event,"EXIT"))++found_exit;
        ++rows;
    }
    assert(rows==VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    assert(found_exit==1u);
    assert(previous==(uint64_t)ITERATIONS*20u);
    fclose(f);
}

/* Preserve the initial fault count even if a later 45-minute
 * flawless run flushes all incident/event rows from the bounded ring.
 * The exporter marks the missing chronology GAP, but cumulative
 * counters still expose earlier errors from the session origin.
 */
static void test_early_errors_survive_multiple_ring_rollovers(void) {
    vh_audio_diag_journal_reset(&log_state);
    VhAudioDiagnostics d={.status=1};
    assert(vh_audio_diag_journal_sample(&log_state,0,&d)==1);
    d.submit_failures=8u;
    d.resume_failures=3u;
    d.lease_mismatches=2u;
    d.pages_submitted=10u;
    assert(vh_audio_diag_journal_sample(&log_state,1,&d)==1);
    /* Fill and wrap the ring repeatedly with later clean output.
     * A periodic heartbeat provides a row every 5 seconds. */
    for(unsigned i=1;i<=1400u;i++) {
        d.pages_submitted=10u+(uint64_t)i*32u;
        d.frames_submitted=d.pages_submitted*557u;
        assert(vh_audio_diag_journal_sample(
            &log_state,(uint64_t)i*5000u+1u,&d)==1);
    }
    assert(log_state.count==VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    assert(log_state.total==1402u);
    assert(vh_audio_diag_journal_finish(
        &log_state,UINT64_C(1401)*5000u+1u,&d)==1);
    FILE *stream=tmpfile();
    assert(stream);
    assert(vh_audio_diag_journal_write_csv(&log_state,stream)==
           VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    rewind(stream);
    char line[512];
    assert(fgets(line,sizeof line,stream));
    assert(fgets(line,sizeof line,stream));
    assert(!strncmp(line,"0,START,",8));
    assert(fgets(line,sizeof line,stream));
    assert(strstr(line,",GAP,")!=NULL);
    unsigned long long ms=0,pcm_pages=0;
    unsigned pcm_fails=0, homes=0, acknowledged=0;
    int status=0;
    unsigned long long last_us=0,worst_us=0,frames=0;
    /* Explicit fields avoid GCC's suppressed-length scanf warning
     * under the production -Werror compiler flags. */
    assert(sscanf(line,"%llu,GAP,%d,%u,%u,%llu,%llu,%llu,%llu,%u,",
                  &ms,&status,&homes,&acknowledged,&last_us,&worst_us,
                  &pcm_pages,&frames,&pcm_fails)==9);
    assert(ms>500000u);
    assert(pcm_pages>40000u);
    assert(pcm_fails==8u);
    unsigned rows=2u, errors_in_recent_rows=0;
    while(fgets(line,sizeof line,stream)) {
        if(strstr(line,",ERROR,"))++errors_in_recent_rows;
        ++rows;
    }
    assert(rows==VH_AUDIO_DIAG_JOURNAL_CAPACITY);
    assert(errors_in_recent_rows==0u);
    fclose(stream);
}

/* Verify the exact bytes seen after closing/reopening a staged CSV,
 * including the header, all fields, the last newline and exact EOF.
 * These tests are independent of the exporter fault-injection mocks. */
static void test_staged_file_exact_readback(void) {
    vh_audio_diag_journal_reset(&log_state);
    VhAudioDiagnostics d={.status=1};
    assert(vh_audio_diag_journal_sample(&log_state,0,&d)==1);
    d.submit_failures=2u;
    d.pages_submitted=1000u;
    assert(vh_audio_diag_journal_sample(&log_state,5000,&d)==1);
    d.status=0;
    assert(vh_audio_diag_journal_finish(&log_state,6000,&d)==1);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_diag_journal_write_csv(&log_state,f)==3);
    assert(fflush(f)==0);
    rewind(f);
    assert(vh_audio_diag_journal_verify_csv(&log_state,f)==3);
    rewind(f);
    assert(fputc('X',f)=='X'); /* corrupt first header byte */
    assert(fflush(f)==0);
    rewind(f);
    assert(vh_audio_diag_journal_verify_csv(&log_state,f)==-1);
    assert(fclose(f)==0);

    f=tmpfile();
    assert(f);
    assert(vh_audio_diag_journal_write_csv(&log_state,f)==3);
    assert(fputs("UNEXPECTED TRAILING SD BYTES\n",f)!=EOF);
    assert(fflush(f)==0);
    rewind(f);
    assert(vh_audio_diag_journal_verify_csv(&log_state,f)==-1);
    assert(fclose(f)==0);

    f=tmpfile();
    assert(f);
    assert(fputs("elapsed_ms,event,status",f)!=EOF);
    assert(fflush(f)==0);
    rewind(f);
    assert(vh_audio_diag_journal_verify_csv(&log_state,f)==-1);
    assert(fclose(f)==0);
    assert(vh_audio_diag_journal_verify_csv(NULL,NULL)==-1);
}

static void test_invalid_journal_and_counter_saturation(void) {
    vh_audio_diag_journal_reset(&log_state);
    VhAudioDiagnostics s={.status=1};
    assert(vh_audio_diag_journal_sample(&log_state,0,&s)==1);
    log_state.total=UINT64_MAX;
    assert(vh_audio_diag_journal_sample(&log_state,6000,&s)==1);
    assert(log_state.total==UINT64_MAX);
    log_state.count=VH_AUDIO_DIAG_JOURNAL_CAPACITY+1u;
    assert(vh_audio_diag_journal_sample(&log_state,7000,&s)==-1);
    assert(vh_audio_diag_journal_finish(&log_state,7000,&s)==-1);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_diag_journal_write_csv(&log_state,f)==-1);
    fclose(f);
    vh_audio_diag_journal_reset(&log_state);
    assert(log_state.count==0 && log_state.total==0 &&
           log_state.head==0);
}

int main(void) {
    test_event_selection();
    test_long_session_rollover_and_csv();
    test_early_errors_survive_multiple_ring_rollovers();
    test_staged_file_exact_readback();
    test_invalid_journal_and_counter_saturation();
    puts("33-minute audio journal: bounded 128 rows, chronological "
         "CSV and 100000 snapshot attempts PASS");
    return 0;
}
