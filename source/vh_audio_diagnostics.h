#ifndef VH_AUDIO_DIAGNOSTICS_H
#define VH_AUDIO_DIAGNOSTICS_H

#include <stddef.h>
#include <stdint.h>

/* Snapshot of published, atomic audio-owner counters. No pointers
 * into music banks, device buffers, or other worker-owned state.
 * Approximate across fields while worker runs; never locks audio.
 */
typedef struct {
    int status;
    uint32_t bank_warnings;
    uint32_t resume_events;
    uint32_t confirmed_resumes;
    uint64_t last_confirmed_us;
    uint64_t worst_confirmed_us;
    uint64_t pages_submitted;
    uint64_t frames_submitted;
    uint32_t submit_failures;
    uint32_t restart_attempts;
    uint32_t recoveries;
    uint32_t resume_failures;
    uint32_t resume_restarts;
    uint32_t resume_recoveries;
    uint32_t lease_mismatches;
    uint32_t abandoned_sessions;
} VhAudioDiagnostics;

/* Renderer-safe ASCII line formatter: uppercase A-Z, 0-9, spaces and
 * hyphens only, fitting existing original 5x7 debug bitmap font.
 * Returns -1 on invalid output, or 0 on success. Never allocates.
 */
#define VH_AUDIO_DIAG_LINES 11u
#define VH_AUDIO_DIAG_LINE_CAP 48u
typedef struct {
    char line[VH_AUDIO_DIAG_LINES][VH_AUDIO_DIAG_LINE_CAP];
} VhAudioDiagText;

int vh_audio_diag_format(const VhAudioDiagnostics *snapshot,
                          VhAudioDiagText *text);

#endif
