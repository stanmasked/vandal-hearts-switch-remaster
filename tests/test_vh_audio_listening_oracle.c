/* Independent long-run oracle for 32-returned-page A/B and all-page
 * listening windows. Host-only synthetic integer page metadata.
 * No libnx, PCM buffers, music assets or audible-glitch inference.
 */
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include "vh_audio_listening_marks.h"

enum { ORACLE_PAGES=4096, ORACLE_EVENTS=4 };
enum { CUE=0, SLOW2=1, SLOW4=2, RETRY=3 };
enum { A_MARK=0, B_CONTROL=1, ALL_PAGES=2 };

typedef struct {
    unsigned band, cue, retry;
    uint32_t step;
} OraclePage;

typedef struct {
    uint64_t windows;
    uint64_t events[ORACLE_EVENTS];
    uint32_t peak;
} OracleStats;

/* Deliberately not based on the production ring structure or helper.
 * This straightforward historical array can distinguish an event on
 * the 32nd-oldest page from one just outside the lookback window. */
static OraclePage history[ORACLE_PAGES];

static void reference_window(size_t end, size_t length,
                             unsigned events[ORACLE_EVENTS],
                             uint32_t *peak) {
    for (unsigned k=0;k<ORACLE_EVENTS;k++) events[k]=0u;
    *peak=0u;
    const size_t begin=end>length ? end-length : 0u;
    for (size_t j=begin;j<end;j++) {
        const OraclePage *p=&history[j];
        if (p->cue) events[CUE]=1u;
        if (p->band>=2u) events[SLOW2]=1u;
        if (p->band==3u) events[SLOW4]=1u;
        if (p->retry) events[RETRY]=1u;
        if (p->step>*peak) *peak=p->step;
    }
}

static void record_expected(OracleStats *stats,
                            const unsigned events[ORACLE_EVENTS],
                            uint32_t peak) {
    ++stats->windows;
    for (unsigned k=0;k<ORACLE_EVENTS;k++)
        stats->events[k]+=(uint64_t)events[k];
    if (peak>stats->peak) stats->peak=peak;
}

static void compare_actual(const VhAudioListeningMarks *m,
                           const OracleStats expected[3]) {
    const OracleStats *a=&expected[A_MARK];
    const OracleStats *b=&expected[B_CONTROL];
    const OracleStats *all=&expected[ALL_PAGES];
    assert(m->manual_marks==a->windows);
    assert(m->control_marks==b->windows);
    assert(m->returned_pages==all->windows);
    assert(m->marks_near_switch==a->events[CUE]);
    assert(m->marks_near_wait_over_2x==a->events[SLOW2]);
    assert(m->marks_near_wait_over_4x==a->events[SLOW4]);
    assert(m->marks_near_retry==a->events[RETRY]);
    assert(m->peak_seam_near_mark==a->peak);
    assert(m->controls_near_switch==b->events[CUE]);
    assert(m->controls_near_wait_over_2x==b->events[SLOW2]);
    assert(m->controls_near_wait_over_4x==b->events[SLOW4]);
    assert(m->controls_near_retry==b->events[RETRY]);
    assert(m->peak_seam_near_control==b->peak);
    assert(m->windows_near_switch==all->events[CUE]);
    assert(m->windows_near_wait_over_2x==all->events[SLOW2]);
    assert(m->windows_near_wait_over_4x==all->events[SLOW4]);
    assert(m->windows_near_retry==all->events[RETRY]);
}

static void verify_live_window(const VhAudioListeningMarks *m,
                               size_t end, unsigned limit) {
    unsigned events[ORACLE_EVENTS];
    uint32_t peak=0u;
    reference_window(end,limit,events,&peak);
    VhListenWindow actual={0};
    assert(vh_audio_listening_window(m,limit,&actual)==0);
    assert(actual.scene_boundary==events[CUE]);
    assert(actual.over_2x==events[SLOW2]);
    assert(actual.over_4x==events[SLOW4]);
    assert(actual.retry==events[RETRY]);
    assert(actual.peak_step==peak);
}

int main(void) {
    VhAudioListeningMarks m={0};
    OracleStats expected[3]={{0}};
    uint32_t seed=UINT32_C(0x4C317EAD);

    for (size_t i=0;i<ORACLE_PAGES;i++) {
        seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);
        OraclePage *p=&history[i];
        /* Independently occurring events, including deliberately
         * adjacent first-window wrap boundaries on pages 31..33. */
        p->band=(i==31u || i%101u==9u) ? 3u :
                (i==32u || i%67u==7u) ? 2u :
                i%13u==3u ? 1u : 0u;
        p->cue=(unsigned)(i==1u || (i>1u && i%149u==0u));
        p->retry=(unsigned)(i==33u || (i>0u && i%181u==17u));
        p->step=i==0u ? 0u : (seed>>8)&65535u;
        assert(vh_audio_listening_observe(
            &m,p->band,p->cue,p->retry,p->step)==0);

        unsigned events[ORACLE_EVENTS];
        uint32_t peak=0u;
        reference_window(i+1u,VH_LISTEN_RECENT_PAGES,events,&peak);
        record_expected(&expected[ALL_PAGES],events,peak);

        /* Both A and B occur repeatedly, but not on the same page.
         * The exact mark choice is independent of production ring. */
        if (i%29u==2u || i==31u || i==33u) {
            assert(vh_audio_listening_mark(&m)==0);
            record_expected(&expected[A_MARK],events,peak);
        } else if (i%31u==9u || i==32u || i==34u) {
            assert(vh_audio_listening_control(&m)==0);
            record_expected(&expected[B_CONTROL],events,peak);
        }
        compare_actual(&m,expected);
        verify_live_window(&m,i+1u,VH_LISTEN_RECENT_PAGES);
        verify_live_window(&m,i+1u,VH_LISTEN_RECENT_PAGES-1u);
        assert(vh_audio_listening_verify(&m,(uint64_t)i+1u)==0);
    }

    assert(m.returned_pages==ORACLE_PAGES);
    assert(m.manual_marks>100u && m.control_marks>100u);
    /* No artificial permanent overlap: many windows have no event. */
    assert(expected[ALL_PAGES].events[CUE]>0u);
    assert(expected[ALL_PAGES].events[CUE]<ORACLE_PAGES);
    assert(expected[ALL_PAGES].events[SLOW4]>0u);
    assert(expected[ALL_PAGES].events[SLOW4]<ORACLE_PAGES);
    assert(expected[ALL_PAGES].events[RETRY]>0u);
    assert(expected[ALL_PAGES].events[RETRY]<ORACLE_PAGES);
    puts("audout A/B 4096-page independent lookback oracle: PASS");
    return 0;
}
