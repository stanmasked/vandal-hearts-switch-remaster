/* Event-sequence tests for console-only, observation-only HOME telemetry.
 * All events here are HOST fixtures; they cannot demonstrate real HOME.
 */
#include <assert.h>
#include <limits.h>
#include <stdatomic.h>
#include <stdio.h>
#include "vh_audio_focus_trace.h"

static void assert_counts(VhAudioFocusTrace *t,unsigned pages,
                          unsigned b,unsigned f,unsigned r,
                          unsigned phase,int post_pcm) {
    const VhAudioFocusObservation o=vh_audio_focus_trace_observe(t,pages);
    assert(o.backgrounds==b);
    assert(o.foreground_returns==f);
    assert(o.resumes==r);
    assert(o.phase==phase);
    assert(o.post_return_pcm==post_pcm);
}

static void test_missing_and_duplicate_focus_notifications(void) {
    VhAudioFocusTrace t;
    vh_audio_focus_trace_init(&t);
    assert_counts(&t,0,0,0,0,VH_FOCUS_NONE,0);

    /* InFocus with no prior Background cannot look like a HOME return. */
    vh_audio_focus_trace_foreground(&t,11);
    assert_counts(&t,12,0,0,0,VH_FOCUS_NONE,0);
    vh_audio_focus_trace_background(&t);
    vh_audio_focus_trace_background(&t);
    assert_counts(&t,18,1,0,0,VH_FOCUS_BACKGROUND,0);

    vh_audio_focus_trace_foreground(&t,18);
    assert_counts(&t,18,1,1,0,VH_FOCUS_RETURNED,0);
    vh_audio_focus_trace_foreground(&t,18);
    assert_counts(&t,19,1,1,0,VH_FOCUS_RETURNED,1);
    vh_audio_focus_trace_resume(&t);
    assert_counts(&t,19,1,1,1,VH_FOCUS_RETURNED,1);
}

static void test_second_cycle_clears_old_pcm_proof(void) {
    VhAudioFocusTrace t;
    vh_audio_focus_trace_init(&t);
    vh_audio_focus_trace_background(&t);
    vh_audio_focus_trace_foreground(&t,20);
    assert_counts(&t,21,1,1,0,VH_FOCUS_RETURNED,1);

    /* An already-returned page from the previous cycle must NOT
     * count as proof after the next HOME/background cycle. */
    vh_audio_focus_trace_background(&t);
    assert_counts(&t,99,2,1,0,VH_FOCUS_BACKGROUND,0);
    vh_audio_focus_trace_background(&t);
    assert_counts(&t,99,2,1,0,VH_FOCUS_BACKGROUND,0);
    vh_audio_focus_trace_resume(&t);
    assert_counts(&t,99,2,1,1,VH_FOCUS_BACKGROUND,0);
    vh_audio_focus_trace_foreground(&t,99);
    assert_counts(&t,99,2,2,1,VH_FOCUS_RETURNED,0);
    assert_counts(&t,100,2,2,1,VH_FOCUS_RETURNED,1);
    assert_counts(&t,101,2,2,1,VH_FOCUS_RETURNED,1);
}

static void test_separate_resume_is_not_foreground(void) {
    VhAudioFocusTrace t;
    vh_audio_focus_trace_init(&t);
    vh_audio_focus_trace_resume(&t);
    vh_audio_focus_trace_resume(&t);
    assert_counts(&t,777,0,0,2,VH_FOCUS_NONE,0);
    vh_audio_focus_trace_background(&t);
    vh_audio_focus_trace_resume(&t);
    assert_counts(&t,778,1,0,3,VH_FOCUS_BACKGROUND,0);
}

static void test_no_wrap_or_stale_progress(void) {
    VhAudioFocusTrace t;
    vh_audio_focus_trace_init(&t);
    atomic_store(&t.backgrounds,UINT_MAX);
    atomic_store(&t.foreground_returns,UINT_MAX);
    atomic_store(&t.resumes,UINT_MAX);
    vh_audio_focus_trace_background(&t);
    vh_audio_focus_trace_foreground(&t,UINT_MAX);
    vh_audio_focus_trace_resume(&t);
    const VhAudioFocusObservation o=vh_audio_focus_trace_observe(&t,1);
    assert(o.backgrounds==UINT_MAX);
    assert(o.foreground_returns==UINT_MAX);
    assert(o.resumes==UINT_MAX);
    assert(o.pages_at_return==UINT_MAX);
    assert(o.post_return_pcm==0);
}

int main(void) {
    test_missing_and_duplicate_focus_notifications();
    test_second_cycle_clears_old_pcm_proof();
    test_separate_resume_is_not_foreground();
    test_no_wrap_or_stale_progress();
    puts("focus trace: duplicate-safe real-event state logic PASS (host fixtures)");
    return 0;
}
