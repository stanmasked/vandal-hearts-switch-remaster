#include <string.h>
/* Portable three-screen Switch audio evidence report test.
 * Full PCM accounting must never be equated with audible quality.
 */
#include <assert.h>
#include <stdio.h>
#include "vh_audio_report_pages.h"

/* Deterministic clock-only test: event-to-returned-descriptor latency,
 * NEVER time until speaker playback. Invalid clocks must not consume
 * the pending foreground state or increment the returned page count. */
static void test_first_pcm_after_home_tick_lag(void) {
    VhAudioAppletEvents e={0};
    assert(vh_audio_applet_record_at(NULL,VH_AUDIO_APPLET_RESUME,1u)==-1);
    assert(vh_audio_applet_page_returned_at(NULL,1u)==-1);
    assert(vh_audio_applet_page_returned_at(&e,50u)==0);
    assert(e.returned_pages==1u && e.timed_first_pages==0u);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_BACKGROUND,100u)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_FOREGROUND,1000u)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_RESUME,1020u)==0);
    assert(vh_audio_applet_verify(&e)==0 && e.timestamp_pending==1u);
    assert(vh_audio_applet_page_returned_at(&e,1440u)==1);
    assert(e.timed_first_pages==1u && e.first_pages_after_return==1u);
    assert(e.total_page_gap_ticks==440u && e.max_page_gap_ticks==440u);
    assert(!e.pending_return && !e.timestamp_pending);
    assert(vh_audio_applet_page_returned_at(&e,1500u)==0);
    assert(e.returned_pages==3u && e.total_page_gap_ticks==440u);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_BACKGROUND,2000u)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_FOREGROUND,3000u)==0);
    assert(vh_audio_applet_page_returned_at(&e,3800u)==1);
    assert(e.timed_first_pages==2u && e.total_page_gap_ticks==1240u);
    assert(e.max_page_gap_ticks==800u && vh_audio_applet_verify(&e)==0);

    /* Several returns without a PCM descriptor use the LATEST
     * recorded foreground tick, while older return is coalesced. */
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_BACKGROUND,3900u)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_FOREGROUND,4000u)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_BACKGROUND,4200u)==0);
    assert(vh_audio_applet_page_returned_at(&e,4250u)==0);
    assert(e.pending_return==1u && e.timed_first_pages==2u);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_FOREGROUND,4500u)==0);
    assert(e.coalesced_returns==1u && e.foreground_tick==4500u);
    assert(vh_audio_applet_page_returned_at(&e,5000u)==1);
    assert(e.timed_first_pages==3u && e.total_page_gap_ticks==1740u);
    assert(e.max_page_gap_ticks==800u && vh_audio_applet_verify(&e)==0);

    /* Untimed focus returns should count one observed page, but
     * must not counterfeit a zero-tick latency measurement. */
    assert(vh_audio_applet_record(&e,VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_FOREGROUND,0u)==0);
    assert(!e.timestamp_pending);
    assert(vh_audio_applet_page_returned_at(&e,6000u)==1);
    assert(e.first_pages_after_return==4u && e.timed_first_pages==3u);
    assert(e.total_page_gap_ticks==1740u && vh_audio_applet_verify(&e)==0);

    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_BACKGROUND,6500u)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_FOREGROUND,7000u)==0);
    VhAudioAppletEvents before=e;
    assert(vh_audio_applet_page_returned_at(&e,6900u)==-1);
    assert(!memcmp(&e,&before,sizeof e));
    assert(vh_audio_applet_page_returned_at(&e,0u)==-1);
    assert(!memcmp(&e,&before,sizeof e));
    assert(vh_audio_applet_page_returned_at(&e,7001u)==1);
    assert(e.total_page_gap_ticks==1741u && vh_audio_applet_verify(&e)==0);

    VhAudioAppletEvents corrupted=e;
    corrupted.total_page_gap_ticks=0u;
    assert(vh_audio_applet_verify(&corrupted)==-1);
    corrupted=e;
    corrupted.timed_first_pages=e.first_pages_after_return+1u;
    assert(vh_audio_applet_verify(&corrupted)==-1);
    corrupted=e;
    corrupted.timestamp_pending=1u;
    assert(vh_audio_applet_verify(&corrupted)==-1);

    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_BACKGROUND,8000u)==0);
    assert(vh_audio_applet_record_at(&e,VH_AUDIO_APPLET_FOREGROUND,9000u)==0);
    corrupted=e;
    corrupted.total_page_gap_ticks=UINT64_MAX;
    before=corrupted;
    assert(vh_audio_applet_page_returned_at(&corrupted,9001u)==-1);
    assert(!memcmp(&corrupted,&before,sizeof corrupted));
    corrupted=e;
    corrupted.timed_first_pages=UINT_MAX;
    before=corrupted;
    assert(vh_audio_applet_page_returned_at(&corrupted,9001u)==-1);
    assert(!memcmp(&corrupted,&before,sizeof corrupted));
}

int main(void) {
    test_first_pcm_after_home_tick_lag();
    unsigned page=0u;
    /* HOME/background and resume are observable lifecycle events,
     * not a proof of audible output or service recovery. */
    VhAudioAppletEvents focus={0};
    assert(vh_audio_applet_verify(&focus)==0);
    assert(vh_audio_applet_record(NULL,VH_AUDIO_APPLET_BACKGROUND)==-1);
    assert(vh_audio_applet_record(&focus,99u)==-1);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(focus.ignored_duplicates==1u && focus.returns==0u);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(focus.backgrounds==1u && focus.in_background==1u);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(focus.ignored_duplicates==2u && focus.backgrounds==1u);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_RESUME)==0);
    assert(focus.resumes==1u && focus.returns==0u);
    assert(vh_audio_applet_verify(&focus)==0);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(focus.returns==1u && !focus.in_background);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_RESUME)==0);
    assert(focus.resumes==2u && vh_audio_applet_verify(&focus)==0);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(focus.ignored_duplicates==3u);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(vh_audio_applet_record(&focus,VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(focus.backgrounds==2u && focus.returns==2u);
    VhAudioAppletEvents invalid=focus;
    invalid.returns=3u;
    assert(vh_audio_applet_verify(&invalid)==-1);
    invalid=focus;
    invalid.in_background=1u;
    assert(vh_audio_applet_verify(&invalid)==-1);
    invalid=focus;
    invalid.resumes=UINT_MAX;
    assert(vh_audio_applet_record(&invalid,VH_AUDIO_APPLET_RESUME)==-1);
    assert(invalid.resumes==UINT_MAX);
    invalid=focus;
    invalid.backgrounds=UINT_MAX;
    assert(vh_audio_applet_record(&invalid,VH_AUDIO_APPLET_BACKGROUND)==-1);
    assert(!invalid.in_background);
    invalid=focus;
    invalid.ignored_duplicates=UINT_MAX;
    assert(vh_audio_applet_record(&invalid,VH_AUDIO_APPLET_FOREGROUND)==-1);
    assert(invalid.ignored_duplicates==UINT_MAX);
    invalid=focus;
    invalid.in_background=1u;
    invalid.returns=UINT_MAX;
    assert(vh_audio_applet_record(&invalid,VH_AUDIO_APPLET_FOREGROUND)==-1);
    assert(invalid.in_background==1u);
    /* Correlate real foreground notifications with returned *PCM
     * descriptors*, not merely a resume event or a rendered frame. */
    VhAudioAppletEvents pages={0};
    assert(vh_audio_applet_page_returned(NULL)==-1);
    assert(vh_audio_applet_page_returned(&pages)==0);
    assert(pages.returned_pages==1u && pages.first_pages_after_return==0u);
    assert(vh_audio_applet_record(&pages,VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(vh_audio_applet_record(&pages,VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(pages.pending_return && pages.first_pages_after_return==0u);
    assert(vh_audio_applet_record(&pages,VH_AUDIO_APPLET_RESUME)==0);
    assert(pages.resumes==1u && pages.pending_return==1u);
    assert(vh_audio_applet_verify(&pages)==0);
    assert(vh_audio_applet_page_returned(&pages)==1);
    assert(!pages.pending_return && pages.first_pages_after_return==1u);
    assert(vh_audio_applet_page_returned(&pages)==0);
    assert(pages.first_pages_after_return==1u);
    assert(vh_audio_applet_record(&pages,VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(vh_audio_applet_record(&pages,VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(vh_audio_applet_record(&pages,VH_AUDIO_APPLET_BACKGROUND)==0);
    /* A returned descriptor during background must not be mislabelled
     * as foreground recovery even when an earlier return is pending. */
    assert(vh_audio_applet_page_returned(&pages)==0);
    assert(pages.pending_return && pages.first_pages_after_return==1u);
    assert(vh_audio_applet_record(&pages,VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(pages.returns==3u && pages.coalesced_returns==1u);
    assert(vh_audio_applet_verify(&pages)==0);
    assert(vh_audio_applet_page_returned(&pages)==1);
    assert(pages.returns==3u && pages.first_pages_after_return==2u &&
           !pages.pending_return && pages.coalesced_returns==1u);
    assert(vh_audio_applet_verify(&pages)==0);
    VhAudioAppletEvents corrupt=pages;
    corrupt.pending_return=1u;
    assert(vh_audio_applet_verify(&corrupt)==-1);
    corrupt=pages;
    corrupt.coalesced_returns=0u;
    assert(vh_audio_applet_verify(&corrupt)==-1);
    corrupt=pages;
    corrupt.first_pages_after_return=pages.returned_pages+1u;
    assert(vh_audio_applet_verify(&corrupt)==-1);
    corrupt=pages;
    corrupt.pending_return=2u;
    assert(vh_audio_applet_verify(&corrupt)==-1);
    corrupt=pages;
    corrupt.returned_pages=UINT_MAX;
    assert(vh_audio_applet_page_returned(&corrupt)==-1);
    assert(corrupt.returned_pages==UINT_MAX);
    corrupt=pages;
    corrupt.pending_return=1u;
    corrupt.first_pages_after_return=UINT_MAX;
    assert(vh_audio_applet_page_returned(&corrupt)==-1);
    assert(corrupt.returned_pages==pages.returned_pages);
    corrupt=(VhAudioAppletEvents){
        .backgrounds=3u,.returns=2u,.in_background=1u,
        .pending_return=1u,.coalesced_returns=UINT_MAX
    };
    assert(vh_audio_applet_record(&corrupt,VH_AUDIO_APPLET_FOREGROUND)==-1);
    assert(corrupt.in_background==1u && corrupt.returns==2u);
    /* HOME observation remains independent of audio report verdicts. */
    assert(vh_audio_report_evidence(1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
    /* Pending foreground with no returned descriptor is INCOMPLETE,
     * not full audio evidence; invalid accounting is always INVALID. */
    VhAudioManualResume focus_manual={0};
    assert(vh_audio_report_focus_evidence(&pages,&focus_manual,
                    1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
    VhAudioAppletEvents pending=pages;
    assert(vh_audio_applet_record(&pending,
                                 VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(vh_audio_applet_record(&pending,
                                 VH_AUDIO_APPLET_FOREGROUND)==0);
    assert(vh_audio_applet_verify(&pending)==0);
    assert(vh_audio_report_focus_evidence(&pending,&focus_manual,
                    1,0,0,0,0)==VH_AUDIO_REPORT_INCOMPLETE);
    assert(vh_audio_report_focus_evidence(&pending,&focus_manual,
                    0,0,0,0,0)==VH_AUDIO_REPORT_INCOMPLETE);
    assert(vh_audio_applet_page_returned(&pending)==1);
    assert(vh_audio_report_focus_evidence(&pending,&focus_manual,
                    1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
    assert(vh_audio_applet_record(&pending,
                                 VH_AUDIO_APPLET_BACKGROUND)==0);
    assert(vh_audio_report_focus_evidence(&pending,&focus_manual,
                    1,0,0,0,0)==VH_AUDIO_REPORT_INCOMPLETE);
    pending.backgrounds=0u; /* impossible underflow/accounting */
    assert(vh_audio_report_focus_evidence(&pending,&focus_manual,
                    1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    assert(vh_audio_report_focus_evidence(NULL,&focus_manual,
                    1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    assert(vh_audio_report_focus_evidence(&pages,NULL,
                    1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    assert(vh_audio_report_focus_evidence(&pages,&focus_manual,
                    1,1,0,0,0)==VH_AUDIO_REPORT_INVALID);
    assert(vh_audio_applet_verify(NULL)==-1);
    /* Successful host accounting is independent from HOME observation. */
    assert(vh_audio_report_evidence(1,0,0,0,0)==VH_AUDIO_REPORT_FULL);

    assert(vh_audio_report_evidence(1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
    assert(vh_audio_report_evidence(0,0,0,0,0)==VH_AUDIO_REPORT_INCOMPLETE);
    for (int bad=-1;bad<=2;bad++) {
        if (bad==0) continue;
        assert(vh_audio_report_evidence(1,bad,0,0,0)==VH_AUDIO_REPORT_INVALID);
        assert(vh_audio_report_evidence(1,0,bad,0,0)==VH_AUDIO_REPORT_INVALID);
        assert(vh_audio_report_evidence(1,0,0,bad,0)==VH_AUDIO_REPORT_INVALID);
        assert(vh_audio_report_evidence(1,0,0,0,bad)==VH_AUDIO_REPORT_INVALID);
    }
    assert(vh_audio_report_evidence(-1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    assert(vh_audio_report_evidence(2,0,0,0,0)==VH_AUDIO_REPORT_INVALID);

    /* Probe must not declare a clean full run when manual service
     * transactions are incomplete, over-counted, unsafe or mutated. */
    VhAudioManualResume manual={0};
    assert(vh_audio_manual_verify(NULL)==-1);
    assert(vh_audio_manual_verify(&manual)==0);
    assert(vh_audio_report_manual_evidence(
             &manual,1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
    assert(vh_audio_report_manual_evidence(
             &manual,0,0,0,0,0)==VH_AUDIO_REPORT_INCOMPLETE);
    assert(vh_audio_report_manual_evidence(
             NULL,1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    manual.quick_attempts=4u;
    manual.quick_ok=4u;
    manual.reopen_attempts=7u;
    manual.reopen_ok=7u;
    manual.ignored_chords=5u; /* intentional chords are not faults */
    assert(vh_audio_manual_verify(&manual)==0);
    assert(vh_audio_report_manual_evidence(
             &manual,1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
    manual.quick_ok=3u;
    assert(vh_audio_report_manual_evidence(
             &manual,1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    manual.quick_ok=5u; /* impossible excess success */
    assert(vh_audio_manual_verify(&manual)==-1);
    manual.quick_ok=4u;
    manual.reopen_ok=6u;
    assert(vh_audio_manual_verify(&manual)==-1);
    manual.reopen_ok=8u;
    assert(vh_audio_manual_verify(&manual)==-1);
    manual.reopen_ok=7u;
    manual.unsafe_requests=1u;
    assert(vh_audio_report_manual_evidence(
             &manual,1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    manual.unsafe_requests=0u;
    manual.state_mismatches=1u;
    assert(vh_audio_manual_verify(&manual)==-1);
    manual.state_mismatches=0u;
    assert(vh_audio_manual_verify(&manual)==0);
    assert(vh_audio_report_manual_evidence(
             &manual,-1,0,0,0,0)==VH_AUDIO_REPORT_INVALID);
    assert(vh_audio_report_manual_evidence(
             &manual,1,0,0,1,0)==VH_AUDIO_REPORT_INVALID);

    /* Test all normalized X/Y chord edge combinations, including a
     * second rising key while the other key remains held. */
    assert(vh_audio_manual_select(0u,0u)==0u);
    assert(vh_audio_manual_select(VH_AUDIO_MANUAL_X,
                                  VH_AUDIO_MANUAL_X)==VH_AUDIO_MANUAL_X);
    assert(vh_audio_manual_select(VH_AUDIO_MANUAL_Y,
                                  VH_AUDIO_MANUAL_Y)==VH_AUDIO_MANUAL_Y);
    assert(vh_audio_manual_select(
             VH_AUDIO_MANUAL_X|VH_AUDIO_MANUAL_Y,
             VH_AUDIO_MANUAL_X|VH_AUDIO_MANUAL_Y)==VH_AUDIO_MANUAL_IGNORE);
    assert(vh_audio_manual_select(VH_AUDIO_MANUAL_X,
                  VH_AUDIO_MANUAL_X|VH_AUDIO_MANUAL_Y)==VH_AUDIO_MANUAL_IGNORE);
    assert(vh_audio_manual_select(VH_AUDIO_MANUAL_Y,
                  VH_AUDIO_MANUAL_X|VH_AUDIO_MANUAL_Y)==VH_AUDIO_MANUAL_IGNORE);
    assert(vh_audio_manual_select(4u,4u)==0u);
    assert(vh_audio_manual_select(VH_AUDIO_MANUAL_X,4u)==0u);

    assert(vh_audio_report_navigate(&page,VH_AUDIO_REPORT_NEXT)==0);
    assert(page==1u);
    assert(vh_audio_report_navigate(&page,VH_AUDIO_REPORT_NEXT)==0);
    assert(page==2u);
    assert(vh_audio_report_navigate(&page,VH_AUDIO_REPORT_NEXT)==0);
    assert(page==0u);
    assert(vh_audio_report_navigate(&page,VH_AUDIO_REPORT_PREV)==0);
    assert(page==2u);
    assert(vh_audio_report_navigate(&page,VH_AUDIO_REPORT_PREV|
        VH_AUDIO_REPORT_NEXT)==0);
    assert(page==2u);
    assert(vh_audio_report_navigate(&page,VH_AUDIO_REPORT_QUIT|
        VH_AUDIO_REPORT_NEXT)==1);
    assert(page==2u);
    assert(vh_audio_report_navigate(&page,8u)==-1);
    assert(page==2u);
    assert(vh_audio_report_navigate(NULL,0u)==-1);
    page=VH_AUDIO_REPORT_PAGE_COUNT;
    assert(vh_audio_report_navigate(&page,VH_AUDIO_REPORT_NEXT)==-1);
    assert(page==VH_AUDIO_REPORT_PAGE_COUNT);
    puts("Switch audio report pages: navigation and verdict PASS");
    return 0;
}
