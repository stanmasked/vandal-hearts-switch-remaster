#ifndef VH_AUDIO_REPORT_PAGES_H
#define VH_AUDIO_REPORT_PAGES_H

/* Portable navigation and strict evidence labels for three fixed
 * on-device report pages. UI only; never touches audio or PCM.
 * "FULL" means valid page accounting, never audible quality.
 */
#define VH_AUDIO_REPORT_PAGE_COUNT 3u
#define VH_AUDIO_REPORT_PREV 1u
#define VH_AUDIO_REPORT_NEXT 2u
#define VH_AUDIO_REPORT_QUIT 4u

#define VH_AUDIO_REPORT_INVALID 0u
#define VH_AUDIO_REPORT_INCOMPLETE 1u
#define VH_AUDIO_REPORT_FULL 2u

static inline unsigned vh_audio_report_evidence(
    int run, int seams, int listening, int input) {
    if ((run!=0 && run!=1) || seams!=0 ||
        listening!=0 || input!=0)
        return VH_AUDIO_REPORT_INVALID;
    return run==1 ? VH_AUDIO_REPORT_FULL : VH_AUDIO_REPORT_INCOMPLETE;
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
