#ifndef VH_AUDIO_DIAG_JOURNAL_H
#define VH_AUDIO_DIAG_JOURNAL_H

#include <stdint.h>
#include <stdio.h>
#include "vh_audio_diagnostics.h"

/* Game-thread-only diagnostic ring. No heap, bank/PCM pointers,
 * device calls or file I/O during collection. Maximum 128 rows.
 * A slow/long hardware session overwrites oldest samples, never
 * allocates more storage or blocks the audio worker.
 */
#define VH_AUDIO_DIAG_JOURNAL_CAPACITY 128u
#define VH_AUDIO_DIAG_PERIOD_MS UINT64_C(5000)

typedef enum {
    VH_AUDIO_DIAG_EVENT_START=0,
    VH_AUDIO_DIAG_EVENT_PERIODIC=1,
    VH_AUDIO_DIAG_EVENT_STATE=2,
    VH_AUDIO_DIAG_EVENT_RESUME=3,
    VH_AUDIO_DIAG_EVENT_ERROR=4,
    VH_AUDIO_DIAG_EVENT_EXIT=5,
    VH_AUDIO_DIAG_EVENT_CLOCK=6,
    VH_AUDIO_DIAG_EVENT_GAP=7 /* exporter-only marker: old rows evicted */
} VhAudioDiagEvent;

typedef struct {
    uint64_t elapsed_ms;
    VhAudioDiagEvent event;
    VhAudioDiagnostics snapshot;
} VhAudioDiagJournalEntry;

typedef struct {
    VhAudioDiagJournalEntry entries[VH_AUDIO_DIAG_JOURNAL_CAPACITY];
    /* Retain initial counter origin OUTSIDE the ring; on wrap export
     * origin + latest 127 snapshots, with an explicit GAP event to
     * make unobservable historical event ordering unambiguous. */
    VhAudioDiagJournalEntry origin;
    uint32_t head; /* next write */
    uint32_t count;
    uint64_t total; /* saturates at UINT64_MAX */
} VhAudioDiagJournal;

void vh_audio_diag_journal_reset(VhAudioDiagJournal *journal);

/* Returns 1 if a row was collected, 0 when unchanged too soon,
 * -1 on invalid arguments. Detects transitions and failures at
 * every game frame; otherwise takes a heartbeat every >=5 seconds.
 */
int vh_audio_diag_journal_sample(VhAudioDiagJournal *journal,
                                  uint64_t elapsed_ms,
                                  const VhAudioDiagnostics *snapshot);

/* Always appends a final snapshot even before the heartbeat timeout. */
int vh_audio_diag_journal_finish(VhAudioDiagJournal *journal,
                                  uint64_t elapsed_ms,
                                  const VhAudioDiagnostics *snapshot);

/* After rollover, exports START + a GAP snapshot + the newest 126
 * snapshots (still <=128 total rows). The GAP contains the FIRST
 * retained counters after eviction; cumulative deltas from START
 * include all past failures, but their exact timing is unknown.
 * Writes chronological CSV rows using stdio. ONLY call from the
 * game/main thread AFTER the audio worker has been joined; never
 * call this function during synthesis or the audio callback.
 * Returns number of exported rows, or -1 on output error.
 */
int vh_audio_diag_journal_write_csv(const VhAudioDiagJournal *journal,
                                     FILE *stream);

/* Verify EXACT stored CSV bytes (including all rows and EOF) by reading
 * a staged file opened in binary read mode. Called after fclose of
 * the writer and before rename to a numbered .csv. Returns number
 * of verified rows, or -1 for mismatch, truncation, garbage or I/O
 * failure. No allocation; does not prove SD power-loss durability. */
int vh_audio_diag_journal_verify_csv(const VhAudioDiagJournal *journal,
                                      FILE *stream);

#endif
