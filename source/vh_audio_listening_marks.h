#ifndef VH_AUDIO_LISTENING_MARKS_H
#define VH_AUDIO_LISTENING_MARKS_H

#include <stdint.h>
#include <limits.h>

/* Device operator listening observations are NOT automatically detected
 * audio glitches. A button-down edge captures a fuzzy look-back window
 * of 32 already-returned audio pages (~0.37s at 44.1 kHz / 512 frames).
 * Keep no samples, timestamps, filenames, notes or source identity.
 * Pure, portable, fixed-storage instrumentation: no audio API calls.
 */
#define VH_LISTEN_RECENT_PAGES 32u

typedef struct {
    uint32_t seam_step;
    uint8_t wait_band;       /* 0:<=1x 1:<=2x 2:<=4x 3:>4x */
    uint8_t scene_boundary;  /* first page after generated cue change */
    uint8_t retry;           /* service needed >1 submission attempt */
} VhListenPage;

typedef struct {
    VhListenPage recent[VH_LISTEN_RECENT_PAGES];
    uint64_t returned_pages;
    uint64_t manual_marks;
    uint64_t marks_near_switch;
    uint64_t marks_near_wait_over_2x;
    uint64_t marks_near_wait_over_4x;
    uint64_t marks_near_retry;
    uint32_t peak_seam_near_mark;
} VhAudioListeningMarks;

/* Each returned logical page is inserted exactly once after success.
 * Invalid observations must not mutate state. Caller separately
 * verifies that returned_pages equals the audout completed-page count.
 */
static inline int vh_audio_listening_observe(
    VhAudioListeningMarks *m, unsigned wait_band,
    unsigned scene_boundary, unsigned retry, uint32_t seam_step) {
    if (!m || wait_band>3u || scene_boundary>1u ||
        retry>1u || seam_step>65535u ||
        m->returned_pages==UINT64_MAX) return -1;
    const unsigned slot=(unsigned)(
        m->returned_pages%VH_LISTEN_RECENT_PAGES);
    VhListenPage *p=&m->recent[slot];
    p->wait_band=(uint8_t)wait_band;
    p->scene_boundary=(uint8_t)scene_boundary;
    p->retry=(uint8_t)retry;
    p->seam_step=seam_step;
    ++m->returned_pages;
    return 0;
}

/* One explicit A-button press marks a *perceived* issue. Correlation
 * is intentionally fuzzy because a human reacts after hearing sound
 * and audoutPlayBuffer returns synchronously. No causality claimed.
 */
static inline int vh_audio_listening_mark(VhAudioListeningMarks *m) {
    if (!m || !m->returned_pages || m->manual_marks==UINT64_MAX)
        return -1;
    const unsigned n=(unsigned)(
        m->returned_pages<VH_LISTEN_RECENT_PAGES
        ? m->returned_pages : VH_LISTEN_RECENT_PAGES);
    unsigned near_switch=0u, near_2x=0u, near_4x=0u, near_retry=0u;
    uint32_t local_peak=0u;
    for (unsigned i=0;i<n;i++) {
        const unsigned slot=(unsigned)(
            (m->returned_pages-1u-i)%VH_LISTEN_RECENT_PAGES);
        const VhListenPage *p=&m->recent[slot];
        if (p->wait_band>3u || p->scene_boundary>1u ||
            p->retry>1u || p->seam_step>65535u) return -1;
        near_switch|=p->scene_boundary;
        near_2x|=(unsigned)(p->wait_band>=2u);
        near_4x|=(unsigned)(p->wait_band==3u);
        near_retry|=p->retry;
        if (p->seam_step>local_peak) local_peak=p->seam_step;
    }
    if ((near_switch && m->marks_near_switch==UINT64_MAX) ||
        (near_2x && m->marks_near_wait_over_2x==UINT64_MAX) ||
        (near_4x && m->marks_near_wait_over_4x==UINT64_MAX) ||
        (near_retry && m->marks_near_retry==UINT64_MAX)) return -1;
    ++m->manual_marks;
    m->marks_near_switch+=near_switch;
    m->marks_near_wait_over_2x+=near_2x;
    m->marks_near_wait_over_4x+=near_4x;
    m->marks_near_retry+=near_retry;
    if (local_peak>m->peak_seam_near_mark)
        m->peak_seam_near_mark=local_peak;
    return 0;
}

/* Reject invalid final metadata before presenting marked observations. */
static inline int vh_audio_listening_verify(
    const VhAudioListeningMarks *m, uint64_t expected_pages) {
    if (!m || m->returned_pages!=expected_pages ||
        m->marks_near_switch>m->manual_marks ||
        m->marks_near_wait_over_2x>m->manual_marks ||
        m->marks_near_wait_over_4x>m->marks_near_wait_over_2x ||
        m->marks_near_retry>m->manual_marks ||
        m->peak_seam_near_mark>65535u ||
        (!m->manual_marks && m->peak_seam_near_mark) ||
        (!m->returned_pages && m->manual_marks)) return -1;
    const unsigned n=(unsigned)(m->returned_pages<VH_LISTEN_RECENT_PAGES
        ? m->returned_pages : VH_LISTEN_RECENT_PAGES);
    for (unsigned i=0;i<n;i++) {
        const VhListenPage *p=&m->recent[i];
        if (p->wait_band>3u || p->scene_boundary>1u ||
            p->retry>1u || p->seam_step>65535u)
            return -1;
    }
    return 0;
}
#endif
