/* Portable three-screen Switch audio evidence report test.
 * Full PCM accounting must never be equated with audible quality.
 */
#include <assert.h>
#include <stdio.h>
#include "vh_audio_report_pages.h"

int main(void) {
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
