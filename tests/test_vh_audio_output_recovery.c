/* Fault-injected audout recovery; host-only, no Nintendo hardware or assets.
 * The recovery must replay a prepared 48-kHz page, not re-render SEQ/SPU.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_audio_output_recovery.h"
#include "vh_audio_output_ramp.h"
#include "vh_audio_resample.h"
#include "vh_music_scene.h"

typedef struct {
    unsigned opened, playing, failures_left;
    unsigned fail_stop, fail_open, fail_start, fail_starts_left;
    unsigned submits, stops, closes, opens, starts;
    uint64_t accepted_frames, checksum, attempted_hash;
    const int16_t *attempted_pointer;
    size_t attempted_frames;
    unsigned attempts_this_page, accepted_pages;
} MockOutput;

static uint64_t hash_pcm(const int16_t *pcm, size_t frames) {
    uint64_t value=UINT64_C(1469598103934665603);
    for (size_t i=0;i<2u*frames;i++) {
        value ^= (uint16_t)pcm[i];
        value *= UINT64_C(1099511628211);
    }
    return value;
}

static int mock_submit(void *ctx, const int16_t *pcm, size_t frames) {
    MockOutput *d=ctx;
    assert(d->opened && d->playing && frames>0u);
    const uint64_t fingerprint=hash_pcm(pcm,frames);
    if (!d->attempts_this_page) {
        d->attempted_hash=fingerprint;
        d->attempted_pointer=pcm;
        d->attempted_frames=frames;
    } else {
        /* The SAME immutable block must be resent after restart. */
        assert(d->attempted_hash==fingerprint);
        assert(d->attempted_pointer==pcm && d->attempted_frames==frames);
    }
    ++d->submits;
    ++d->attempts_this_page;
    if (d->failures_left) {
        --d->failures_left;
        return -1;
    }
    d->checksum ^= fingerprint;
    d->checksum *= UINT64_C(1099511628211);
    d->accepted_frames+=frames;
    ++d->accepted_pages;
    return 0;
}
static int mock_stop(void *ctx) {
    MockOutput *d=ctx;
    ++d->stops;
    if(d->fail_stop) return -1;
    d->playing=0;
    return 0;
}
static void mock_close(void *ctx) {
    MockOutput *d=ctx;
    if(!d->opened) return;
    assert(!d->playing);
    ++d->closes;
    d->opened=0;
}
static int mock_open(void *ctx) {
    MockOutput *d=ctx;
    ++d->opens;
    if(d->fail_open) return -1;
    assert(!d->opened);
    d->opened=1;
    return 0;
}
static int mock_start(void *ctx) {
    MockOutput *d=ctx;
    ++d->starts;
    if(d->fail_start) return -1;
    if(d->fail_starts_left) {
        --d->fail_starts_left;
        return -1;
    }
    assert(d->opened && !d->playing);
    d->playing=1;
    return 0;
}
static VhAudioOutputOps ops_for(MockOutput *d) {
    return (VhAudioOutputOps){
        d,mock_submit,mock_stop,mock_close,mock_open,mock_start
    };
}
static void next_page(MockOutput *d, unsigned rejected) {
    d->failures_left=rejected;
    d->attempts_this_page=0;
    d->attempted_hash=0;
    d->attempted_pointer=NULL;
    d->attempted_frames=0;
}

static void test_failed_restart_paths(void) {
    int16_t page[16];
    for(unsigned i=0;i<16;i++)page[i]=(int16_t)(i*729-6000);
    VhAudioOutputRecovery stats={0};
    MockOutput d={.opened=1,.playing=1,.checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps ops=ops_for(&d);
    assert(vh_audio_output_submit_recover(NULL,&stats,page,8)==-1);
    assert(vh_audio_output_submit_recover(&ops,NULL,page,8)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,NULL,8)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,page,0)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,page,
                                          VH_AUDIO_RESAMPLE_MAX_FRAMES+1u)==-1);
    assert(stats.pages_submitted==0 && d.submits==0);
    next_page(&d,0);
    assert(vh_audio_output_submit_recover(&ops,&stats,page,8)==0);
    assert(stats.pages_submitted==1 && stats.frames_submitted==8);
    assert(stats.submit_failures==0 && stats.restart_attempts==0);
    next_page(&d,1);
    assert(vh_audio_output_submit_recover(&ops,&stats,page,8)==0);
    assert(stats.pages_submitted==2 && stats.frames_submitted==16);
    assert(stats.recoveries==1 && stats.restart_attempts==1);
    assert(d.stops==1 && d.closes==1 && d.opens==1 && d.starts==1);
    next_page(&d,2);
    assert(vh_audio_output_submit_recover(&ops,&stats,page,8)==0);
    assert(stats.pages_submitted==3 && stats.frames_submitted==24);
    assert(stats.recoveries==2 && stats.restart_attempts==3);
    assert(stats.submit_failures==3);
    next_page(&d,3);
    assert(vh_audio_output_submit_recover(&ops,&stats,page,8)==-1);
    assert(stats.pages_submitted==3 && stats.frames_submitted==24);
    assert(stats.restart_attempts==5 && stats.submit_failures==6);
    assert(d.attempts_this_page==3u); /* bounded, not runaway */
    assert(d.opened && d.playing);
    for(unsigned error=0;error<3;error++) {
        MockOutput failing={.opened=1,.playing=1};
        VhAudioOutputOps bad=ops_for(&failing);
        VhAudioOutputRecovery counts={0};
        next_page(&failing,1);
        failing.fail_stop=error==0;
        failing.fail_open=error==1;
        failing.fail_start=error==2;
        assert(vh_audio_output_submit_recover(
               &bad,&counts,page,8)==-1);
        assert(counts.pages_submitted==0 && counts.frames_submitted==0);
        assert(counts.submit_failures==1);
        assert(counts.restart_attempts==(error==0?0u:1u));
        assert(failing.submits==1u);
        if(error==0) assert(failing.opened && failing.playing);
        else if(error==1) assert(!failing.opened && !failing.playing);
        else assert(failing.opened && !failing.playing);
    }
}

/* Explicit applet HOME resume and ordinary focus-only starts.
 * A successful recovery must never submit a page or increment any
 * produced PCM counter; a terminal error leaves ownership unchanged.
 */
static void test_resume_restart_paths(void) {
    VhAudioOutputRecovery counters={0};
    MockOutput d={.opened=1,.playing=0};
    VhAudioOutputOps ops=ops_for(&d);
    assert(vh_audio_output_resume_recover(NULL,&counters,1)==-1);
    assert(vh_audio_output_resume_recover(&ops,NULL,1)==-1);
    assert(!d.submits && !d.starts && !counters.pages_submitted);

    /* Focus only: the current stopped service should simply start. */
    assert(vh_audio_output_resume_recover(&ops,&counters,0)==0);
    assert(d.playing && d.opened && d.starts==1);
    assert(!counters.resume_restarts && !counters.resume_failures);
    assert(mock_stop(&d)==0);

    /* Explicit HOME: close stale stopped handles even if start on
     * the previous session might otherwise report success. */
    assert(vh_audio_output_resume_recover(&ops,&counters,1)==0);
    assert(d.playing && d.opened && d.closes==1 && d.opens==1);
    assert(counters.resume_restarts==1 && counters.resume_recoveries==1);
    assert(mock_stop(&d)==0);

    /* A start failure without a resume serial also forces reopen. */
    d.fail_starts_left=1;
    assert(vh_audio_output_resume_recover(&ops,&counters,0)==0);
    assert(d.playing && counters.resume_restarts==2);
    assert(counters.resume_failures==1 && counters.resume_recoveries==2);
    assert(mock_stop(&d)==0);

    /* Forced HOME resume: first fresh service start fails, second
     * one succeeds; both attempts are bounded. */
    d.fail_starts_left=1;
    assert(vh_audio_output_resume_recover(&ops,&counters,1)==0);
    assert(d.playing && counters.resume_restarts==4);
    assert(counters.resume_failures==2 && counters.resume_recoveries==3);
    assert(mock_stop(&d)==0);

    /* A permanently failing output cannot spin forever or produce
     * a false success; the caller must enter normal teardown. */
    d.fail_start=1;
    const unsigned before=d.starts;
    assert(vh_audio_output_resume_recover(&ops,&counters,1)==-1);
    assert(d.starts==before+VH_AUDIO_OUTPUT_RESTART_LIMIT);
    assert(!d.playing && d.opened);
    assert(counters.resume_restarts==6);
    assert(counters.resume_failures==4);
    assert(counters.pages_submitted==0 && counters.frames_submitted==0);

    for(unsigned error=0;error<2;error++) {
        MockOutput bad={.opened=1,.playing=0};
        VhAudioOutputRecovery stats={0};
        VhAudioOutputOps broken=ops_for(&bad);
        bad.fail_stop=(error==0);
        bad.fail_open=(error==1);
        assert(vh_audio_output_resume_recover(&broken,&stats,1)==-1);
        assert(stats.pages_submitted==0u && stats.frames_submitted==0u);
        if(!error) {
            assert(bad.opened && !bad.playing && bad.closes==0u);
        } else {
            assert(!bad.opened && !bad.playing);
            assert(stats.resume_restarts==VH_AUDIO_OUTPUT_RESTART_LIMIT);
        }
    }
}

#define SEQ_HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0
static const uint8_t field_seq[]={
    SEQ_HDR,0,0xc0,7,0,0x90,60,110,
    0x81,0x70,0x80,60,0,0x81,0x70,0xff,0x2f
};
static const uint8_t selected_seq[]={
    SEQ_HDR,0,0xc0,7,0,0x90,67,110,
    0x81,0x70,0x80,67,0,0x81,0x70,0xff,0x2f
};
static int16_t sample[128];
static VhNativeSpu spu[2];
static VhMusicScene music[2];
static VhAudioResample resampler[2];
static int16_t pcm[2][VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t output[2][VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];

static int lookup(void *ctx, unsigned program, unsigned note,
                  unsigned velocity, unsigned volume, unsigned pan,
                  VhSeqTone *out) {
    (void)ctx;(void)velocity;(void)volume;(void)pan;
    if(!out || program!=7 || (note!=60 && note!=67))return -1;
    memset(out,0,sizeof(*out));
    out->pcm=sample;out->frames=128;
    out->loop_start=0;out->loop_end=128;
    out->pitch_step=note==60?4096u:5161u;
    out->adsr1=15;
    out->gain_left=.75f;
    out->gain_right=.45f;
    out->reverb_send=1;
    return 0;
}
static const VhMusicCue field_cue={
    1,field_seq,sizeof field_seq,0,lookup,NULL
};
static const VhMusicCue selected_cue={
    2,selected_seq,sizeof selected_seq,0,lookup,NULL
};
static void test_replay_prepared_page_preserves_music_clock(void) {
    enum { TOTAL_BLOCKS=96 };
    for(unsigned i=0;i<128;i++)sample[i]=(int16_t)((int)i*179-10000);
    for(unsigned i=0;i<2u;i++) {
        vh_native_spu_reset(&spu[i]);
        assert(vh_native_spu_set_interpolation(&spu[i],VH_SPU_GAUSSIAN)==0);
        assert(vh_native_spu_set_reverb(&spu[i],1,0.5f)==0);
        vh_music_scene_init(&music[i],&spu[i]);
        vh_audio_resample_reset(&resampler[i]);
        assert(vh_music_scene_request(&music[i],&field_cue,0)==0);
    }
    MockOutput device[2]={
        {.opened=1,.playing=1,.checksum=UINT64_C(1469598103934665603)},
        {.opened=1,.playing=1,.checksum=UINT64_C(1469598103934665603)}
    };
    VhAudioOutputOps ops[2]={ops_for(&device[0]),ops_for(&device[1])};
    VhAudioOutputRecovery counters[2]={{0},{0}};
    VhAudioOutputRamp envelopes[2]={{0},{0}}; /* initial start fades in */
    unsigned expected_restarts=0,expected_bad_submits=0,expected_recoveries=0;
    unsigned home_reopens=0, home_start_failures=0;
    for(unsigned block=0;block<TOTAL_BLOCKS;block++) {
        if(block==9u || block==31u || block==60u || block==88u) {
            /* Both musical timelines pause in sync, while the
             * injected backend simulates an invalidated HOME service.
             * No scene, voice or resampler samples are generated until
             * audout is reopened and focused again. */
            const uint64_t before_clock[2]={
                resampler[0].input_frames,resampler[1].input_frames
            };
            const uint64_t before_frames[2]={
                spu[0].frames_rendered,spu[1].frames_rendered
            };
            const uint64_t before_pages[2]={
                counters[0].pages_submitted,counters[1].pages_submitted
            };
            for(unsigned i=0;i<2u;i++) {
                assert(mock_stop(&device[i])==0);
                assert(!device[i].playing);
            }
            /* Multiple paused owner turns do not synthesize
             * anything or queue a duplicate output page. */
            for(unsigned paused=0;paused<20u;paused++) {
                for(unsigned i=0;i<2u;i++) {
                    assert(resampler[i].input_frames==before_clock[i]);
                    assert(spu[i].frames_rendered==before_frames[i]);
                    assert(counters[i].pages_submitted==before_pages[i]);
                }
            }
            const unsigned injected=block==31u ? 1u :
                                    block==60u ? 1u : 0u;
            device[1].fail_starts_left=injected;
            home_start_failures+=injected;
            for(unsigned i=0;i<2u;i++) {
                assert(vh_audio_output_resume_recover(
                    &ops[i],&counters[i],1)==0);
                assert(device[i].opened && device[i].playing);
                assert(resampler[i].input_frames==before_clock[i]);
                assert(spu[i].frames_rendered==before_frames[i]);
                assert(counters[i].pages_submitted==before_pages[i]);
                vh_audio_output_ramp_arm(&envelopes[i]);
                assert(envelopes[i].position==0u);
            }
            home_reopens+=2u;
        }
        if(block==22u || block==57u || block==81u) {
            for(unsigned i=0;i<2u;i++)
                assert(vh_music_scene_request(&music[i],
                    block==57u?&field_cue:&selected_cue,4)==0);
        }
        for(unsigned i=0;i<2u;i++) {
            assert(vh_music_scene_render(&music[i],pcm[i])==0);
            const size_t count=vh_audio_resample_process(
                &resampler[i],pcm[i],VH_AUDIO_BLOCK_FRAMES,
                output[i],VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(count>=555u && count<=559u);
            assert(vh_audio_output_ramp_apply(
                &envelopes[i],output[i],count)==0);
            assert(envelopes[i].position==VH_AUDIO_OUTPUT_RAMP_FRAMES);
            /* The page is transformed exactly once, BEFORE the
             * bounded submit retry. MockOutput fingerprints it at
             * the first attempt and checks every replay byte. */
            const unsigned faults=i==1u ?
                (block%19u==5u ? 2u :
                (block%13u==3u ? 1u:0u)) : 0u;
            if(i==1u && faults) {
                expected_restarts+=faults;
                expected_bad_submits+=faults;
                ++expected_recoveries;
            }
            next_page(&device[i],faults);
            assert(vh_audio_output_submit_recover(
                &ops[i],&counters[i],output[i],count)==0);
            assert(counters[i].pages_submitted==block+1u);
            assert(resampler[i].input_frames==(uint64_t)(block+1u)*512u);
            assert(music[i].blocks_rendered==block+1u);
            /* A scene transition intentionally resets the SPU voice
             * clock; compare it to the failure-free reference instead
             * of assuming it grows across scene replacements. */
        }
        assert(spu[0].frames_rendered==spu[1].frames_rendered);
        assert(music[0].active.id==music[1].active.id);
        assert(music[0].stage==music[1].stage);
        assert(music[0].seq.note_ons==music[1].seq.note_ons);
        assert(music[0].seq.cycles_completed==music[1].seq.cycles_completed);
        assert(resampler[0].next_output_tick==
               resampler[1].next_output_tick);
        assert(counters[0].frames_submitted==
               counters[1].frames_submitted);
        assert(envelopes[0].position==envelopes[1].position);
        assert(memcmp(output[0],output[1],
                      device[0].attempted_frames*2u*sizeof(int16_t))==0);
        assert(device[0].checksum==device[1].checksum);
    }
    assert(home_reopens==8u && home_start_failures==2u);
    assert(counters[0].resume_restarts==4u);
    assert(counters[1].resume_restarts==6u);
    assert(counters[0].resume_recoveries==4u);
    assert(counters[1].resume_recoveries==4u);
    assert(counters[1].resume_failures==2u);
    assert(counters[1].recoveries==expected_recoveries);
    assert(counters[1].restart_attempts==expected_restarts);
    assert(counters[1].submit_failures==expected_bad_submits);
    assert(counters[0].recoveries==0u);
    assert(device[0].checksum!=UINT64_C(1469598103934665603));
    assert(device[0].accepted_pages==TOTAL_BLOCKS);
    assert(device[1].accepted_pages==TOTAL_BLOCKS);
    printf("audout recovery: %u seamless PCM pages, %u restarts PASS\n",
           TOTAL_BLOCKS,expected_restarts);
}

int main(void) {
    test_failed_restart_paths();
    test_resume_restart_paths();
    test_replay_prepared_page_preserves_music_clock();
    puts("bounded device error recovery and SEQ/SPU clock preservation: PASS");
    return 0;
}
