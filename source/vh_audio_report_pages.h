#ifndef VH_AUDIO_REPORT_PAGES_H
#define VH_AUDIO_REPORT_PAGES_H

/* Portable navigation and strict evidence labels for three fixed
 * on-device report pages. UI only; never touches audio or PCM.
 * "FULL" means valid page accounting, never audible quality.
 */
/* Portable manual X/Y evidence; a successful audio-page audit does not
 * override missing or contradictory manual recovery measurements.
 * "FULL" still means internally consistent bookkeeping, NOT audible
 * quality, HOME/sleep compatibility or physical console verification. */
typedef struct {
    unsigned quick_attempts, quick_ok;
    unsigned reopen_attempts, reopen_ok;
    unsigned ignored_chords, unsafe_requests, state_mismatches;
} VhAudioManualResume;

#define VH_AUDIO_MANUAL_X 1u
#define VH_AUDIO_MANUAL_Y 2u
#define VH_AUDIO_MANUAL_IGNORE 3u

/* Pressed/held use normalized X/Y flags, not hardware key bit positions.
 * An X+Y chord is ignored even when the keys were pressed on different
 * controller polls (only the second key may have a rising edge).
 * Return 0 for no new keypress or unrecognized flags. */
static inline unsigned vh_audio_manual_select(unsigned pressed,
                                               unsigned held) {
    if (!pressed || (pressed|held)&~(VH_AUDIO_MANUAL_X|VH_AUDIO_MANUAL_Y))
        return 0u;
    if ((held & (VH_AUDIO_MANUAL_X|VH_AUDIO_MANUAL_Y)) ==
        (VH_AUDIO_MANUAL_X|VH_AUDIO_MANUAL_Y))
        return VH_AUDIO_MANUAL_IGNORE;
    return pressed == VH_AUDIO_MANUAL_X ? VH_AUDIO_MANUAL_X :
           pressed == VH_AUDIO_MANUAL_Y ? VH_AUDIO_MANUAL_Y :
           VH_AUDIO_MANUAL_IGNORE;
}

/* Invalid/failed manual attempts MUST NOT be silently reported as FULL. */
static inline int vh_audio_manual_verify(const VhAudioManualResume *m) {
    return m && !m->unsafe_requests && !m->state_mismatches &&
           m->quick_ok==m->quick_attempts &&
           m->reopen_ok==m->reopen_attempts ? 0 : -1;
}

#define VH_AUDIO_REPORT_PAGE_COUNT 3u
#define VH_AUDIO_REPORT_PREV 1u
#define VH_AUDIO_REPORT_NEXT 2u
#define VH_AUDIO_REPORT_QUIT 4u

#define VH_AUDIO_REPORT_INVALID 0u
#define VH_AUDIO_REPORT_INCOMPLETE 1u
#define VH_AUDIO_REPORT_FULL 2u

static inline unsigned vh_audio_report_evidence(
    int run, int seams, int listening, int input, int compute) {
    if ((run!=0 && run!=1) || seams!=0 ||
        listening!=0 || input!=0 || compute!=0)
        return VH_AUDIO_REPORT_INVALID;
    return run==1 ? VH_AUDIO_REPORT_FULL : VH_AUDIO_REPORT_INCOMPLETE;
}

/* Combines existing PCM/telemetry evidence with explicit manual X/Y
 * safety accounting without changing other report call sites. */
static inline unsigned vh_audio_report_manual_evidence(
    const VhAudioManualResume *manual, int run, int seams,
    int listening, int input, int compute) {
    if (vh_audio_manual_verify(manual)) return VH_AUDIO_REPORT_INVALID;
    return vh_audio_report_evidence(run,seams,listening,input,compute);
}

/* 0 means continue, 1 means user requested exit, -1 invalid input.
 * Both direction keys in one sample mean no page change; PLUS wins.
 * Reject unknown flags before modifying the current page.
 */
static inline int vh_audio_report_navigate(unsigned *page,
                                           unsigned flags) {
    if (!page || *page>=VH_AUDIO_REPORT_PAGE_COUNT ||
        (flags&~(VH_AUDIO_REPORT_PREV|VH_AUDIO_REPORT_NEXT|
                  VH_AUDIO_REPORT_QUIT))) return -1;
    if (flags&VH_AUDIO_REPORT_QUIT) return 1;
    const unsigned dirs=flags&(VH_AUDIO_REPORT_PREV|VH_AUDIO_REPORT_NEXT);
    if (dirs==VH_AUDIO_REPORT_PREV)
        *page=(*page+VH_AUDIO_REPORT_PAGE_COUNT-1u)%
              VH_AUDIO_REPORT_PAGE_COUNT;
    if (dirs==VH_AUDIO_REPORT_NEXT)
        *page=(*page+1u)%VH_AUDIO_REPORT_PAGE_COUNT;
    return 0;
}
#endif
