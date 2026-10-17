/* Portable three-screen Switch audio evidence report test.
 * Full PCM accounting must never be equated with audible quality.
 */
#include <assert.h>
#include <stdio.h>
#include "vh_audio_report_pages.h"

int main(void) {
    unsigned page=0u;
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
