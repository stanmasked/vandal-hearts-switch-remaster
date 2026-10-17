/* Copyright-free native audout pause/resume -> terminal failure
 * integration: no physical Switch claims, SEQ game assets or PCM export.
 * All page deliveries use the same real production helper functions.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_page_telemetry.h"
#include "vh_audio_report_pages.h"

#define HZ UINT64_C(19200000)
#define FRAMES 8u
#define PAGES 70u
#define FNV_INIT UINT64_C(1469598103934665603)
#define FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    unsigned open, playing, calls, delivered, failures_left;
    unsigned page_attempts, starts, stops, opens, closes;
    unsigned failed_stops_left, failed_opens_left;
    const int16_t *page_addr;
    size_t page_frames;
    uint64_t page_hash, delivery_hash;
    VhAudioSubmitTiming timing;
} Device;

static uint64_t page_hash(const int16_t *pcm,size_t frames) {
    uint64_t result=FNV_INIT;
    for(size_t i=0u;i<frames*2u;i++) {
        result^=(uint16_t)pcm[i];
        result*=FNV_PRIME;
    }
    return result;
}
static int submit(void *ctx,const int16_t *pcm,size_t frames) {
    Device *d=ctx;
    assert(d->open && d->playing && pcm && frames==FRAMES);
    const uint64_t hash=page_hash(pcm,frames);
    if (!d->page_attempts) {
        d->page_addr=pcm;
        d->page_frames=frames;
        d->page_hash=hash;
    } else {
        /* A service retry must use the identical existing audio
         * page, never rerender music or switch backing memory. */
        assert(d->page_addr==pcm && d->page_frames==frames);
        assert(d->page_hash==hash);
    }
    ++d->page_attempts;
    ++d->calls;
    const uint64_t ticks=d->calls%7u==0u ? 14500u :
                         d->calls%5u==0u ? 7200u : 1400u;
    const unsigned failure=(unsigned)(d->failures_left!=0u);
    if(failure) --d->failures_left;
    assert(vh_audio_output_record_submit_timing(
        &d->timing,ticks,HZ,frames,!failure)==0);
    if(failure) return -1;
    ++d->delivered;
    d->delivery_hash=(d->delivery_hash^hash)*FNV_PRIME;
    return 0;
}
static int stop(void *ctx) {
    Device *d=ctx;
    ++d->stops;
    if(d->failed_stops_left) {
        --d->failed_stops_left;
        return -1;
    }
    d->playing=0u;
    return 0;
}
static void close_device(void *ctx) {
    Device *d=ctx;
    assert(!d->playing);
    ++d->closes;
    d->open=0u;
}
static int open_device(void *ctx) {
    Device *d=ctx;
    ++d->opens;
    if(d->failed_opens_left) {
        --d->failed_opens_left;
        return -1;
    }
    d->open=1u;
    return 0;
}
static int start(void *ctx) {
    Device *d=ctx;
    ++d->starts;
    assert(!d->playing);
    if(!d->open) return -1;
    d->playing=1u;
    return 0;
}
static VhAudioOutputOps callbacks(Device *d) {
    const VhAudioOutputOps ops={
        .context=d,.submit=submit,.stop=stop,
        .close=close_device,.open=open_device,.start=start
    };
    return ops;
}
static void new_page(Device *d,unsigned failures) {
    d->page_attempts=0u;
    d->page_addr=NULL;
    d->page_frames=0u;
    d->page_hash=0u;
    d->failures_left=failures;
}
static void audit(const Device *dev, const VhAudioOutputRecovery *recovery,
                  const VhAudioSceneWaits *waits,
                  const VhAudioPcmSeams *seams,
                  const VhAudioComputeWaitJoin *joint,
                  const VhAudioListeningMarks *marks,
                  uint64_t delivered, uint64_t target) {
    assert(dev->delivered==delivered);
    assert(recovery->pages_submitted==delivered);
    assert(recovery->frames_submitted==delivered*FRAMES);
    assert(marks->returned_pages==delivered);
    assert(seams->delivered_pages==delivered);
    assert(joint->ordinary.returned==delivered);
    assert(joint->first_after_switch.returned==0u);
    assert(waits->ordinary.pages-waits->ordinary.failed_pages==delivered);
    assert(vh_audio_output_verify_pcm_seams(seams,waits,delivered)==0);
    assert(vh_audio_last_returned_page_verify(seams,marks,delivered)==0);
    assert(vh_audio_listening_verify(marks,delivered)==0);
    assert(vh_audio_listening_verify_dsp_totals(
        marks,joint->ordinary.dsp_over,
        joint->ordinary.both_over_2x,
        joint->ordinary.both_over_4x)==0);
    assert(vh_audio_output_verify_run(waits,recovery,&dev->timing,
                                     delivered,0u,target,0u,0)==0);
}
/* Pausing happens only AFTER a PCM buffer has been returned.
 * Neither an immediate second resume nor a failed one may submit
 * the just-returned descriptor again.
 */
static void pause_resume(Device *dev, VhAudioOutputOps *ops,
                         VhAudioOutputRecovery *recovery,
                         const VhAudioSceneWaits *waits,
                         const VhAudioPcmSeams *seams,
                         const VhAudioComputeWaitJoin *joint,
                         const VhAudioListeningMarks *marks,
                         unsigned mode) {
    assert(ops->stop(ops->context)==0);
    const unsigned calls=dev->calls, accepted=dev->delivered;
    const uint64_t hash=dev->delivery_hash;
    const uint64_t pages=recovery->pages_submitted;
    const uint64_t frames=recovery->frames_submitted;
    const VhAudioSubmitTiming timing=dev->timing;
    const VhAudioSceneWaits old_waits=*waits;
    const VhAudioPcmSeams old_seams=*seams;
    const VhAudioComputeWaitJoin old_joint=*joint;
    const VhAudioListeningMarks old_marks=*marks;
    if(mode==1u) {
        dev->failed_opens_left=1u;
        assert(vh_audio_output_resume_recover(ops,recovery,1)==0);
    } else if(mode==2u) {
        dev->failed_stops_left=1u;
        assert(vh_audio_output_resume_recover(ops,recovery,1)==-1);
        assert(!dev->playing);
        assert(vh_audio_output_resume_recover(ops,recovery,1)==0);
    } else {
        assert(vh_audio_output_resume_recover(ops,recovery,0)==0);
    }
    assert(dev->open && dev->playing);
    assert(dev->calls==calls && dev->delivered==accepted);
    assert(dev->delivery_hash==hash);
    assert(recovery->pages_submitted==pages);
    assert(recovery->frames_submitted==frames);
    assert(!memcmp(&dev->timing,&timing,sizeof timing));
    assert(!memcmp(waits,&old_waits,sizeof old_waits));
    assert(!memcmp(seams,&old_seams,sizeof old_seams));
    assert(!memcmp(joint,&old_joint,sizeof old_joint));
    assert(!memcmp(marks,&old_marks,sizeof old_marks));
    assert(vh_audio_last_returned_page_verify(seams,marks,pages)==0);
}
int main(void) {
    Device dev={.open=1u,.playing=1u,.delivery_hash=FNV_INIT};
    VhAudioOutputOps ops=callbacks(&dev);
    VhAudioOutputRecovery recovery={0};
    VhAudioSceneWaits waits={0};
    VhAudioPcmSeams seams={0};
    VhAudioComputeWaitJoin joint={0};
    VhAudioListeningMarks marks={0};
    uint64_t wanted=FNV_INIT;
    uint64_t synthetic_music_frame=0u;

    for(unsigned i=0u;i<PAGES;i++) {
        int16_t pcm[FRAMES*2u];
        for(unsigned k=0u;k<FRAMES*2u;k++)
            pcm[k]=(int16_t)((int)i*47+(int)k*13-2200);
        /* Simulated producer renders one unique page before submit.
         * No producer call can occur inside resume/retry callbacks. */
        synthetic_music_frame+=FRAMES;
        const VhAudioSubmitTiming before=dev.timing;
        new_page(&dev,(unsigned)(i==37u || i==65u));
        assert(vh_audio_output_submit_recover(
            &ops,&recovery,pcm,FRAMES)==0);
        assert(vh_audio_returned_page_telemetry_record(
            &waits,&seams,&joint,&marks,pcm,FRAMES,0u,
            &before,&dev.timing,HZ,(unsigned)(i%9u==0u))==0);
        wanted=(wanted^page_hash(pcm,FRAMES))*FNV_PRIME;
        assert(dev.delivery_hash==wanted);
        assert(dev.delivered==i+1u);
        assert(synthetic_music_frame==(uint64_t)(i+1u)*FRAMES);
        audit(&dev,&recovery,&waits,&seams,&joint,&marks,
              i+1u,PAGES+1u);
        if(i==5u || i==31u || i==32u ||
           i==63u || i==64u || i==69u) {
            const uint64_t music_before=synthetic_music_frame;
            const unsigned mode=(i==31u || i==63u) ? 1u :
                                (i==64u ? 2u : 0u);
            pause_resume(&dev,&ops,&recovery,&waits,&seams,
                         &joint,&marks,mode);
            /* Test an immediate second pause after a successful
             * resume: no intervening PCM page can be replayed. */
            if(i==32u || i==64u)
                pause_resume(&dev,&ops,&recovery,&waits,&seams,
                             &joint,&marks,0u);
            assert(synthetic_music_frame==music_before);
            audit(&dev,&recovery,&waits,&seams,&joint,&marks,
                  i+1u,PAGES+1u);
        }
    }
    assert(dev.delivered==PAGES);
    assert(marks.returned_pages==PAGES);
    assert(recovery.recoveries==2u);
    assert(recovery.submit_failures==2u);
    const unsigned final_slot=(PAGES-1u)%VH_LISTEN_RECENT_PAGES;
    const VhListenPage tail=marks.recent[final_slot];
    const VhAudioPcmSeams last_seams=seams;
    const VhAudioComputeWaitJoin last_joint=joint;
    const VhAudioListeningMarks last_marks=marks;
    const unsigned last_delivered=dev.delivered;
    const uint64_t last_hash=dev.delivery_hash;
    const uint64_t last_music=synthetic_music_frame;

    /* The next fully-rendered page suffers three failed raw service
     * submissions, exhausting two legal restarts. Its logical
     * failed wait bucket is counted ONCE. The returned-page seam,
     * joint counters, listening tail and delivery hash stay fixed. */
    int16_t never_delivered[FRAMES*2u];
    for(unsigned i=0u;i<FRAMES*2u;i++)
        never_delivered[i]=(int16_t)(9100u+i*23u);
    synthetic_music_frame+=FRAMES; /* rendered, not delivered */
    const VhAudioSubmitTiming before_failed=dev.timing;
    new_page(&dev,3u);
    assert(vh_audio_output_submit_recover(
        &ops,&recovery,never_delivered,FRAMES)==-1);
    assert(dev.page_attempts==3u);
    assert(vh_audio_output_record_scene_page(
        &waits,&before_failed,&dev.timing,HZ,FRAMES,0,0)==0);
    assert(waits.ordinary.failed_pages==1u);
    assert(dev.delivered==last_delivered);
    assert(recovery.pages_submitted==PAGES);
    assert(recovery.frames_submitted==PAGES*FRAMES);
    assert(dev.delivery_hash==last_hash);
    assert(!memcmp(&seams,&last_seams,sizeof seams));
    assert(!memcmp(&joint,&last_joint,sizeof joint));
    assert(!memcmp(&marks,&last_marks,sizeof marks));
    assert(!memcmp(&marks.recent[final_slot],&tail,sizeof tail));
    assert(synthetic_music_frame==last_music+FRAMES);
    audit(&dev,&recovery,&waits,&seams,&joint,&marks,
          PAGES,PAGES+1u);

    /* The audio session may still be reopened after the terminal
     * submit failure; doing so must not queue the failed page or
     * change the last successfully delivered one. */
    const unsigned calls_before_resume=dev.calls;
    const VhAudioSubmitTiming ticks_before_resume=dev.timing;
    assert(ops.stop(ops.context)==0);
    assert(vh_audio_output_resume_recover(&ops,&recovery,1)==0);
    assert(dev.calls==calls_before_resume);
    assert(!memcmp(&dev.timing,&ticks_before_resume,
                   sizeof ticks_before_resume));
    assert(dev.delivered==PAGES && dev.delivery_hash==last_hash);
    assert(!memcmp(&seams,&last_seams,sizeof seams));
    assert(!memcmp(&joint,&last_joint,sizeof joint));
    assert(!memcmp(&marks,&last_marks,sizeof marks));
    audit(&dev,&recovery,&waits,&seams,&joint,&marks,
          PAGES,PAGES+1u);

    /* Forced shutdown while the last *attempted* PCM page was not
     * delivered: failed stops must not close the service, release
     * any descriptor, create returned-page metadata, or advance
     * the previously accepted audio checksum. */
    dev.failed_stops_left=3u;
    const unsigned closes_before=dev.closes;
    const unsigned stops_before=dev.stops;
    const unsigned raw_before=dev.calls;
    const unsigned delivered_before=dev.delivered;
    const uint64_t checksum_before=dev.delivery_hash;
    const VhAudioSubmitTiming timing_shutdown=dev.timing;
    const VhAudioSceneWaits waits_shutdown=waits;
    const VhAudioOutputRecovery recovery_shutdown=recovery;
    const uint64_t rendered_shutdown=synthetic_music_frame;
    for(unsigned i=0u;i<3u;i++) {
        assert(vh_audio_output_stop_close(&ops)==-1);
        assert(dev.failed_stops_left==2u-i);
        assert(dev.stops==stops_before+i+1u);
        assert(dev.closes==closes_before);
        assert(dev.open && dev.playing);
        assert(dev.calls==raw_before && dev.delivered==delivered_before);
        assert(dev.delivery_hash==checksum_before);
        assert(!memcmp(&dev.timing,&timing_shutdown,sizeof dev.timing));
        assert(!memcmp(&waits,&waits_shutdown,sizeof waits));
        assert(!memcmp(&recovery,&recovery_shutdown,sizeof recovery));
        assert(!memcmp(&seams,&last_seams,sizeof seams));
        assert(!memcmp(&joint,&last_joint,sizeof joint));
        assert(!memcmp(&marks,&last_marks,sizeof marks));
        assert(synthetic_music_frame==rendered_shutdown);
        audit(&dev,&recovery,&waits,&seams,&joint,&marks,
              PAGES,PAGES+1u);
    }
    /* Fourth stop actually succeeds: close exactly ONCE. Closing
     * is a resource action only and can never retroactively count
     * a failed audio page as returned. */
    assert(vh_audio_output_stop_close(&ops)==0);
    assert(dev.stops==stops_before+4u && dev.closes==closes_before+1u);
    assert(!dev.open && !dev.playing);
    assert(dev.calls==raw_before && dev.delivered==PAGES);
    assert(dev.delivery_hash==last_hash);
    assert(!memcmp(&dev.timing,&timing_shutdown,sizeof dev.timing));
    assert(!memcmp(&waits,&waits_shutdown,sizeof waits));
    assert(!memcmp(&recovery,&recovery_shutdown,sizeof recovery));
    assert(!memcmp(&seams,&last_seams,sizeof seams));
    assert(!memcmp(&joint,&last_joint,sizeof joint));
    assert(!memcmp(&marks,&last_marks,sizeof marks));
    audit(&dev,&recovery,&waits,&seams,&joint,&marks,
          PAGES,PAGES+1u);
    assert(vh_audio_output_stop_close(NULL)==-1);
    VhAudioOutputOps invalid_stop=ops;
    invalid_stop.stop=NULL;
    assert(vh_audio_output_stop_close(&invalid_stop)==-1);
    invalid_stop=ops;
    invalid_stop.close=NULL;
    assert(vh_audio_output_stop_close(&invalid_stop)==-1);
    assert(dev.closes==closes_before+1u);

    /* Fresh session: zero successfully returned pages and one
     * terminal failure must still report incomplete, not FULL. */
    Device empty={.open=1u,.playing=1u,.delivery_hash=FNV_INIT};
    VhAudioOutputOps empty_ops=callbacks(&empty);
    VhAudioOutputRecovery empty_recovery={0};
    VhAudioSceneWaits empty_waits={0};
    VhAudioPcmSeams empty_seams={0};
    VhAudioComputeWaitJoin empty_joint={0};
    VhAudioListeningMarks empty_marks={0};
    const VhAudioSubmitTiming empty_before={0};
    new_page(&empty,3u);
    assert(vh_audio_output_submit_recover(
        &empty_ops,&empty_recovery,never_delivered,FRAMES)==-1);
    assert(vh_audio_output_record_scene_page(
        &empty_waits,&empty_before,&empty.timing,HZ,FRAMES,0,0)==0);
    audit(&empty,&empty_recovery,&empty_waits,&empty_seams,
          &empty_joint,&empty_marks,0u,1u);
    assert(empty_waits.ordinary.failed_pages==1u);
    assert(empty_recovery.pages_submitted==0u);
    /* An empty run that never submitted a page is INCOMPLETE,
     * never FULL; shutdown success cannot manufacture playback. */
    {
        const VhAudioSceneWaits untouched_waits={0};
        const VhAudioOutputRecovery untouched_stats={0};
        const VhAudioSubmitTiming untouched_timing={0};
        assert(vh_audio_output_verify_run(
            &untouched_waits,&untouched_stats,&untouched_timing,
            0u,0u,1u,0u,1)==0);
        assert(vh_audio_report_evidence(0,0,0,0,0)==
               VH_AUDIO_REPORT_INCOMPLETE);
    }

    /* One entire failed page, ZERO delivered pages. Stop fails
     * twice, then succeeds and closes exactly once. Neither an
     * unsuccessful shutdown nor the subsequent open/start may
     * backfill the failed page into any returned-page accumulator. */
    const uint64_t abandoned_hash=page_hash(never_delivered,FRAMES);
    const unsigned failed_calls=empty.calls;
    const uint64_t no_audio_hash=empty.delivery_hash;
    const VhAudioSubmitTiming failed_timing=empty.timing;
    const VhAudioSceneWaits failed_waits=empty_waits;
    const VhAudioOutputRecovery failed_recovery=empty_recovery;
    empty.failed_stops_left=2u;
    for(unsigned i=0u;i<2u;i++) {
        assert(vh_audio_output_stop_close(&empty_ops)==-1);
        assert(empty.stops==VH_AUDIO_OUTPUT_RESTART_LIMIT+i+1u);
        assert(empty.closes==VH_AUDIO_OUTPUT_RESTART_LIMIT);
        assert(empty.open && empty.playing);
        assert(empty.calls==failed_calls && empty.delivered==0u);
        assert(empty.delivery_hash==no_audio_hash);
        assert(!memcmp(&empty.timing,&failed_timing,sizeof failed_timing));
        assert(!memcmp(&empty_waits,&failed_waits,sizeof failed_waits));
        assert(!memcmp(&empty_recovery,&failed_recovery,sizeof failed_recovery));
        audit(&empty,&empty_recovery,&empty_waits,&empty_seams,
              &empty_joint,&empty_marks,0u,1u);
    }
    assert(empty.failed_stops_left==0u);
    assert(vh_audio_output_stop_close(&empty_ops)==0);
    assert(!empty.open && !empty.playing);
    assert(empty.stops==VH_AUDIO_OUTPUT_RESTART_LIMIT+3u);
    assert(empty.closes==VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    assert(empty.calls==failed_calls && empty.delivered==0u);
    assert(empty.delivery_hash==no_audio_hash);
    assert(vh_audio_last_returned_page_verify(
        &empty_seams,&empty_marks,0u)==0);
    assert(vh_audio_output_verify_run(
        &empty_waits,&empty_recovery,&empty.timing,
        0u,0u,1u,0u,1)==0);

    /* A true *fresh* audio device open/start is not a submission:
     * the old run's failed-page evidence remains in the old
     * accumulators until intentionally beginning a new run. */
    const unsigned raw_before_open=empty.calls;
    const uint64_t frames_before_open=empty_recovery.frames_submitted;
    assert(empty_ops.open(empty_ops.context)==0);
    assert(empty_ops.start(empty_ops.context)==0);
    assert(empty.open && empty.playing);
    assert(empty.calls==raw_before_open);
    assert(empty.delivered==0u && empty.delivery_hash==FNV_INIT);
    assert(empty_recovery.frames_submitted==frames_before_open);
    assert(empty_waits.ordinary.failed_pages==1u);
    assert(vh_audio_last_returned_page_verify(
        &empty_seams,&empty_marks,0u)==0);

    /* A deliberately NEW PCM page is the FIRST ever delivered
     * page. It receives no predecessor seam and cannot erase the
     * earlier terminal backend failure from the session verdict. */
    int16_t first_after_reopen[FRAMES*2u];
    for(unsigned i=0u;i<FRAMES*2u;i++)
        first_after_reopen[i]=(int16_t)(-6000+(int)i*173);
    const uint64_t first_hash=page_hash(first_after_reopen,FRAMES);
    const VhAudioSubmitTiming before_new=empty.timing;
    new_page(&empty,0u);
    assert(vh_audio_output_submit_recover(
        &empty_ops,&empty_recovery,first_after_reopen,FRAMES)==0);
    assert(vh_audio_returned_page_telemetry_record(
        &empty_waits,&empty_seams,&empty_joint,&empty_marks,
        first_after_reopen,FRAMES,0u,&before_new,&empty.timing,
        HZ,0u)==0);
    assert(empty.calls==failed_calls+1u && empty.delivered==1u);
    assert(empty.delivery_hash==(FNV_INIT^first_hash)*FNV_PRIME);
    assert(empty_recovery.pages_submitted==1u);
    assert(empty_waits.ordinary.pages==2u &&
           empty_waits.ordinary.failed_pages==1u);
    assert(empty_seams.delivered_pages==1u &&
           empty_seams.last_abs_step==0u &&
           empty_marks.returned_pages==1u);
    assert(page_hash(never_delivered,FRAMES)==abandoned_hash);
    audit(&empty,&empty_recovery,&empty_waits,&empty_seams,
          &empty_joint,&empty_marks,1u,2u);
    assert(vh_audio_output_verify_run(
        &empty_waits,&empty_recovery,&empty.timing,
        1u,0u,1u,0u,1)==0);
    assert(vh_audio_report_evidence(0,0,0,0,0)==
           VH_AUDIO_REPORT_INCOMPLETE);

    /* Resume the SAME interrupted session with nine more returned
     * pages, two labeled scene changes (index 4 and 8), and a
     * recovered backend retry (index 6). The first missing page
     * remains a terminal ordinary-page failure throughout. */
    uint64_t scene_hash=empty.delivery_hash;
    unsigned scene_index=0u,boundaries=0u;
    for(unsigned page=1u;page<10u;page++) {
        const unsigned scene_boundary=(unsigned)(page%4u==0u);
        if(scene_boundary) {
            ++scene_index;
            ++boundaries;
        }
        int16_t pcm[FRAMES*2u];
        for(unsigned k=0u;k<FRAMES*2u;k++)
            pcm[k]=(int16_t)(-3600+(int)scene_index*3200+
                             (int)page*113+(int)k*19);
        const uint64_t hash=page_hash(pcm,FRAMES);
        const VhAudioSubmitTiming before=empty.timing;
        const uint64_t previous_frames=empty_recovery.frames_submitted;
        const uint64_t previous_failures=empty_recovery.submit_failures;
        new_page(&empty,(unsigned)(page==6u));
        assert(vh_audio_output_submit_recover(
            &empty_ops,&empty_recovery,pcm,FRAMES)==0);
        assert(empty.page_addr==pcm && empty.page_hash==hash);
        assert(empty.page_attempts==(page==6u ? 2u : 1u));
        scene_hash=(scene_hash^hash)*FNV_PRIME;
        assert(empty.delivery_hash==scene_hash);
        assert(empty_recovery.frames_submitted==
               previous_frames+FRAMES);
        assert(empty_recovery.submit_failures==
               previous_failures+(page==6u ? 1u : 0u));
        assert(vh_audio_returned_page_telemetry_record(
            &empty_waits,&empty_seams,&empty_joint,&empty_marks,
            pcm,FRAMES,scene_boundary,&before,&empty.timing,
            HZ,(unsigned)(page%3u==0u))==0);
        assert(empty.delivered==page+1u);
        assert(empty_recovery.pages_submitted==page+1u);
        assert(empty_waits.ordinary.failed_pages==1u);
        assert(empty_waits.first_after_switch.pages==boundaries);
        assert(empty_joint.first_after_switch.returned==boundaries);
        assert(empty_marks.recent[page].scene_boundary==scene_boundary);
        assert(empty_marks.recent[page].retry==(unsigned)(page==6u));
        assert(empty_marks.recent[page].dsp_over_budget==
               (unsigned)(page%3u==0u));
        assert(empty_marks.recent[page].wait_band==
               empty_seams.last_wait_band);
        assert(empty_marks.recent[page].seam_step==
               empty_seams.last_abs_step);
        assert(vh_audio_output_verify_pcm_seams(
            &empty_seams,&empty_waits,page+1u)==0);
        assert(vh_audio_last_returned_page_verify(
            &empty_seams,&empty_marks,page+1u)==0);
        assert(vh_audio_listening_verify(&empty_marks,page+1u)==0);
        assert(vh_audio_listening_verify_dsp_totals(
            &empty_marks,
            empty_joint.ordinary.dsp_over+
                empty_joint.first_after_switch.dsp_over,
            empty_joint.ordinary.both_over_2x+
                empty_joint.first_after_switch.both_over_2x,
            empty_joint.ordinary.both_over_4x+
                empty_joint.first_after_switch.both_over_4x)==0);
        assert(vh_audio_output_verify_run(
            &empty_waits,&empty_recovery,&empty.timing,
            page+1u,boundaries,10u,4u,1)==0);
        assert(vh_audio_report_evidence(0,0,0,0,0)==
               VH_AUDIO_REPORT_INCOMPLETE);
        if(scene_boundary) {
            /* Reopen right after each cue change: no accepted
             * audio, raw callback, PCM tail or prior failure may
             * appear/disappear while the service resumes. */
            const VhAudioSubmitTiming saved_timing=empty.timing;
            const VhAudioSceneWaits saved_waits=empty_waits;
            const VhAudioPcmSeams saved_seams=empty_seams;
            const VhAudioComputeWaitJoin saved_joint=empty_joint;
            const VhAudioListeningMarks saved_marks=empty_marks;
            const uint64_t saved_hash=empty.delivery_hash;
            const uint64_t saved_pages=empty_recovery.pages_submitted;
            const unsigned saved_calls=empty.calls;
            const unsigned saved_failures=empty_recovery.submit_failures;
            assert(empty_ops.stop(empty_ops.context)==0);
            assert(vh_audio_output_resume_recover(
                &empty_ops,&empty_recovery,1)==0);
            assert(empty.calls==saved_calls &&
                   empty.delivery_hash==saved_hash);
            assert(empty_recovery.pages_submitted==saved_pages &&
                   empty_recovery.submit_failures==saved_failures);
            assert(!memcmp(&empty.timing,&saved_timing,
                           sizeof saved_timing));
            assert(!memcmp(&empty_waits,&saved_waits,
                           sizeof saved_waits));
            assert(!memcmp(&empty_seams,&saved_seams,
                           sizeof saved_seams));
            assert(!memcmp(&empty_joint,&saved_joint,
                           sizeof saved_joint));
            assert(!memcmp(&empty_marks,&saved_marks,
                           sizeof saved_marks));
        }
    }
    assert(scene_index==2u && boundaries==2u);
    assert(empty.delivered==10u && empty.calls==14u);
    assert(empty_recovery.submit_failures==4u &&
           empty_recovery.restart_attempts==3u &&
           empty_recovery.recoveries==1u);
    assert(empty_waits.ordinary.pages==9u &&
           empty_waits.ordinary.failed_pages==1u &&
           empty_waits.first_after_switch.pages==2u);
    assert(empty_joint.ordinary.returned==8u &&
           empty_joint.first_after_switch.returned==2u);
    for(unsigned k=0u;k<10u;k++)
        assert(empty_marks.recent[k].scene_boundary==
               (unsigned)(k!=0u && k%4u==0u));
    assert(page_hash(never_delivered,FRAMES)==abandoned_hash);
    assert(vh_audio_output_verify_run(
        &empty_waits,&empty_recovery,&empty.timing,
        10u,2u,10u,4u,1)==0);
    /* Historical failure erasure or switch-counter corruption
     * must fail the original run audit, never become FULL. */
    VhAudioSceneWaits bad_waits=empty_waits;
    bad_waits.ordinary.failed_pages=0u;
    assert(vh_audio_output_verify_run(
        &bad_waits,&empty_recovery,&empty.timing,
        10u,2u,10u,4u,1)==-1);
    VhAudioOutputRecovery bad_recovery=empty_recovery;
    --bad_recovery.submit_failures;
    assert(vh_audio_output_verify_run(
        &empty_waits,&bad_recovery,&empty.timing,
        10u,2u,10u,4u,1)==-1);
    assert(vh_audio_output_verify_run(
        &empty_waits,&empty_recovery,&empty.timing,
        10u,1u,10u,4u,1)==-1);
    puts("audout recovered three-scene history and failure retention: PASS");

    /* FULL may be reported only for an independently reset session
     * which contains a genuinely delivered PCM page and NO failed
     * logical pages. This contrast prevents a false FULL caused by
     * reopening the device and disregarding previous failures. */
    Device clean={.open=1u,.playing=1u,.delivery_hash=FNV_INIT};
    VhAudioOutputOps clean_ops=callbacks(&clean);
    VhAudioOutputRecovery clean_recovery={0};
    VhAudioSceneWaits clean_waits={0};
    VhAudioPcmSeams clean_seams={0};
    VhAudioComputeWaitJoin clean_joint={0};
    VhAudioListeningMarks clean_marks={0};
    const VhAudioSubmitTiming clean_before={0};
    new_page(&clean,0u);
    assert(vh_audio_output_submit_recover(
        &clean_ops,&clean_recovery,first_after_reopen,FRAMES)==0);
    assert(vh_audio_returned_page_telemetry_record(
        &clean_waits,&clean_seams,&clean_joint,&clean_marks,
        first_after_reopen,FRAMES,0u,&clean_before,&clean.timing,
        HZ,0u)==0);
    assert(vh_audio_output_verify_pcm_seams(
        &clean_seams,&clean_waits,1u)==0);
    assert(vh_audio_last_returned_page_verify(
        &clean_seams,&clean_marks,1u)==0);
    assert(vh_audio_output_verify_run(
        &clean_waits,&clean_recovery,&clean.timing,
        1u,0u,1u,0u,1)==1);
    assert(vh_audio_report_evidence(1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
    puts("audout zero-delivery shutdown/reopen verdict isolation: PASS");
    puts("audout 70-page repeated pause/resume + terminal failure: PASS");
    return 0;
}
