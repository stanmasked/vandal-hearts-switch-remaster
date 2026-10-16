/* Stage 210: one subprocess = one game-like session, using the SAME
 * bounded journal and checked staging exporter as the Switch NRO.
 * No libnx, bank files, PCM samples or hardware are accessed.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vh_audio_diag_export.h"

static VhAudioDiagJournal journal; /* no stack growth in a running game */

static void create_session(int faulty) {
    vh_audio_diag_journal_reset(&journal);
    VhAudioDiagnostics state={.status=1};
    /* 21 retained snapshots: 2400 newly completed output pages,
     * 40 resume events, 20 individual acknowledged PCM latencies.
     * All cumulative counters originate at digital zero. */
    for(unsigned i=0;i<=20u;i++) {
        state.pages_submitted=(uint64_t)i*120u;
        state.frames_submitted=state.pages_submitted*557u;
        state.resume_events=i*2u;
        state.confirmed_resumes=i;
        state.last_confirmed_us=i ? (faulty ? 95000u : 12000u) : 0u;
        state.worst_confirmed_us=i ? state.last_confirmed_us : 0u;
        if(faulty) {
            /* Recovered errors, not a stuck device or bad speaker. */
            state.submit_failures=i/4u;
            state.restart_attempts=state.submit_failures;
            state.recoveries=state.submit_failures;
            state.resume_failures=i/10u;
            state.resume_restarts=i*2u+state.resume_failures;
            state.resume_recoveries=i*2u;
        } else {
            state.resume_restarts=i*2u;
            state.resume_recoveries=i*2u;
        }
        const uint64_t elapsed=(uint64_t)i*5000u;
        if(i==20u) {
            state.status=0;
            if(vh_audio_diag_journal_finish(&journal,elapsed,&state)!=1) abort();
        } else if(vh_audio_diag_journal_sample(&journal,elapsed,&state)!=1) {
            abort();
        }
    }
    if(journal.count!=21u || journal.total!=21u) abort();
}

int main(int argc,char **argv) {
    if(argc!=4 || strcmp(argv[1],"--directory")!=0) {
        fputs("usage: switch_audio_export_session --directory DIR "
              "clean|faulty|interrupted\n",stderr);
        return 2;
    }
    const char *dir=argv[2], *mode=argv[3];
    if(!strcmp(mode,"interrupted")) {
        /* Reproduce a sudden stop AFTER a partial write, BEFORE
         * fclose/rename: only .tmp exists. Next independent process
         * MUST safely replace this, preserving existing CSVs.
         * This is an OS-host simulation, not actual SD power loss. */
        char temp[VH_AUDIO_DIAG_EXPORT_PATH_CAP];
        const int n=snprintf(temp,sizeof temp,
                             "%s/audio-diagnostics.tmp",dir);
        if(n<=0 || (size_t)n>=sizeof temp) return 3;
        FILE *f=fopen(temp,"wb");
        if(!f) return 3;
        if(fputs("elapsed_ms,event,PARTIAL\n0,not-a-CSV\n",f)==EOF ||
           fflush(f)!=0 || fclose(f)!=0) return 3;
        printf("INTERRUPTED %s\n",temp);
        return 0;
    }
    if(strcmp(mode,"clean") && strcmp(mode,"faulty")) return 2;
    create_session(!strcmp(mode,"faulty"));
    char dest[VH_AUDIO_DIAG_EXPORT_PATH_CAP];
    const VhAudioDiagExportResult code=vh_audio_diag_export(
        &journal,dir,NULL,dest,sizeof dest);
    if(code!=VH_AUDIO_EXPORT_OK) {
        fprintf(stderr,"export status %d\n",(int)code);
        return 4;
    }
    puts(dest);
    return 0;
}
