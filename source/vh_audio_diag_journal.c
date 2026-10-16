#include "vh_audio_diag_journal.h"

#include <limits.h>
#include <string.h>

void vh_audio_diag_journal_reset(VhAudioDiagJournal *j) {
    if (j) memset(j,0,sizeof *j);
}

static VhAudioDiagJournalEntry *last_entry(VhAudioDiagJournal *j) {
    if (!j->count) return NULL;
    const uint32_t idx=(j->head+VH_AUDIO_DIAG_JOURNAL_CAPACITY-1u)
        %VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    return &j->entries[idx];
}

static int add(VhAudioDiagJournal *j,uint64_t ms,
               const VhAudioDiagnostics *s,VhAudioDiagEvent event) {
    VhAudioDiagJournalEntry *slot=&j->entries[j->head];
    slot->elapsed_ms=ms;
    slot->event=event;
    slot->snapshot=*s;
    j->head=(j->head+1u)%VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    if(j->count<VH_AUDIO_DIAG_JOURNAL_CAPACITY) ++j->count;
    if(j->total<UINT64_MAX) ++j->total;
    return 1;
}

int vh_audio_diag_journal_sample(VhAudioDiagJournal *j,
                                  uint64_t ms,
                                  const VhAudioDiagnostics *s) {
    if (!j || !s || j->count>VH_AUDIO_DIAG_JOURNAL_CAPACITY ||
        j->head>=VH_AUDIO_DIAG_JOURNAL_CAPACITY) return -1;
    const VhAudioDiagJournalEntry *last=last_entry(j);
    if (!last) return add(j,ms,s,VH_AUDIO_DIAG_EVENT_START);
    const VhAudioDiagnostics *p=&last->snapshot;
    VhAudioDiagEvent event=VH_AUDIO_DIAG_EVENT_PERIODIC;
    if (ms<last->elapsed_ms) event=VH_AUDIO_DIAG_EVENT_CLOCK;
    else if((s->status<0 && p->status>=0) ||
            s->submit_failures!=p->submit_failures ||
            s->resume_failures!=p->resume_failures ||
            s->lease_mismatches!=p->lease_mismatches)
        event=VH_AUDIO_DIAG_EVENT_ERROR;
    else if(s->resume_events!=p->resume_events ||
            s->confirmed_resumes!=p->confirmed_resumes ||
            s->restart_attempts!=p->restart_attempts ||
            s->resume_restarts!=p->resume_restarts)
        event=VH_AUDIO_DIAG_EVENT_RESUME;
    else if(s->status!=p->status ||
            s->bank_warnings!=p->bank_warnings)
        event=VH_AUDIO_DIAG_EVENT_STATE;
    else if(ms-last->elapsed_ms<VH_AUDIO_DIAG_PERIOD_MS) return 0;
    return add(j,ms,s,event);
}

int vh_audio_diag_journal_finish(VhAudioDiagJournal *j,
                                  uint64_t ms,
                                  const VhAudioDiagnostics *s) {
    if (!j || !s || j->count>VH_AUDIO_DIAG_JOURNAL_CAPACITY ||
        j->head>=VH_AUDIO_DIAG_JOURNAL_CAPACITY) return -1;
    return add(j,ms,s,VH_AUDIO_DIAG_EVENT_EXIT);
}

static const char *name(VhAudioDiagEvent event) {
    switch(event) {
    case VH_AUDIO_DIAG_EVENT_START: return "START";
    case VH_AUDIO_DIAG_EVENT_PERIODIC: return "PERIODIC";
    case VH_AUDIO_DIAG_EVENT_STATE: return "STATE";
    case VH_AUDIO_DIAG_EVENT_RESUME: return "RESUME";
    case VH_AUDIO_DIAG_EVENT_ERROR: return "ERROR";
    case VH_AUDIO_DIAG_EVENT_EXIT: return "EXIT";
    case VH_AUDIO_DIAG_EVENT_CLOCK: return "CLOCK";
    default: return "UNKNOWN";
    }
}

int vh_audio_diag_journal_write_csv(const VhAudioDiagJournal *j,FILE *f) {
    if(!j || !f || j->count>VH_AUDIO_DIAG_JOURNAL_CAPACITY ||
       j->head>=VH_AUDIO_DIAG_JOURNAL_CAPACITY) return -1;
    if(fputs("elapsed_ms,event,status,home_resumes,first_pcm_count,"
             "last_pcm_us,worst_pcm_us,output_pages,output_frames,"
             "pcm_fail,pcm_restart,pcm_recover,home_fail,home_reopen,"
             "home_recover,lease_fail,lease_reset,vab_warn\n",f)==EOF)
        return -1;
    const uint32_t start=(j->head+VH_AUDIO_DIAG_JOURNAL_CAPACITY-
                          j->count)%VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    for(uint32_t i=0;i<j->count;i++) {
        const VhAudioDiagJournalEntry *entry=&j->entries[
            (start+i)%VH_AUDIO_DIAG_JOURNAL_CAPACITY];
        const VhAudioDiagnostics *s=&entry->snapshot;
        if(fprintf(f,"%llu,%s,%d,%u,%u,%llu,%llu,%llu,%llu,"
                     "%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
              (unsigned long long)entry->elapsed_ms,name(entry->event),
              s->status,s->resume_events,s->confirmed_resumes,
              (unsigned long long)s->last_confirmed_us,
              (unsigned long long)s->worst_confirmed_us,
              (unsigned long long)s->pages_submitted,
              (unsigned long long)s->frames_submitted,
              s->submit_failures,s->restart_attempts,s->recoveries,
              s->resume_failures,s->resume_restarts,s->resume_recoveries,
              s->lease_mismatches,s->abandoned_sessions,
              s->bank_warnings)<0) return -1;
    }
    return ferror(f) ? -1 : (int)j->count;
}
