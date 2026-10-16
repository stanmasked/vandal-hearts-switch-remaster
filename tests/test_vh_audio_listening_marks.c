/* Synthetic audio-lookback and manual A-button annotation tests.
 * No sample buffers, libnx, console hardware or audible-glitch claims.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_listening_marks.h"

int main(void) {
    VhAudioListeningMarks m={0};
    assert(vh_audio_listening_mark(&m)==-1); /* no returned page */
    assert(vh_audio_listening_verify(&m,0u)==0);
    assert(vh_audio_listening_observe(&m,4u,0u,0u,0u)==-1);
    assert(vh_audio_listening_observe(&m,0u,2u,0u,0u)==-1);
    assert(vh_audio_listening_observe(&m,0u,0u,2u,0u)==-1);
    assert(vh_audio_listening_observe(&m,0u,0u,0u,65536u)==-1);
    assert(!m.returned_pages);

    /* First page has zero PCM predecessor seam. */
    assert(vh_audio_listening_observe(&m,0u,0u,0u,0u)==0);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==1u && m.peak_seam_near_mark==0u);
    assert(!m.marks_near_switch && !m.marks_near_wait_over_2x);
    assert(vh_audio_listening_observe(&m,3u,1u,1u,4000u)==0);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==2u);
    assert(m.marks_near_switch==1u);
    assert(m.marks_near_wait_over_2x==1u);
    assert(m.marks_near_wait_over_4x==1u);
    assert(m.marks_near_retry==1u);
    assert(m.peak_seam_near_mark==4000u);

    /* Fill 32 normal pages, evicting both older observations. */
    for (unsigned i=0;i<VH_LISTEN_RECENT_PAGES;i++)
        assert(vh_audio_listening_observe(&m,0u,0u,0u,42u)==0);
    assert(m.returned_pages==VH_LISTEN_RECENT_PAGES+2u);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==3u);
    assert(m.marks_near_switch==1u);
    assert(m.marks_near_wait_over_2x==1u);
    assert(m.marks_near_wait_over_4x==1u);
    assert(m.marks_near_retry==1u);
    assert(m.peak_seam_near_mark==4000u);
    assert(vh_audio_listening_verify(&m,m.returned_pages)==0);
    assert(vh_audio_listening_verify(&m,m.returned_pages-1u)==-1);

    /* A tampered ring slot cannot silently validate. */
    VhAudioListeningMarks damaged=m;
    damaged.recent[0].wait_band=4u;
    assert(vh_audio_listening_verify(&damaged,m.returned_pages)==-1);
    const VhAudioListeningMarks unchanged=damaged;
    assert(vh_audio_listening_mark(&damaged)==-1);
    assert(memcmp(&damaged,&unchanged,sizeof damaged)==0);
    damaged=m;
    damaged.marks_near_switch=damaged.manual_marks+1u;
    assert(vh_audio_listening_verify(&damaged,m.returned_pages)==-1);
    damaged=m;
    damaged.marks_near_wait_over_4x=
        damaged.marks_near_wait_over_2x+1u;
    assert(vh_audio_listening_verify(&damaged,m.returned_pages)==-1);
    assert(vh_audio_listening_verify(NULL,0u)==-1);
    puts("manual listening marks: ring wrap, wait/switch/retry audit PASS");
    return 0;
}
