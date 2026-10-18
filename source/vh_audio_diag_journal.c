#include "vh_audio_diag_journal.h"

#include <limits.h>
#include <stdio.h>
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
    if (!j->total) j->origin=*slot;
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
    case VH_AUDIO_DIAG_EVENT_GAP: return "GAP";
    default: return "UNKNOWN";
    }
}

/* A canonical, bounded line formatter is shared by the CSV writer
 * and the verification pass that reads bytes BACK from staged storage.
 * Maximum line length is below 384 bytes even with UINT64_MAX for
 * every wide counter. Any truncation fails closed instead of creating
 * a seemingly complete CSV with missing digits.
 */
#define CSV_LINE_CAP 384u
static const char csv_header[]=
    "elapsed_ms,event,status,home_resumes,first_pcm_count,"
    "last_pcm_us,worst_pcm_us,output_pages,output_frames,"
    "pcm_fail,pcm_restart,pcm_recover,home_fail,home_reopen,"
    "home_recover,lease_fail,lease_reset,vab_warn\n";

static int format_entry(char *line,size_t capacity,
                        const VhAudioDiagJournalEntry *entry,
                        VhAudioDiagEvent event) {
    const VhAudioDiagnostics *s=&entry->snapshot;
    const int n=snprintf(line,capacity,
        "%llu,%s,%d,%u,%u,%llu,%llu,%llu,%llu,"
        "%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
        (unsigned long long)entry->elapsed_ms,name(event),
        s->status,s->resume_events,s->confirmed_resumes,
        (unsigned long long)s->last_confirmed_us,
        (unsigned long long)s->worst_confirmed_us,
        (unsigned long long)s->pages_submitted,
        (unsigned long long)s->frames_submitted,
        s->submit_failures,s->restart_attempts,s->recoveries,
        s->resume_failures,s->resume_restarts,s->resume_recoveries,
        s->lease_mismatches,s->abandoned_sessions,s->bank_warnings);
    return n>0 && (size_t)n<capacity ? 0 : -1;
}

static int journal_valid(const VhAudioDiagJournal *j) {
    return j && j->count && j->count<=VH_AUDIO_DIAG_JOURNAL_CAPACITY &&
           j->head<VH_AUDIO_DIAG_JOURNAL_CAPACITY;
}

/* Yield each serialized row in the SAME order to both consumers.
 * On rollover START is pinned, the first retained row is skipped
 * and the next row is labelled GAP, retaining at most 128 lines.
 */
static const VhAudioDiagJournalEntry *journal_row(
    const VhAudioDiagJournal *j,uint32_t i,VhAudioDiagEvent *event) {
    const int wrapped=j->total>VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    if(wrapped && i==0u) {
        *event=j->origin.event;
        return &j->origin;
    }
    const uint32_t start=(j->head+VH_AUDIO_DIAG_JOURNAL_CAPACITY-
                          j->count)%VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    const uint32_t slot=(start+i)%VH_AUDIO_DIAG_JOURNAL_CAPACITY;
    const VhAudioDiagJournalEntry *entry=&j->entries[slot];
    *event=wrapped && i==1u ? VH_AUDIO_DIAG_EVENT_GAP : entry->event;
    return entry;
}

int vh_audio_diag_journal_write_csv(const VhAudioDiagJournal *j,FILE *f) {
    if(!journal_valid(j) || !f) return -1;
    if(fputs(csv_header,f)==EOF) return -1;
    char line[CSV_LINE_CAP];
    for(uint32_t i=0;i<j->count;i++) {
        VhAudioDiagEvent event;
        const VhAudioDiagJournalEntry *entry=journal_row(j,i,&event);
        if(format_entry(line,sizeof line,entry,event) || fputs(line,f)==EOF)
            return -1;
    }
    return ferror(f) ? -1 : (int)j->count;
}

/* No file is promoted to .csv unless exact readback matches the
 * expected canonical header, rows, line endings and EOF. A short
 * write returning a false success, post-write corruption or appended
 * garbage is rejected. Readback verifies filesystem-visible bytes,
 * NOT their durability after real hardware power loss.
 */
int vh_audio_diag_journal_verify_csv(const VhAudioDiagJournal *j,FILE *f) {
    if(!journal_valid(j) || !f) return -1;
    char actual[CSV_LINE_CAP],expected[CSV_LINE_CAP];
    if(!fgets(actual,sizeof actual,f) ||
       strcmp(actual,csv_header)!=0) return -1;
    for(uint32_t i=0;i<j->count;i++) {
        VhAudioDiagEvent event;
        const VhAudioDiagJournalEntry *entry=journal_row(j,i,&event);
        if(format_entry(expected,sizeof expected,entry,event) ||
           !fgets(actual,sizeof actual,f) || strcmp(actual,expected)!=0)
            return -1;
    }
    return fgetc(f)==EOF && !ferror(f) ? (int)j->count : -1;
}
