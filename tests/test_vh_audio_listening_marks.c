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
    assert(vh_audio_listening_control(&m)==-1);
    assert(vh_audio_listening_mark_kind(&m,2u)==-1);
    assert(vh_audio_listening_verify(&m,0u)==0);
    assert(vh_audio_listening_observe(&m,4u,0u,0u,0u,0u)==-1);
    assert(vh_audio_listening_observe(&m,0u,2u,0u,0u,0u)==-1);
    assert(vh_audio_listening_observe(&m,0u,0u,2u,0u,0u)==-1);
    assert(vh_audio_listening_observe(&m,0u,0u,0u,65536u,0u)==-1);
    assert(!m.returned_pages);

    /* First page has zero PCM predecessor seam. */
    assert(vh_audio_listening_observe(&m,0u,0u,0u,0u,0u)==0);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==1u && m.peak_seam_near_mark==0u);
    assert(!m.marks_near_switch && !m.marks_near_wait_over_2x);
    assert(m.returned_pages==1u && !m.windows_near_switch);
    assert(!m.windows_near_wait_over_2x);
    assert(!m.windows_near_wait_over_4x && !m.windows_near_retry);
    assert(vh_audio_listening_observe(&m,3u,1u,1u,4000u,1u)==0);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==2u);
    assert(m.marks_near_switch==1u);
    assert(m.marks_near_wait_over_2x==1u);
    assert(m.marks_near_wait_over_4x==1u);
    assert(m.marks_near_retry==1u);
    assert(m.peak_seam_near_mark==4000u);
    /* B shares the precise A look-back but has distinct counters. */
    assert(vh_audio_listening_control(&m)==0);
    assert(m.control_marks==1u && m.controls_near_switch==1u);
    assert(m.controls_near_wait_over_2x==1u);
    assert(m.controls_near_wait_over_4x==1u);
    assert(m.controls_near_retry==1u);
    assert(m.peak_seam_near_control==4000u);
    assert(m.manual_marks==2u);
    assert(m.windows_near_switch==1u);
    assert(m.windows_near_wait_over_2x==1u);
    assert(m.windows_near_wait_over_4x==1u);
    assert(m.windows_near_retry==1u);

    /* Fill 32 normal pages, evicting both older observations. */
    for (unsigned i=0;i<VH_LISTEN_RECENT_PAGES;i++)
        assert(vh_audio_listening_observe(&m,0u,0u,0u,42u,0u)==0);
    assert(m.returned_pages==VH_LISTEN_RECENT_PAGES+2u);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==3u);
    assert(vh_audio_listening_control(&m)==0);
    assert(m.control_marks==2u && m.controls_near_switch==1u);
    assert(m.controls_near_wait_over_2x==1u);
    assert(m.controls_near_wait_over_4x==1u);
    assert(m.controls_near_retry==1u);
    assert(m.peak_seam_near_control==4000u);
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
    assert(vh_audio_listening_control(&damaged)==-1);
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
    damaged=m;
    damaged.controls_near_wait_over_4x=
        damaged.controls_near_wait_over_2x+1u;
    assert(vh_audio_listening_verify(&damaged,m.returned_pages)==-1);
    damaged=m;
    damaged.controls_near_retry=damaged.control_marks+1u;
    assert(vh_audio_listening_verify(&damaged,m.returned_pages)==-1);
    damaged=m;
    damaged.control_marks=UINT64_MAX;
    const VhAudioListeningMarks guard=damaged;
    assert(vh_audio_listening_control(&damaged)==-1);
    assert(memcmp(&damaged,&guard,sizeof damaged)==0);
    /* A new 2..4x wait increments only its own baseline
     * (not >4x, cue switch or retry). */
    assert(vh_audio_listening_observe(&m,2u,0u,0u,2500u,1u)==0);
    assert(m.returned_pages==VH_LISTEN_RECENT_PAGES+3u);
    assert(m.windows_near_switch==VH_LISTEN_RECENT_PAGES);
    assert(m.windows_near_wait_over_2x==VH_LISTEN_RECENT_PAGES+1u);
    assert(m.windows_near_wait_over_4x==VH_LISTEN_RECENT_PAGES);
    assert(m.windows_near_retry==VH_LISTEN_RECENT_PAGES);
    assert(vh_audio_listening_mark(&m)==0);
    assert(m.manual_marks==4u);
    assert(m.marks_near_switch==1u && m.marks_near_wait_over_2x==2u);
    assert(m.marks_near_wait_over_4x==1u && m.marks_near_retry==1u);
    assert(vh_audio_listening_control(&m)==0);
    assert(m.control_marks==3u);
    assert(m.controls_near_switch==1u);
    assert(m.controls_near_wait_over_2x==2u);
    assert(m.controls_near_wait_over_4x==1u);
    assert(m.controls_near_retry==1u);
    assert(m.peak_seam_near_control==4000u);
    assert(m.manual_marks==4u);
    assert(m.dsp_over_pages==2u && m.dsp_wait_over_2x_pages==2u);
    assert(m.dsp_wait_over_4x_pages==1u);
    assert(m.marks_near_dsp_over==2u && m.controls_near_dsp_over==2u);
    assert(m.windows_near_dsp_over==VH_LISTEN_RECENT_PAGES+1u);
    assert(vh_audio_listening_verify_dsp_totals(&m,2u,2u,1u)==0);
    assert(vh_audio_listening_verify_dsp_totals(&m,2u,1u,1u)==-1);
    VhAudioListeningMarks broken_dsp=m;
    broken_dsp.recent[(m.returned_pages-1u)%VH_LISTEN_RECENT_PAGES]
        .dsp_over_budget=2u;
    assert(vh_audio_listening_verify(&broken_dsp,m.returned_pages)==-1);
    broken_dsp=m;
    broken_dsp.marks_near_dsp_wait_over_4x=
        broken_dsp.marks_near_dsp_wait_over_2x+1u;
    assert(vh_audio_listening_verify(&broken_dsp,m.returned_pages)==-1);
    assert(vh_audio_listening_verify(&m,m.returned_pages)==0);
    assert(vh_audio_listening_verify(NULL,0u)==-1);
    puts("manual listening marks: ring wrap, wait/switch/retry audit PASS");
    return 0;
}
