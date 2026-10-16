/* Synthetic held-button samples, not a physical hardware audio test. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_mark_buttons.h"
int main(void) {
    VhAudioMarkButtons s={0};
    unsigned event=55u;
    assert(vh_audio_mark_buttons_verify(&s,0u,0u,0u)==0);
    /* Input already held on probe startup must not count. */
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_A,&event)==0);
    assert(event==0u && !s.armed && !s.marks_a);
    assert(vh_audio_mark_buttons_sample(&s,0u,&event)==0);
    assert(event==0u && s.armed);
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_A,&event)==0);
    assert(event==VH_AUDIO_MARK_A && s.marks_a==1u && !s.armed);
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_A,&event)==0);
    assert(event==0u && s.marks_a==1u);
    /* B pressed while A HELD does NOT create B control. */
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_CHORD,&event)==0);
    assert(event==0u && !s.marks_b && !s.rejected_chords);
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_B,&event)==0);
    assert(event==0u && !s.marks_b);
    assert(vh_audio_mark_buttons_sample(&s,0u,&event)==0);
    assert(event==0u && s.armed);
    /* Simultaneous A+B consumes armed release cycle. */
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_CHORD,&event)==0);
    assert(event==0u && s.rejected_chords==1u && !s.armed);
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_B,&event)==0);
    assert(event==0u && !s.marks_b);
    assert(vh_audio_mark_buttons_sample(&s,0u,&event)==0);
    assert(vh_audio_mark_buttons_sample(&s,VH_AUDIO_MARK_B,&event)==0);
    assert(event==VH_AUDIO_MARK_B && s.marks_b==1u);
    assert(vh_audio_mark_buttons_verify(&s,s.polls,1u,1u)==0);
    assert(vh_audio_mark_buttons_verify(&s,s.polls,1u,0u)==-1);
    assert(vh_audio_mark_buttons_verify(&s,s.polls+1u,1u,1u)==-1);
    const VhAudioMarkButtons snapshot=s;
    event=77u;
    assert(vh_audio_mark_buttons_sample(&s,4u,&event)==-1);
    assert(event==77u && memcmp(&s,&snapshot,sizeof s)==0);
    assert(vh_audio_mark_buttons_sample(&s,0u,NULL)==-1);
    assert(memcmp(&s,&snapshot,sizeof s)==0);
    VhAudioMarkButtons bad=s;
    bad.armed=2u;
    assert(vh_audio_mark_buttons_sample(&bad,0u,&event)==-1);
    assert(vh_audio_mark_buttons_verify(&bad,s.polls,1u,1u)==-1);
    bad=s; bad.marks_a=s.polls; bad.marks_b=2u;
    assert(vh_audio_mark_buttons_verify(&bad,s.polls,bad.marks_a,2u)==-1);
    bad=s; bad.polls=UINT64_MAX;
    const VhAudioMarkButtons saturated=bad;
    assert(vh_audio_mark_buttons_sample(&bad,0u,&event)==-1);
    assert(memcmp(&bad,&saturated,sizeof bad)==0);
    bad=s; bad.armed=1u; bad.marks_a=UINT64_MAX;
    const VhAudioMarkButtons full=bad;
    assert(vh_audio_mark_buttons_sample(&bad,VH_AUDIO_MARK_A,&event)==-1);
    assert(memcmp(&bad,&full,sizeof bad)==0);
    assert(vh_audio_mark_buttons_sample(NULL,0u,&event)==-1);
    assert(vh_audio_mark_buttons_verify(NULL,0u,0u,0u)==-1);
    puts("Switch A/B held-release annotation gate: PASS");
    return 0;
}
