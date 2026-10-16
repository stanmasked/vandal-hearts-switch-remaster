/* Fault-injected output restart: never re-render SEQ, SPU or resampler
 * while retrying an immutable 48-kHz PCM page. Host only, no libnx.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_output_recovery.h"
#include "vh_audio_resample.h"
#include "vh_native_seq.h"

typedef struct {
    unsigned opened, playing, failures_left, submissions, accepted;
    unsigned opens, closes, stops, starts, attempts_this_page;
    int fail_stop, fail_open, fail_start;
    unsigned mismatched_returns_left, null_returns_left;
    int owned_descriptor, foreign_descriptor;
    const int16_t *page_pointer;
    size_t page_frames;
    uint64_t page_hash, checksum;
    VhAudioSubmitTiming timing;
} Mock;

static uint64_t hash_page(const int16_t *pcm, size_t frames) {
    uint64_t h=UINT64_C(1469598103934665603);
    for (size_t i=0;i<frames*2u;i++) {
        h^=(uint16_t)pcm[i];
        h*=UINT64_C(1099511628211);
    }
    return h;
}
static int submit(void *ctx,const int16_t *pcm,size_t frames) {
    Mock *m=ctx;
    assert(m->opened && m->playing && pcm && frames);
    const uint64_t hash=hash_page(pcm,frames);
    if (!m->attempts_this_page) {
        m->page_pointer=pcm;
        m->page_frames=frames;
        m->page_hash=hash;
    } else {
        assert(m->page_pointer==pcm);
        assert(m->page_frames==frames && m->page_hash==hash);
    }
    ++m->attempts_this_page;
    ++m->submissions;
    /* Fake backend latency, not elapsed wall-clock CI time. One
     * record per raw attempt, including retries and failures.
     */
    const uint64_t waited=(m->submissions%5u==0u)
        ? 250000u : 110000u;
    if (m->failures_left) {
        --m->failures_left;
        assert(vh_audio_output_record_submit_timing(
            &m->timing,waited,19200000u,frames,0)==0);
        return -1;
    }
    /* Simulate a successful libnx return with a wrong (or missing)
     * descriptor. Never permit page reuse until the matching buffer
     * is released, even though the underlying API reported success.
     */
    const void *returned=&m->owned_descriptor;
    if (m->mismatched_returns_left) {
        --m->mismatched_returns_left;
        returned=&m->foreign_descriptor;
    } else if (m->null_returns_left) {
        --m->null_returns_left;
        returned=NULL;
    }
    const int returned_ours=
        vh_audio_output_page_returned(&m->owned_descriptor,returned);
    assert(vh_audio_output_record_submit_timing(
        &m->timing,waited,19200000u,frames,returned_ours)==0);
    if (!returned_ours) return -1;
    ++m->accepted;
    m->checksum=(m->checksum ^ hash)*UINT64_C(1099511628211);
    return 0;
}
static int stop(void *ctx) {
    Mock *m=ctx;
    ++m->stops;
    if (m->fail_stop) return -1;
    m->playing=0;
    return 0;
}
static void close_device(void *ctx) {
    Mock *m=ctx;
    assert(!m->playing);
    ++m->closes;
    m->opened=0;
}
static int open_device(void *ctx) {
    Mock *m=ctx;
    ++m->opens;
    if (m->fail_open) return -1;
    m->opened=1;
    return 0;
}
static int start(void *ctx) {
    Mock *m=ctx;
    ++m->starts;
    if (m->fail_start) return -1;
    assert(m->opened && !m->playing);
    m->playing=1;
    return 0;
}
static VhAudioOutputOps callbacks(Mock *m) {
    const VhAudioOutputOps ops={
        m,submit,stop,close_device,open_device,start
    };
    return ops;
}
static void begin_page(Mock *m,unsigned failures) {
    m->failures_left=failures;
    m->attempts_this_page=0;
    m->page_pointer=NULL;
    m->page_frames=0;
    m->page_hash=0;
}
static const uint8_t song[]={
    'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
    0,0xc0,7,0,0x90,60,110,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static int16_t sample[128], alternate_sample[128];
static int16_t src[512u*2u], dst[640u*2u];
static VhSpuReverb history_before_switch;
static VhNativeSpu spu;
static VhNativeSeq seq;
static VhAudioResample resampler;
static int resolve(void *ctx,unsigned program,unsigned note,
                   unsigned velocity,unsigned volume,unsigned pan,
                   VhSeqTone *out) {
    (void)velocity;(void)volume;(void)pan;
    if (!out || program!=7u || note!=60u) return -1;
    memset(out,0,sizeof *out);
    out->pcm=ctx ? (const int16_t *)ctx : sample;
    out->frames=128u;
    out->loop_start=0;
    out->loop_end=128;
    out->pitch_step=4096u;
    out->adsr1=15;
    out->gain_left=.7f;
    out->gain_right=.4f;
    out->reverb_send=1;
    return 0;
}
int main(void) {
    Mock device={.opened=1,.playing=1,
                 .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps ops=callbacks(&device);
    VhAudioOutputRecovery stats={0};
    /* Deterministic synthetic timer: distinguishes expected blocking
     * page waits from failed backend calls, without sleeping in CI.
     * The page budget at 19.2 MHz / 48 kHz for 576 frames is 230400.
     */
    VhAudioSubmitTiming timing={0};
    const uint64_t freq=UINT64_C(19200000);
    assert(vh_audio_output_record_submit_timing(
               &timing,100000u,freq,576u,1)==0);
    assert(vh_audio_output_record_submit_timing(
               &timing,240000u,freq,576u,0)==0);
    assert(vh_audio_output_record_submit_timing(
               &timing,230400u,freq,576u,1)==0);
    assert(timing.calls==3u);
    assert(timing.total_ticks==570400u);
    assert(timing.max_ticks==240000u);
    assert(timing.waits_longer_than_page==1u);
    assert(timing.failed_submissions==1u);
    assert(vh_audio_output_ticks_to_us(240000u,freq)==12500u);
    assert(vh_audio_output_ticks_to_us(freq,freq)==1000000u);
    assert(vh_audio_output_ticks_to_us(UINT64_MAX,1u)==UINT64_MAX);
    assert(vh_audio_output_ticks_to_us(100u,0u)==0u);
    const VhAudioSubmitTiming stable=timing;
    assert(vh_audio_output_record_submit_timing(
               NULL,10u,freq,576u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,0u,576u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,0u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,VH_AUDIO_RESAMPLE_MAX_FRAMES+1u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,UINT64_MAX,576u,1)==-1);
    assert(!memcmp(&timing,&stable,sizeof timing));
    timing.calls=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,576u,1)==-1);
    timing=stable;
    timing.total_ticks=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,1u,freq,576u,1)==-1);
    timing=stable;
    timing.failed_submissions=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,576u,0)==-1);
    timing=stable;
    timing.waits_longer_than_page=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,240000u,freq,576u,1)==-1);

    /* Per-logical-page wait grouping; retries count as ONE accepted
     * page and their raw blocking ticks are accumulated together.
     */
    VhAudioSceneWaits grouping={0};
    const VhAudioSubmitTiming first_before={0};
    const VhAudioSubmitTiming first_after={
        .calls=2u, .total_ticks=340000u,
        .waits_longer_than_page=1u, .failed_submissions=1u
    };
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,1)==0);
    assert(grouping.first_after_switch.pages==1u);
    assert(grouping.first_after_switch.total_ticks==340000u);
    assert(grouping.first_after_switch.peak_page_ticks==340000u);
    assert(grouping.first_after_switch.slow_pages==1u);
    assert(grouping.first_after_switch.retried_pages==1u);
    assert(grouping.first_after_switch.failed_pages==0u);
    const VhAudioSubmitTiming second_after={
        .calls=3u, .total_ticks=460000u,
        .waits_longer_than_page=1u, .failed_submissions=1u
    };
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_after,&second_after,freq,576u,0,1)==0);
    assert(grouping.ordinary.pages==1u);
    assert(grouping.ordinary.total_ticks==120000u);
    assert(grouping.ordinary.slow_pages==0u);
    assert(grouping.ordinary.retried_pages==0u);
    const VhAudioSubmitTiming failed_after={
        .calls=4u, .total_ticks=510000u,
        .waits_longer_than_page=1u, .failed_submissions=2u
    };
    assert(vh_audio_output_record_scene_page(
        &grouping,&second_after,&failed_after,freq,576u,1,0)==0);
    assert(grouping.first_after_switch.pages==2u);
    assert(grouping.first_after_switch.failed_pages==1u);
    assert(grouping.first_after_switch.total_ticks==390000u);
    const VhAudioSceneWaits fixed_grouping=grouping;
    assert(vh_audio_output_record_scene_page(
        NULL,&first_before,&first_after,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,NULL,&first_after,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,NULL,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_after,&first_before,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,0u,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,0u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,
        VH_AUDIO_RESAMPLE_MAX_FRAMES+1u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,0)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,UINT64_MAX,576u,1,1)==-1);
    VhAudioSubmitTiming too_many=first_after;
    too_many.calls=VH_AUDIO_OUTPUT_RESTART_LIMIT+2u;
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&too_many,freq,576u,1,1)==-1);
    assert(!memcmp(&grouping,&fixed_grouping,sizeof grouping));
    grouping.first_after_switch.pages=UINT64_MAX;
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,1)==-1);
    grouping=fixed_grouping;
    grouping.first_after_switch.total_ticks=UINT64_MAX;
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,1)==-1);
    grouping=fixed_grouping;

    assert(vh_audio_output_submit_recover(NULL,&stats,dst,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,NULL,dst,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,NULL,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,0u)==-1);
    assert(vh_audio_output_submit_recover(
               &ops,&stats,dst,VH_AUDIO_RESAMPLE_MAX_FRAMES+1u)==-1);
    assert(device.submissions==0u && stats.pages_submitted==0u);
    /* Identity contract used by both native libnx probes: a service
     * success with NULL or a foreign descriptor is NOT page release. */
    int owned_page=1, foreign_page=2;
    assert(vh_audio_output_page_returned(&owned_page,&owned_page));
    assert(!vh_audio_output_page_returned(&owned_page,&foreign_page));
    assert(!vh_audio_output_page_returned(&owned_page,NULL));
    assert(!vh_audio_output_page_returned(NULL,NULL));
    for (unsigned form=0;form<2u;form++) {
        Mock wrong={.opened=1,.playing=1};
        VhAudioOutputOps wrong_ops=callbacks(&wrong);
        VhAudioOutputRecovery wrong_stats={0};
        for (unsigned i=0;i<64u;i++) dst[i]=(int16_t)i;
        const uint64_t original_hash=hash_page(dst,32u);
        begin_page(&wrong,0u);
        if (form==0u) wrong.mismatched_returns_left=1u;
        else wrong.null_returns_left=1u;
        assert(vh_audio_output_submit_recover(
                   &wrong_ops,&wrong_stats,dst,32u)==0);
        assert(wrong_stats.pages_submitted==1u);
        assert(wrong_stats.frames_submitted==32u);
        assert(wrong_stats.submit_failures==1u);
        assert(wrong_stats.restart_attempts==1u);
        assert(wrong_stats.recoveries==1u);
        assert(wrong.submissions==2u && wrong.accepted==1u);
        assert(wrong.opens==1u && wrong.closes==1u &&
               wrong.stops==1u && wrong.starts==1u);
        assert(hash_page(dst,32u)==original_hash);
        assert(wrong.page_pointer==dst && wrong.page_frames==32u);
        assert(wrong.page_hash==original_hash);
    }
    /* Repeated foreign released pointers never grant ownership of the
     * caller's page. Exhausting two restarts must stop the session and
     * return failure, leaving the entire prepared page untouched.
     */
    Mock never_returned={.opened=1,.playing=1};
    VhAudioOutputOps no_return_ops=callbacks(&never_returned);
    VhAudioOutputRecovery no_return_stats={0};
    begin_page(&never_returned,0u);
    never_returned.mismatched_returns_left=
        VH_AUDIO_OUTPUT_RESTART_LIMIT+1u;
    const uint64_t guarded_hash=hash_page(dst,32u);
    assert(vh_audio_output_submit_recover(&no_return_ops,&no_return_stats,
                                          dst,32u)==-1);
    assert(no_return_stats.pages_submitted==0u);
    assert(no_return_stats.frames_submitted==0u);
    assert(no_return_stats.submit_failures==
           VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    assert(no_return_stats.restart_attempts==
           VH_AUDIO_OUTPUT_RESTART_LIMIT);
    assert(never_returned.accepted==0u);
    assert(never_returned.submissions==VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    assert(never_returned.timing.calls==never_returned.submissions);
    assert(never_returned.timing.failed_submissions==
           never_returned.submissions);
    assert(hash_page(dst,32u)==guarded_hash);
    for(unsigned i=0;i<128u;i++)
        sample[i]=(int16_t)((int)i*113-7000);
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,resolve,NULL,0)==0);
    /* Independent expected 48-kHz stream fingerprint: backend restarts
     * must not duplicate, drop or reorder any accepted PCM page.
     */
    uint64_t expected_checksum=UINT64_C(1469598103934665603);
    uint64_t expected_frames=0;
    unsigned expected_failures=0,expected_recovered_pages=0;
    for (unsigned block=0;block<64u;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
            &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        expected_checksum=(expected_checksum ^ hash_page(dst,frames)) *
                          UINT64_C(1099511628211);
        expected_frames+=frames;
        const uint64_t old_spu=spu.frames_rendered;
        const uint64_t old_in=resampler.input_frames;
        const uint64_t old_tick=resampler.next_output_tick;
        const uint64_t old_notes=seq.note_ons;
        const unsigned failures=(block%17u==5u)?2u:
                                (block%11u==3u)?1u:0u;
        expected_failures+=failures;
        if(failures) ++expected_recovered_pages;
        begin_page(&device,failures);
        assert(vh_audio_output_submit_recover(
            &ops,&stats,dst,frames)==0);
        assert(device.attempts_this_page==failures+1u);
        assert(stats.pages_submitted==block+1u);
        assert(spu.frames_rendered==old_spu);
        assert(resampler.input_frames==old_in);
        assert(resampler.next_output_tick==old_tick);
        assert(seq.note_ons==old_notes);
        assert(old_in==(uint64_t)(block+1u)*512u);
    }
    assert(device.accepted==64u);
    assert(device.checksum==expected_checksum);
    assert(stats.frames_submitted==expected_frames);
    assert(stats.frames_submitted==resampler.next_output_tick/44100u);
    assert(stats.pages_submitted==64u);
    assert(stats.recoveries==expected_recovered_pages);
    assert(stats.submit_failures==expected_failures);
    assert(stats.restart_attempts==expected_failures);
    assert(device.submissions==64u+expected_failures);
    assert(expected_recovered_pages>0u && expected_failures>0u);

    /* Three failed submissions exceed the two permitted restarts.
     * An external caller can later submit the same prepared page again,
     * but no SEQ/SPU/resampling is performed by the recovery helper.
     */
    const uint64_t old_clock=spu.frames_rendered;
    const uint64_t old_input=resampler.input_frames;
    const uint64_t old_pages=stats.pages_submitted;
    const uint64_t page_hash=hash_page(dst,557u);
    begin_page(&device,3u);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==-1);
    assert(device.attempts_this_page==3u);
    assert(stats.pages_submitted==old_pages);
    assert(hash_page(dst,557u)==page_hash);
    assert(spu.frames_rendered==old_clock);
    assert(resampler.input_frames==old_input);
    begin_page(&device,0u);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==0);
    assert(stats.pages_submitted==old_pages+1u);

    /* Restart failure must never mark the rejected page as accepted. */
    begin_page(&device,1u);
    device.fail_stop=1;
    const uint64_t accepted=stats.pages_submitted;
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==-1);
    assert(stats.pages_submitted==accepted);
    assert(spu.frames_rendered==old_clock);
    /* An unsuccessful stop/open/start cannot claim page delivery. */
    for(unsigned stage=0;stage<3u;stage++) {
        Mock broken={.opened=1,.playing=1};
        VhAudioOutputOps bad=callbacks(&broken);
        VhAudioOutputRecovery counts={0};
        begin_page(&broken,1u);
        broken.fail_stop=stage==0u;
        broken.fail_open=stage==1u;
        broken.fail_start=stage==2u;
        assert(vh_audio_output_submit_recover(
            &bad,&counts,dst,557u)==-1);
        assert(counts.pages_submitted==0u);
        assert(counts.frames_submitted==0u);
        assert(broken.submissions==1u);
        assert(spu.frames_rendered==old_clock);
        assert(resampler.input_frames==old_input);
    }
    /* HOME/sleep resume must not generate a new PCM page. */
    Mock paused={.opened=1,.playing=0};
    VhAudioOutputOps pause_ops=callbacks(&paused);
    VhAudioOutputRecovery pause_stats={0};
    const uint64_t old_notes=seq.note_ons;
    assert(vh_audio_output_resume_recover(&pause_ops,&pause_stats,1)==0);
    assert(paused.opened && paused.playing);
    assert(paused.opens==1u && paused.starts==1u);
    assert(pause_stats.pages_submitted==0u);
    assert(pause_stats.resume_recoveries==1u);
    assert(spu.frames_rendered==old_clock);
    assert(resampler.input_frames==old_input);
    assert(seq.note_ons==old_notes);
    /* Combine bank switching and blocking audout page ownership.
     * Unlike the previous single-bank test, this one changes the
     * borrowed voice sample arena between 6 eight-block scenes.
     * No switch or PCM overwrite occurs before the mock reports
     * release of the exact previous page, including after failures.
     */
    for (unsigned i=0;i<128u;i++)
        alternate_sample[i]=(int16_t)(6000-(int)i*127);
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,resolve,
                              sample,0)==0);
    Mock switching={.opened=1,.playing=1,
                    .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps switch_ops=callbacks(&switching);
    VhAudioOutputRecovery switch_stats={0};
    VhAudioSceneWaits measured_pages={0};
    uint64_t check_hash=UINT64_C(1469598103934665603);
    uint64_t frame_count=0;
    unsigned switch_count=0, extra_submits=0, recovered_pages=0;
    for (unsigned block=0;block<48u;block++) {
        if (block && block%8u==0u) {
            /* Submissions are synchronous: all previous page memory
             * must already have returned to the caller.
             */
            assert(switching.accepted==block);
            assert(switch_stats.pages_submitted==block);
            assert(switching.page_pointer==dst);
            assert(switching.attempts_this_page>=1u);
            const uint64_t old_input=resampler.input_frames;
            const uint64_t old_tick=resampler.next_output_tick;
            memcpy(&history_before_switch,&spu.reverb,
                   sizeof(history_before_switch));
            const int16_t *new_source=(block/8u)%2u
                ? alternate_sample : sample;
            assert(vh_native_seq_switch_scene(&seq,song,sizeof song,&spu,
                       resolve,(void *)new_source,0)==0);
            assert(!memcmp(&spu.reverb,&history_before_switch,
                           sizeof(history_before_switch)));
            assert(resampler.input_frames==old_input);
            assert(resampler.next_output_tick==old_tick);
            assert(seq.context==new_source);
            assert(spu.frames_rendered==0u);
            for (unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
                assert(!spu.voice[slot].active);
                assert(spu.voice[slot].pcm==NULL);
            }
            ++switch_count;
        }
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
            &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t hash=hash_page(dst,frames);
        check_hash=(check_hash^hash)*UINT64_C(1099511628211);
        frame_count+=frames;
        const uint64_t old_input=resampler.input_frames;
        const uint64_t old_tick=resampler.next_output_tick;
        const uint64_t old_voice_time=spu.frames_rendered;
        const uint64_t old_notes=seq.note_ons;
        /* Force recovery on the first page of new scenes 3 and 5,
         * not just ordinary pages between bank changes.
         */
        begin_page(&switching,(block%19u==7u || block==16u) ? 1u : 0u);
        switching.mismatched_returns_left=(block%13u==5u || block==32u);
        switching.null_returns_left=(block%17u==11u);
        const unsigned failures=switching.failures_left+
            switching.mismatched_returns_left+switching.null_returns_left;
        const VhAudioSubmitTiming before_page=switching.timing;
        extra_submits+=failures;
        recovered_pages+=(failures!=0u);
        assert(vh_audio_output_submit_recover(&switch_ops,&switch_stats,
                                              dst,frames)==0);
        const int boundary=block && block%8u==0u;
        assert(vh_audio_output_record_scene_page(
                   &measured_pages,&before_page,&switching.timing,
                   freq,frames,boundary,1)==0);
        assert(switching.accepted==block+1u);
        assert(switch_stats.pages_submitted==block+1u);
        assert(switching.attempts_this_page==failures+1u);
        assert(hash_page(dst,frames)==hash);
        assert(resampler.input_frames==old_input);
        assert(resampler.next_output_tick==old_tick);
        assert(spu.frames_rendered==old_voice_time);
        assert(seq.note_ons==old_notes);
    }
    assert(switch_count==5u);
    assert(switching.accepted==48u);
    assert(switching.submissions==48u+extra_submits);
    assert(switching.timing.calls==switching.submissions);
    assert(switching.timing.failed_submissions==extra_submits);
    assert(switching.timing.waits_longer_than_page>0u);
    assert(switching.timing.max_ticks==250000u);
    assert(measured_pages.first_after_switch.pages==5u);
    assert(measured_pages.ordinary.pages==43u);
    assert(measured_pages.first_after_switch.failed_pages==0u);
    assert(measured_pages.ordinary.failed_pages==0u);
    assert(measured_pages.first_after_switch.retried_pages==2u);
    assert(measured_pages.ordinary.retried_pages==recovered_pages-2u);
    assert(measured_pages.first_after_switch.total_ticks+
           measured_pages.ordinary.total_ticks==switching.timing.total_ticks);
    assert(measured_pages.first_after_switch.retried_pages+
           measured_pages.ordinary.retried_pages==recovered_pages);
    assert(measured_pages.first_after_switch.slow_pages+
           measured_pages.ordinary.slow_pages>0u);
    assert(measured_pages.first_after_switch.peak_page_ticks>0u);
    assert(measured_pages.ordinary.peak_page_ticks>0u);
    assert(switching.checksum==check_hash);
    assert(switch_stats.frames_submitted==frame_count);
    assert(switch_stats.pages_submitted==48u);
    assert(switch_stats.submit_failures==extra_submits);
    assert(switch_stats.restart_attempts==extra_submits);
    assert(switch_stats.recoveries==recovered_pages);
    assert(extra_submits>0u && recovered_pages>0u);
    assert(resampler.input_frames==48u*512u);
    assert(frame_count==((48u*512u-1u)*48000u)/44100u+1u);
    assert(resampler.next_output_tick==frame_count*44100u);
    /* A successful test is only eligible for FULL once all returned
     * PCM pages, synthetic scene changes and service waits reconcile.
     * The same facts are INCOMPLETE when the requested duration is
     * longer, or when a human stops the test early.
     */
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,64u,8u,1)==0);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,48u,8u,0)==0);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,4u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,48u,0u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        47u,5u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        NULL,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,NULL,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,NULL,
        48u,5u,48u,8u,1)==-1);
    VhAudioSceneWaits altered=measured_pages;
    altered.first_after_switch.pages=6u;
    assert(vh_audio_output_verify_run(
        &altered,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    altered=measured_pages;
    altered.ordinary.total_ticks++;
    assert(vh_audio_output_verify_run(
        &altered,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    altered=measured_pages;
    altered.ordinary.failed_pages=altered.ordinary.pages+1u;
    assert(vh_audio_output_verify_run(
        &altered,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    VhAudioOutputRecovery altered_recovery=switch_stats;
    altered_recovery.pages_submitted++;
    assert(vh_audio_output_verify_run(
        &measured_pages,&altered_recovery,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    VhAudioSubmitTiming altered_timing=switching.timing;
    altered_timing.failed_submissions++;
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&altered_timing,
        48u,5u,48u,8u,1)==-1);
    /* A failed logical page is accounted for without ever claiming
     * that the audio service returned a usable PCM page.
     */
    VhAudioSceneWaits aborted={0};
    aborted.ordinary.pages=1u;
    aborted.ordinary.failed_pages=1u;
    aborted.ordinary.total_ticks=100u;
    aborted.ordinary.peak_page_ticks=100u;
    VhAudioOutputRecovery aborted_recovery={.submit_failures=1u};
    VhAudioSubmitTiming aborted_timing={
        .calls=1u,.total_ticks=100u,.max_ticks=100u,
        .failed_submissions=1u};
    assert(vh_audio_output_verify_run(
        &aborted,&aborted_recovery,&aborted_timing,
        0u,0u,48u,8u,0)==0);
    /* A user-owned bank is never automatically switched; the same
     * class of observations is valid only with zero boundary pages.
     */
    VhAudioSceneWaits sd_pages={0};
    sd_pages.ordinary.pages=2u;
    sd_pages.ordinary.total_ticks=200u;
    sd_pages.ordinary.peak_page_ticks=100u;
    VhAudioOutputRecovery sd_recovery={.pages_submitted=2u};
    VhAudioSubmitTiming sd_timing={
        .calls=2u,.total_ticks=200u,.max_ticks=100u};
    assert(vh_audio_output_verify_run(
        &sd_pages,&sd_recovery,&sd_timing,2u,0u,2u,0u,1)==1);
    assert(vh_audio_output_verify_run(
        &sd_pages,&sd_recovery,&sd_timing,2u,1u,2u,0u,1)==-1);

    printf("audout recovery: %u accepted pages, %u restarts, clock stable PASS\n",
           device.accepted,stats.restart_attempts);
    return 0;
}
