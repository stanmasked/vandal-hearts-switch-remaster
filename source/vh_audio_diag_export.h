#ifndef VH_AUDIO_DIAG_EXPORT_H
#define VH_AUDIO_DIAG_EXPORT_H

#include <stdio.h>
#include "vh_audio_diag_journal.h"

/* Bounded, explicit game-thread-only SD exporter. No I/O from SPU,
 * audout, callbacks, or the per-frame input/render loop.
 * Records get unique 0000..0063 names. Prior CSVs are NEVER opened
 * for writing or removed. An incomplete .tmp file is not a report.
 */
#define VH_AUDIO_DIAG_EXPORT_SLOTS 64u
#define VH_AUDIO_DIAG_EXPORT_PATH_CAP 512u

typedef struct {
    void *context;
    /* exists: 1 present, 0 missing, -1 failed/unknown. */
    int (*exists)(void *, const char *path);
    FILE *(*open)(void *, const char *path);
    /* Re-open the CLOSED temporary file to verify its actual bytes. */
    FILE *(*open_read)(void *, const char *path);
    int (*write)(void *, const VhAudioDiagJournal *, FILE *);
    int (*flush)(void *, FILE *);
    int (*close)(void *, FILE *);
    int (*rename)(void *, const char *old_path, const char *new_path);
    int (*remove)(void *, const char *path);
} VhAudioDiagExportOps;

typedef enum {
    VH_AUDIO_EXPORT_OK=0,
    VH_AUDIO_EXPORT_INVALID=-1,
    VH_AUDIO_EXPORT_PATH=-2,
    VH_AUDIO_EXPORT_SLOTS_FULL=-3,
    VH_AUDIO_EXPORT_OPEN=-4,
    VH_AUDIO_EXPORT_WRITE=-5,
    VH_AUDIO_EXPORT_FLUSH=-6,
    VH_AUDIO_EXPORT_CLOSE=-7,
    VH_AUDIO_EXPORT_RENAME=-8,
    VH_AUDIO_EXPORT_STAT=-9,
    VH_AUDIO_EXPORT_READ=-10,
    VH_AUDIO_EXPORT_VERIFY=-11
} VhAudioDiagExportResult;

/* Caller must join the native audio worker first. directory must
 * already exist; no mkdir, hidden device access, or original assets.
 * On success, dest receives the committed CSV pathname. On error,
 * dest is empty and old committed CSVs remain untouched.
 * Staged bytes are read back and compared to the canonical CSV
 * before rename. This is NOT a power-loss durability guarantee.
 * ops=NULL uses portable stdio/stat/rename; a complete custom ops
 * implementation can inject storage failures in host regression tests.
 */
VhAudioDiagExportResult vh_audio_diag_export(
    const VhAudioDiagJournal *journal, const char *directory,
    const VhAudioDiagExportOps *ops, char *dest, size_t dest_capacity);

#endif
