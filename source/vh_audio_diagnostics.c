#include "vh_audio_diagnostics.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>

int vh_audio_diag_format(const VhAudioDiagnostics *s, VhAudioDiagText *o) {
    if (!s || !o) return -1;
    memset(o,0,sizeof *o);
    const char *state=s->status==1 ? "PLAYING" :
                      s->status==2 ? "PAUSED" :
                      s->status<0 ? "ERROR" : "START";
    snprintf(o->line[0],VH_AUDIO_DIAG_LINE_CAP,"AUDIO DIAGNOSTICS");
    snprintf(o->line[1],VH_AUDIO_DIAG_LINE_CAP,"STATE %s",state);
    snprintf(o->line[2],VH_AUDIO_DIAG_LINE_CAP,"HOME RESUMES %u",
             s->resume_events);
    snprintf(o->line[3],VH_AUDIO_DIAG_LINE_CAP,"FIRST PCM COUNT %u",
             s->confirmed_resumes);
    snprintf(o->line[4],VH_AUDIO_DIAG_LINE_CAP,"LAST PCM US %llu",
             (unsigned long long)s->last_confirmed_us);
    snprintf(o->line[5],VH_AUDIO_DIAG_LINE_CAP,"WORST PCM US %llu",
             (unsigned long long)s->worst_confirmed_us);
    snprintf(o->line[6],VH_AUDIO_DIAG_LINE_CAP,"OUTPUT PAGES %llu",
             (unsigned long long)s->pages_submitted);
    snprintf(o->line[7],VH_AUDIO_DIAG_LINE_CAP,"PCM FAIL %u RESTART %u",
             s->submit_failures,s->restart_attempts);
    snprintf(o->line[8],VH_AUDIO_DIAG_LINE_CAP,"HOME FAIL %u REOPEN %u",
             s->resume_failures,s->resume_restarts);
    snprintf(o->line[9],VH_AUDIO_DIAG_LINE_CAP,"LEASE FAIL %u RESET %u",
             s->lease_mismatches,s->abandoned_sessions);
    const uint32_t recovered =
        UINT32_MAX-s->recoveries < s->resume_recoveries
        ? UINT32_MAX : s->recoveries+s->resume_recoveries;
    snprintf(o->line[10],VH_AUDIO_DIAG_LINE_CAP,"VAB WARN %u RECOVERED %u",
             s->bank_warnings,recovered);
    /* Even under arbitrary UINT32_MAX metrics, every label remains
     * legible on the in-game diagnostic overlay. */
    return 0;
}
