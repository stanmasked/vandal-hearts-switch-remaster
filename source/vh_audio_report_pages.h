#ifndef VH_AUDIO_REPORT_PAGES_H
#define VH_AUDIO_REPORT_PAGES_H

/* Portable navigation and strict evidence labels for four fixed
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

#include <limits.h>
#include <stdint.h>


/* Platform-independent applet lifecycle observer. It records only event
 * order, NOT successful audio resume or sound. The applet hook may call
 * this synchronously while appletMainLoop handles system messages.
 * No PCM or audout service action is permitted in the callback. */
typedef struct {
    unsigned backgrounds, returns, resumes, ignored_duplicates;
    unsigned in_background;
    /* A foreground notice arms ONE page observation. Multiple
     * foreground notices without an intervening returned page are
     * explicitly coalesced, never silently counted as observed audio. */
    unsigned pending_return, coalesced_returns;
    unsigned first_pages_after_return, returned_pages;
    /* Same-clock interval from observed foreground to returned PCM.
     * Zero timestamp means unknown, not zero latency. */
    uint64_t foreground_tick, max_page_gap_ticks, total_page_gap_ticks;
    unsigned timestamp_pending, timed_first_pages;
    /* Budget-normalized, disjoint first-return bands <=1x, (1,2]x,
     * (2,4]x and >4x. Missing budgets remain unclassified, not 0x. */
    unsigned budgeted_first_pages, page_budget_bands[4];
    /* A failed logical submit_recover() call does NOT return a PCM
     * descriptor. Its failure cannot consume pending HOME evidence.
     * A subsequent explicit retry of the same immutable page may yet
     * return it; these counters describe failed calls, not dropped
     * or audible PCM frames. */
    unsigned failed_logical_submissions, failures_while_pending;
} VhAudioAppletEvents;

#define VH_AUDIO_APPLET_BACKGROUND 1u
#define VH_AUDIO_APPLET_FOREGROUND 2u
#define VH_AUDIO_APPLET_RESUME 3u

/* Atomic on invalid enum/counter overflow. Ignore duplicate focus
 * notifications; a return counts only after a recorded background.
 * OnResume is a separate system message, not an assertion of recovery. */
static inline int vh_audio_applet_record(VhAudioAppletEvents *s,
                                         unsigned event) {
    if(!s) return -1;
    if(event==VH_AUDIO_APPLET_BACKGROUND) {
        if(s->in_background) {
            if(s->ignored_duplicates==UINT_MAX) return -1;
            ++s->ignored_duplicates;
            return 0;
        }
        if(s->backgrounds==UINT_MAX) return -1;
        ++s->backgrounds;
        s->in_background=1u;
        return 0;
    }
    if(event==VH_AUDIO_APPLET_FOREGROUND) {
        if(!s->in_background) {
            if(s->ignored_duplicates==UINT_MAX) return -1;
            ++s->ignored_duplicates;
            return 0;
        }
        if(s->returns==UINT_MAX ||
           (s->pending_return && s->coalesced_returns==UINT_MAX))
            return -1;
        ++s->returns;
        if(s->pending_return) ++s->coalesced_returns;
        /* A new foreground notice supersedes any older timestamp.
         * record_at() installs a fresh tick; the untimed path MUST
         * NOT borrow time from a prior coalesced HOME return. */
        s->timestamp_pending=0u;
        s->foreground_tick=0u;
        s->pending_return=1u;
        s->in_background=0u;
        return 0;
    }
    if(event==VH_AUDIO_APPLET_RESUME) {
        if(s->resumes==UINT_MAX) return -1;
        ++s->resumes;
        return 0;
    }
    return -1;
}

/* Call once after the audout descriptor has been returned AND the
 * returned-page telemetry transaction has committed. A focus notice
 * alone never implies playback; this records the next observed PCM
 * descriptor returned on the producer thread. Returns 1 only for
 * that first page, 0 for other pages, -1 on invalid/overflow state. */
static inline int vh_audio_applet_page_returned(VhAudioAppletEvents *s) {
    if(!s || s->returned_pages==UINT_MAX ||
       (s->pending_return && s->first_pages_after_return==UINT_MAX))
        return -1;
    ++s->returned_pages;
    /* A callback may report background between returned pages.
     * Pages returned while backgrounded do not confirm foreground. */
    if(!s->pending_return || s->in_background) return 0;
    s->pending_return=0u;
    s->timestamp_pending=0u;
    ++s->first_pages_after_return;
    return 1;
}

/* Timestamp-aware wrapper for libnx applet events. Other callers may
 * use the untimed recorder; a return with no timestamp is excluded
 * from latency statistics. Tick values must share the PCM clock. */
static inline int vh_audio_applet_record_at(VhAudioAppletEvents *s,
                                             unsigned event,
                                             uint64_t tick) {
    if(!s) return -1;
    const unsigned before=s->returns;
    if(vh_audio_applet_record(s,event)) return -1;
    if(event==VH_AUDIO_APPLET_FOREGROUND && s->returns!=before) {
        s->foreground_tick=tick;
        s->timestamp_pending=tick!=0u;
    }
    return 0;
}

/* Measure only after a validated audout page and telemetry commit.
 * Preflight clock regression and overflow BEFORE incrementing pages.
 * This is callback-to-page service latency, not proof of audible
 * output and not wall time spent while the console is asleep. */
static inline int vh_audio_applet_page_returned_budget_at(
    VhAudioAppletEvents *s, uint64_t tick, uint64_t budget_ticks) {
    if(!s) return -1;
    const unsigned measure=s->pending_return && !s->in_background &&
                           s->timestamp_pending;
    uint64_t delta=0u;
    unsigned band=0u;
    if(measure) {
        if(!tick || tick<s->foreground_tick ||
           s->timed_first_pages==UINT_MAX) return -1;
        delta=tick-s->foreground_tick;
        if(delta>UINT64_MAX-s->total_page_gap_ticks) return -1;
        if(budget_ticks) {
            /* Use division and remainder to avoid 2x/4x overflow on
             * synthetic UINT64_MAX budgets. Inclusive upper bounds. */
            const uint64_t multiple=delta/budget_ticks;
            const uint64_t rem=delta%budget_ticks;
            if(delta<=budget_ticks) band=0u;
            else if(multiple<2u || (multiple==2u && !rem)) band=1u;
            else if(multiple<4u || (multiple==4u && !rem)) band=2u;
            else band=3u;
            if(s->budgeted_first_pages==UINT_MAX ||
               s->page_budget_bands[band]==UINT_MAX) return -1;
        }
    }
    const int first=vh_audio_applet_page_returned(s);
    if(first<=0) return first;
    if(measure) {
        s->total_page_gap_ticks+=delta;
        if(delta>s->max_page_gap_ticks) s->max_page_gap_ticks=delta;
        ++s->timed_first_pages;
        if(budget_ticks) {
            ++s->page_budget_bands[band];
            ++s->budgeted_first_pages;
        }
    }
    return first;
}

/* Calls without a known frame-time budget remain time-stamped but
 * excluded from budget-normalized bins. */
static inline int vh_audio_applet_page_returned_at(VhAudioAppletEvents *s,
                                                    uint64_t tick) {
    return vh_audio_applet_page_returned_budget_at(s,tick,0u);
}

/* Record only AFTER a failed logical submission is accepted by
 * the scene-page telemetry. Preserve pending foreground and the
 * original callback tick; no PCM page was returned. On error the
 * observer remains byte-for-byte unchanged. */
static inline int vh_audio_applet_submit_failed(VhAudioAppletEvents *s) {
    if(!s || s->failed_logical_submissions==UINT_MAX ||
       (s->pending_return && s->failures_while_pending==UINT_MAX))
        return -1;
    ++s->failed_logical_submissions;
    if(s->pending_return) ++s->failures_while_pending;
    return 0;
}

/* Strong internal event-to-returned-page accounting, never a
 * hardware-audio PASS. Subtractions avoid unsigned addition wrap. */
static inline int vh_audio_applet_verify(const VhAudioAppletEvents *s) {
    if(!s || s->in_background>1u || s->pending_return>1u ||
       s->returns>s->backgrounds ||
       s->backgrounds-s->returns!=s->in_background ||
       s->first_pages_after_return>s->returns ||
       s->first_pages_after_return>s->returned_pages ||
       s->coalesced_returns>s->returns-s->first_pages_after_return ||
       s->timestamp_pending>1u ||
       (s->timestamp_pending && !s->pending_return) ||
       s->timed_first_pages>s->first_pages_after_return ||
       s->budgeted_first_pages>s->timed_first_pages ||
       s->failures_while_pending>s->failed_logical_submissions ||
       (uint64_t)s->page_budget_bands[0]+s->page_budget_bands[1]+
           s->page_budget_bands[2]+s->page_budget_bands[3] !=
                                                  s->budgeted_first_pages ||
       s->max_page_gap_ticks>s->total_page_gap_ticks ||
       (!s->timed_first_pages &&
        (s->max_page_gap_ticks || s->total_page_gap_ticks)))
        return -1;
    return s->returns-s->first_pages_after_return-
           s->coalesced_returns==s->pending_return ? 0 : -1;
}

#define VH_AUDIO_REPORT_PAGE_COUNT 4u
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

/* An observed foreground return WITHOUT any subsequently returned
 * audout descriptor is missing evidence. Do not upgrade such a session
 * to FULL even if older PCM/page counters are internally consistent.
 * This remains bookkeeping, not a test of audible playback. */
static inline unsigned vh_audio_report_focus_evidence(
    const VhAudioAppletEvents *focus, const VhAudioManualResume *manual,
    int run, int seams, int listening, int input, int compute) {
    if(vh_audio_applet_verify(focus))
        return VH_AUDIO_REPORT_INVALID;
    const unsigned verdict=vh_audio_report_manual_evidence(
        manual,run,seams,listening,input,compute);
    if(verdict==VH_AUDIO_REPORT_FULL &&
       (focus->pending_return || focus->in_background))
        return VH_AUDIO_REPORT_INCOMPLETE;
    return verdict;
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
