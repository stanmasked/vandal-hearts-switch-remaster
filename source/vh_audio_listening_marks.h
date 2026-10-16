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
    /* For EVERY returned page, ask if its last 32 pages overlap the
     * same events as a human-marked window. These windows overlap and
     * are NOT statistically independent observations. */
    uint64_t windows_near_switch;
    uint64_t windows_near_wait_over_2x;
    uint64_t windows_near_wait_over_4x;
    uint64_t windows_near_retry;
    uint32_t peak_seam_near_mark;
} VhAudioListeningMarks;

typedef struct {
    unsigned scene_boundary, over_2x, over_4x, retry;
    uint32_t peak_step;
} VhListenWindow;

/* Scan at most limit already-returned pages. This is a read-only
 * helper shared by button marks and baseline controls. Rejects bad
 * ring data without changing the requested result. */
static inline int vh_audio_listening_window(
    const VhAudioListeningMarks *m, unsigned limit, VhListenWindow *out) {
    if (!m || !out || limit>VH_LISTEN_RECENT_PAGES) return -1;
    const unsigned n=(unsigned)(m->returned_pages<limit
        ? m->returned_pages : limit);
    VhListenWindow w={0};
    for (unsigned i=0;i<n;i++) {
        const unsigned index=(unsigned)(
            (m->returned_pages-1u-i)%VH_LISTEN_RECENT_PAGES);
        const VhListenPage *p=&m->recent[index];
        if (p->wait_band>3u || p->scene_boundary>1u ||
            p->retry>1u || p->seam_step>65535u)
            return -1;
        w.scene_boundary|=(unsigned)p->scene_boundary;
        w.over_2x|=(unsigned)(p->wait_band>=2u);
        w.over_4x|=(unsigned)(p->wait_band==3u);
        w.retry|=(unsigned)p->retry;
        if (p->seam_step>w.peak_step) w.peak_step=p->seam_step;
    }
    *out=w;
    return 0;
}

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
    /* A control window contains this page + up to 31 preceding pages.
     * Scan before overwriting the oldest slot at ring wrap. */
    VhListenWindow w;
    if (vh_audio_listening_window(
            m,VH_LISTEN_RECENT_PAGES-1u,&w)) return -1;
    const unsigned sw=w.scene_boundary|scene_boundary;
    const unsigned slow2=w.over_2x|(unsigned)(wait_band>=2u);
    const unsigned slow4=w.over_4x|(unsigned)(wait_band==3u);
    const unsigned retried=w.retry|retry;
    if ((sw && m->windows_near_switch==UINT64_MAX) ||
        (slow2 && m->windows_near_wait_over_2x==UINT64_MAX) ||
        (slow4 && m->windows_near_wait_over_4x==UINT64_MAX) ||
        (retried && m->windows_near_retry==UINT64_MAX))
        return -1;
    const unsigned slot=(unsigned)(
        m->returned_pages%VH_LISTEN_RECENT_PAGES);
    VhListenPage *p=&m->recent[slot];
    p->wait_band=(uint8_t)wait_band;
    p->scene_boundary=(uint8_t)scene_boundary;
    p->retry=(uint8_t)retry;
    p->seam_step=seam_step;
    ++m->returned_pages;
    m->windows_near_switch+=sw;
    m->windows_near_wait_over_2x+=slow2;
    m->windows_near_wait_over_4x+=slow4;
    m->windows_near_retry+=retried;
    return 0;
}

/* One explicit A-button press marks a *perceived* issue. Correlation
 * is intentionally fuzzy because a human reacts after hearing sound
 * and audoutPlayBuffer returns synchronously. No causality claimed.
 */
static inline int vh_audio_listening_mark(VhAudioListeningMarks *m) {
    if (!m || !m->returned_pages || m->manual_marks==UINT64_MAX)
        return -1;
    VhListenWindow w;
    if (vh_audio_listening_window(
            m,VH_LISTEN_RECENT_PAGES,&w)) return -1;
    if ((w.scene_boundary && m->marks_near_switch==UINT64_MAX) ||
        (w.over_2x && m->marks_near_wait_over_2x==UINT64_MAX) ||
        (w.over_4x && m->marks_near_wait_over_4x==UINT64_MAX) ||
        (w.retry && m->marks_near_retry==UINT64_MAX)) return -1;
    ++m->manual_marks;
    m->marks_near_switch+=w.scene_boundary;
    m->marks_near_wait_over_2x+=w.over_2x;
    m->marks_near_wait_over_4x+=w.over_4x;
    m->marks_near_retry+=w.retry;
    if (w.peak_step>m->peak_seam_near_mark)
        m->peak_seam_near_mark=w.peak_step;
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
        m->windows_near_switch>m->returned_pages ||
        m->windows_near_wait_over_2x>m->returned_pages ||
        m->windows_near_wait_over_4x>m->windows_near_wait_over_2x ||
        m->windows_near_retry>m->returned_pages ||
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
