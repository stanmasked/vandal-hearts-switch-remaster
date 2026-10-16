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
    assert(m.returned_pages==1u && !m.windows_near_switch);
    assert(!m.windows_near_wait_over_2x);
    assert(!m.windows_near_wait_over_4x && !m.windows_near_retry);
    assert(vh_audio_listening_observe(&m,3u,1u,1u,4000u)==0);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==2u);
    assert(m.marks_near_switch==1u);
    assert(m.marks_near_wait_over_2x==1u);
    assert(m.marks_near_wait_over_4x==1u);
    assert(m.marks_near_retry==1u);
    assert(m.peak_seam_near_mark==4000u);
    assert(m.windows_near_switch==1u);
    assert(m.windows_near_wait_over_2x==1u);
    assert(m.windows_near_wait_over_4x==1u);
    assert(m.windows_near_retry==1u);

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
    /* The event in page index 1 occurs in the next 32 windows
     * exactly once per window, then expires at index 33. */
    assert(m.windows_near_switch==VH_LISTEN_RECENT_PAGES);
    assert(m.windows_near_wait_over_2x==VH_LISTEN_RECENT_PAGES);
    assert(m.windows_near_wait_over_4x==VH_LISTEN_RECENT_PAGES);
    assert(m.windows_near_retry==VH_LISTEN_RECENT_PAGES);
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
    damaged=m;
    damaged.windows_near_switch=damaged.returned_pages+1u;
    assert(vh_audio_listening_verify(&damaged,m.returned_pages)==-1);
    damaged=m;
    damaged.windows_near_wait_over_4x=
        damaged.windows_near_wait_over_2x+1u;
    assert(vh_audio_listening_verify(&damaged,m.returned_pages)==-1);
    /* A new 2..4x wait increments only its own baseline
     * (not >4x, cue switch or retry). */
    assert(vh_audio_listening_observe(&m,2u,0u,0u,2500u)==0);
    assert(m.returned_pages==VH_LISTEN_RECENT_PAGES+3u);
    assert(m.windows_near_switch==VH_LISTEN_RECENT_PAGES);
    assert(m.windows_near_wait_over_2x==VH_LISTEN_RECENT_PAGES+1u);
    assert(m.windows_near_wait_over_4x==VH_LISTEN_RECENT_PAGES);
    assert(m.windows_near_retry==VH_LISTEN_RECENT_PAGES);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==4u);
    assert(m.marks_near_switch==1u && m.marks_near_wait_over_2x==2u);
    assert(m.marks_near_wait_over_4x==1u && m.marks_near_retry==1u);
    assert(vh_audio_listening_verify(&m,m.returned_pages)==0);
    assert(vh_audio_listening_verify(NULL,0u)==-1);
    puts("manual listening marks: ring wrap, wait/switch/retry audit PASS");
    return 0;
}
