/* Portable three-screen Switch audio evidence report test.
 * Full PCM accounting must never be equated with audible quality.
 */
#include <assert.h>
#include <stdio.h>
#include "vh_audio_report_pages.h"

int main(void) {
    unsigned page=0u;
    assert(vh_audio_report_evidence(1,0,0,0)==VH_AUDIO_REPORT_FULL);
    assert(vh_audio_report_evidence(0,0,0,0)==VH_AUDIO_REPORT_INCOMPLETE);
    for (int bad=-1;bad<=2;bad++) {
        if (bad==0) continue;
        assert(vh_audio_report_evidence(1,bad,0,0)==VH_AUDIO_REPORT_INVALID);
        assert(vh_audio_report_evidence(1,0,bad,0)==VH_AUDIO_REPORT_INVALID);
        assert(vh_audio_report_evidence(1,0,0,bad)==VH_AUDIO_REPORT_INVALID);
    }
    assert(vh_audio_report_evidence(-1,0,0,0)==VH_AUDIO_REPORT_INVALID);
    assert(vh_audio_report_evidence(2,0,0,0)==VH_AUDIO_REPORT_INVALID);
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
