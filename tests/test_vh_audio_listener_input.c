/* Transaction tests for synthetic audout pages and A/B held states.
 * No Switch service, copyrighted music or audible-glitch claims.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "vh_audio_listener_input.h"

static void page(VhAudioListeningMarks *m,unsigned band,unsigned sw) {
    assert(vh_audio_listening_observe(m,band,sw,0u,120u)==0);
}
static void consistent(const VhAudioListeningMarks *m,
                       const VhAudioMarkButtons *g) {
    assert(vh_audio_listening_verify(m,m->returned_pages)==0);
    assert(vh_audio_mark_buttons_verify(
        g,m->returned_pages,m->manual_marks,m->control_marks)==0);
}
int main(void) {
    VhAudioListeningMarks m={0};
    VhAudioMarkButtons g={0};
    assert(vh_audio_listener_input_page(&g,&m,0u)==-1);
    assert(m.returned_pages==0u && g.polls==0u);

    page(&m,0u,0u);
    /* A poll on an initial disarmed gate is not an annotation. */
    assert(vh_audio_listener_input_page(&g,&m,0u)==0);
    consistent(&m,&g);
    page(&m,3u,1u);
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_A)==0);
    assert(m.manual_marks==1u && m.marks_near_wait_over_4x==1u);
    assert(m.marks_near_switch==1u && g.marks_a==1u);
    consistent(&m,&g);

    /* No second input sample for the same delivered logical page. */
    VhAudioMarkButtons before_g=g;
    VhAudioListeningMarks before_m=m;
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_B)==-1);
    assert(!memcmp(&g,&before_g,sizeof g));
    assert(!memcmp(&m,&before_m,sizeof m));

    page(&m,0u,0u);
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_A)==0);
    assert(m.manual_marks==1u && g.marks_a==1u); /* held A */
    page(&m,0u,0u);
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_CHORD)==0);
    assert(!m.control_marks); /* B added while A held: no B */
    page(&m,0u,0u);
    assert(vh_audio_listener_input_page(&g,&m,0u)==0);
    page(&m,0u,0u);
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_B)==0);
    assert(m.control_marks==1u && g.marks_b==1u);
    assert(m.controls_near_wait_over_4x==1u);
    consistent(&m,&g);

    /* Inject a corrupted ring observation. The marker rejects it,
     * and the gate must remain unchanged so no false accepted tag
     * can be reported after an interrupted/invalid probe. */
    page(&m,0u,0u);
    assert(vh_audio_listener_input_page(&g,&m,0u)==0); /* rearm */
    page(&m,0u,0u);
    m.recent[(m.returned_pages-1u)%VH_LISTEN_RECENT_PAGES].wait_band=4u;
    before_g=g;
    before_m=m;
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_A)==-1);
    assert(!memcmp(&g,&before_g,sizeof g));
    assert(!memcmp(&m,&before_m,sizeof m));
    m.recent[(m.returned_pages-1u)%VH_LISTEN_RECENT_PAGES].wait_band=0u;
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_A)==0);
    assert(m.manual_marks==2u && g.marks_a==2u);
    consistent(&m,&g);

    /* Simulate a saturated listening counter with an otherwise valid
     * ring. An attempted A may not partially increment gate counts.
     */
    page(&m,0u,0u);
    assert(vh_audio_listener_input_page(&g,&m,0u)==0);
    page(&m,0u,0u);
    const uint64_t old_marks=m.manual_marks;
    m.manual_marks=UINT64_MAX;
    before_g=g;
    before_m=m;
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_A)==-1);
    assert(!memcmp(&g,&before_g,sizeof g));
    assert(!memcmp(&m,&before_m,sizeof m));
    m.manual_marks=old_marks;
    assert(vh_audio_listener_input_page(&g,&m,VH_AUDIO_MARK_A)==0);
    assert(m.manual_marks==3u && g.marks_a==3u);
    consistent(&m,&g);

    /* Terminal/interrupted page: no input poll is committed.
     * Final cross-check must reject it rather than claim a full run.
     */
    page(&m,0u,0u);
    assert(vh_audio_mark_buttons_verify(
        &g,m.returned_pages,m.manual_marks,m.control_marks)==-1);
    before_g=g;
    before_m=m;
    assert(vh_audio_listener_input_page(&g,&m,4u)==-1);
    assert(!memcmp(&g,&before_g,sizeof g));
    assert(!memcmp(&m,&before_m,sizeof m));
    assert(vh_audio_listener_input_page(&g,&m,0u)==0);
    consistent(&m,&g);

    /* A gate whose poll clock jumps ahead cannot annotate this page. */
    VhAudioMarkButtons malformed=g;
    ++malformed.polls;
    before_g=malformed;
    before_m=m;
    assert(vh_audio_listener_input_page(&malformed,&m,0u)==-1);
    assert(!memcmp(&malformed,&before_g,sizeof malformed));
    assert(!memcmp(&m,&before_m,sizeof m));
    assert(vh_audio_listener_input_page(NULL,&m,0u)==-1);
    assert(vh_audio_listener_input_page(&g,NULL,0u)==-1);
    puts("audout A/B input transaction: failed annotations are atomic PASS");
    return 0;
}
