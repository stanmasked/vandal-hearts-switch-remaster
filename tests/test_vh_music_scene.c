/* Asset-free event-driven gameplay music transition regression.
 * Two synthetic pQES compositions and raw PCM fixtures are used.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_music_scene.h"

static VhNativeSpu synth, reference_synth;
static VhMusicScene scene, reference_scene;
static int16_t out[512u * 2u], reference[512u * 2u];
static int16_t pcm_a[128], pcm_b[128];
static unsigned calls_a, calls_b;

#define HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0
static const uint8_t song_a[] = {
    HDR,
    0,0xc0,7, 0,0x90,60,100,
    0x87,0x68,0x80,60,0,0,0xff,0x2f
};
static const uint8_t song_b[] = {
    HDR,
    0,0xc0,9, 0,0x90,64,110,
    0x87,0x68,0x80,64,0,0,0xff,0x2f
};
static const uint8_t broken[] = {HDR, 0,0x90,64};
static const VhMusicCue a = {101u,song_a,sizeof song_a,0u,NULL,NULL};
static const VhMusicCue b = {202u,song_b,sizeof song_b,0u,NULL,NULL};

static int resolve(void *ctx, unsigned program, unsigned note,
                   unsigned velocity, unsigned volume, unsigned pan,
                   VhSeqTone *tone) {
    (void)ctx;(void)velocity;(void)volume;(void)pan;
    memset(tone,0,sizeof(*tone));
    if (program==7 && note==60) {
        tone->pcm=pcm_a;
        ++calls_a;
    } else if(program==9 && note==64) {
        tone->pcm=pcm_b;
        ++calls_b;
    } else return -1;
    tone->frames=128;
    tone->loop_start=0;tone->loop_end=128;
    tone->pitch_step=4096;
    tone->adsr1=15;
    tone->adsr2=0;
    tone->gain_left=0.75f;
    tone->gain_right=0.4f;
    tone->reverb_send=1;
    return 0;
}
static VhMusicCue cue_a(void) {
    VhMusicCue cue=a;
    cue.resolver=resolve;
    return cue;
}
static VhMusicCue cue_b(void) {
    VhMusicCue cue=b;
    cue.resolver=resolve;
    return cue;
}

static void setup(void) {
    calls_a=calls_b=0;
    for(unsigned i=0;i<128;i++) {
        pcm_a[i]=(int16_t)(11000+(int)i*17);
        pcm_b[i]=(int16_t)(-10000-(int)i*13);
    }
    vh_native_spu_reset(&synth);
    assert(vh_native_spu_set_interpolation(&synth,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&synth,1,0.5f)==0);
    vh_music_scene_init(&scene,&synth);
    assert(vh_music_scene_active_id(&scene)==0);
    assert(scene.stage==VH_MUSIC_SILENT);
    assert(scene.spu==&synth);
}

static int has_signal(const int16_t *pcm) {
    for(unsigned i=0;i<1024;i++)
        if(pcm[i]) return 1;
    return 0;
}

static void test_validation_and_zero_fade_restart(void) {
    setup();
    VhMusicCue invalid={301u,broken,sizeof broken,0,resolve,NULL};
    assert(vh_music_scene_request(&scene,&invalid,2)==-1);
    assert(scene.stage==VH_MUSIC_SILENT && !scene.switches);
    assert(vh_music_scene_request(&scene,NULL,0)==0);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(!has_signal(out));
    assert(scene.blocks_rendered==1);

    VhMusicCue c=cue_a();
    assert(vh_music_scene_request(&scene,&c,0)==0);
    assert(scene.stage==VH_MUSIC_PLAYING && scene.switches==1);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(has_signal(out) && scene.seq.note_ons==1);
    assert(vh_music_scene_active_id(&scene)==101u);
    assert(calls_a==1);
    assert(scene.seq.blocks_advanced==1);

    const uint64_t frames=synth.frames_rendered;
    assert(vh_music_scene_request(&scene,&c,7)==0);
    assert(scene.stage==VH_MUSIC_PLAYING);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(calls_a==1 && scene.switches==1);
    assert(synth.frames_rendered==frames+512u);
    assert(vh_music_scene_request(&scene,&invalid,0)==-1);
    assert(scene.switches==1 && scene.active.id==101u);

    VhMusicCue other=cue_b();
    assert(vh_music_scene_request(&scene,&other,
                                 VH_MUSIC_SCENE_MAX_FADE_BLOCKS+1)==-1);
    assert(vh_music_scene_request(&scene,&other,0)==0);
    assert(scene.switches==2 && scene.active.id==202u);
    assert(scene.seq.note_ons==0);
    assert(synth.interpolation==VH_SPU_GAUSSIAN);
    assert(synth.reverb_enabled && synth.reverb_depth==0.5f);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(calls_b==1 && scene.seq.note_ons==1 && has_signal(out));
}

static void test_two_block_fade_and_silence(void) {
    setup();
    VhMusicCue first=cue_a(),second=cue_b();
    assert(vh_music_scene_request(&scene,&first,0)==0);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(has_signal(out));
    assert(vh_music_scene_request(&scene,&second,2)==0);
    assert(scene.stage==VH_MUSIC_FADE_OUT);
    assert(vh_music_scene_request(&scene,NULL,0)==-2);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.stage==VH_MUSIC_FADE_OUT);
    assert(scene.active.id==101u && scene.fade_position==1);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.stage==VH_MUSIC_SWITCH_PENDING);
    assert(!out[1022] && !out[1023]); /* faded to exact zero */
    assert(scene.active.id==101u && calls_b==0);
    assert(vh_music_scene_request(&scene,&second,0)==-2);

    const uint64_t rendered_before=scene.blocks_rendered;
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.blocks_rendered==rendered_before+1);
    assert(scene.stage==VH_MUSIC_FADE_IN);
    assert(scene.active.id==202u && scene.switches==2);
    assert(scene.seq.note_ons==1 && calls_b==1);
    assert(synth.voice[0].pcm==pcm_b && synth.voice[0].reverb_send);
    assert(synth.interpolation==VH_SPU_GAUSSIAN && synth.reverb_enabled);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.stage==VH_MUSIC_PLAYING);
    assert(vh_music_scene_active_id(&scene)==202u);

    assert(vh_music_scene_request(&scene,NULL,1)==0);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(!out[1022] && !out[1023]);
    assert(scene.stage==VH_MUSIC_SWITCH_PENDING);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.stage==VH_MUSIC_SILENT);
    assert(!has_signal(out));
    assert(scene.active.id==0 && scene.switches==3);
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++)
        assert(!synth.voice[i].active);
    for(unsigned i=0;i<VH_REV_SAMPLES;i++)
        assert(synth.reverb.work[i]==0);
    assert(scene.blocks_rendered==7);
}

static void test_fade_ramp_matches_unscaled_audio(void) {
    setup();
    VhMusicCue first=cue_a();
    vh_native_spu_reset(&reference_synth);
    assert(vh_native_spu_set_interpolation(
        &reference_synth,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&reference_synth,1,0.5f)==0);
    vh_music_scene_init(&reference_scene,&reference_synth);
    assert(vh_music_scene_request(&scene,&first,1)==0);
    assert(vh_music_scene_request(&reference_scene,&first,0)==0);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(vh_music_scene_render(&reference_scene,reference)==0);
    for(unsigned i=0;i<512;i++) {
        const int32_t gain=(int32_t)((int64_t)(i+1)*32768/512);
        for(unsigned ch=0;ch<2;ch++) {
            const int16_t expected=(int16_t)(
                ((int64_t)reference[2*i+ch]*gain)/32768);
            assert(out[2*i+ch]==expected);
        }
    }
    assert(scene.stage==VH_MUSIC_PLAYING);
    assert(scene.blocks_rendered==1u && reference_scene.blocks_rendered==1u);
}

static void test_pending_corruption_fails_closed(void) {
    setup();
    VhMusicCue first=cue_a();
    assert(vh_music_scene_request(&scene,&first,0)==0);
    assert(vh_music_scene_render(&scene,out)==0);

    uint8_t mutable_song[sizeof song_b];
    memcpy(mutable_song,song_b,sizeof mutable_song);
    VhMusicCue pending=cue_b();
    pending.seq=mutable_song;
    assert(vh_music_scene_request(&scene,&pending,1)==0);
    mutable_song[0]='X'; /* a caller must keep queued assets stable */
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.stage==VH_MUSIC_SWITCH_PENDING);
    memset(out,0x7f,sizeof out);
    assert(vh_music_scene_render(&scene,out)==-1);
    assert(scene.last_error);
    assert(!has_signal(out));
    memset(out,0x7f,sizeof out);
    assert(vh_music_scene_render(&scene,out)==-1);
    assert(!has_signal(out));
    assert(vh_music_scene_request(&scene,&first,0)==-1);
}

static void assert_scene_fully_detached(void) {
    assert(scene.stage==VH_MUSIC_SILENT);
    assert(scene.active.id==0u && scene.pending.id==0u);
    assert(scene.active.seq==NULL && scene.pending.seq==NULL);
    assert(scene.active.context==NULL && scene.pending.context==NULL);
    assert(scene.seq.bytes==NULL && scene.seq.context==NULL);
    assert(scene.seq.resolver==NULL && !scene.seq.playing);
    assert(scene.fade_blocks==0u && scene.fade_position==0u);
    assert(scene.next_fade_in==0u && !scene.last_error);
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++) {
        assert(synth.voice[i].pcm==NULL);
        assert(!synth.voice[i].active);
    }
    for(unsigned i=0;i<VH_REV_SAMPLES;i++)
        assert(synth.reverb.work[i]==0);
    assert(synth.interpolation==VH_SPU_GAUSSIAN);
    assert(synth.reverb_enabled==1 && synth.reverb_depth==0.5f);
}

static void test_forced_bank_detach_in_all_fade_stages(void) {
    setup();
    VhMusicCue first=cue_a(),second=cue_b();
    assert(vh_music_scene_detach(NULL)==-1);
    VhMusicScene invalid={0};
    assert(vh_music_scene_detach(&invalid)==-1);
    assert(vh_music_scene_detach(&scene)==0);
    const uint32_t initial_switches=scene.switches;
    assert(vh_music_scene_detach(&scene)==0);
    assert(scene.switches==initial_switches);
    for(unsigned stage=0;stage<4u;++stage) {
        assert(vh_music_scene_request(&scene,&first,0)==0);
        assert(vh_music_scene_render(&scene,out)==0);
        assert(has_signal(out));
        if(stage==0u) {
            assert(scene.stage==VH_MUSIC_PLAYING);
        } else {
            assert(vh_music_scene_request(&scene,&second,2)==0);
            if(stage>=2u) {
                assert(vh_music_scene_render(&scene,out)==0);
                assert(vh_music_scene_render(&scene,out)==0);
                assert(scene.stage==VH_MUSIC_SWITCH_PENDING);
            }
            if(stage==3u) {
                assert(vh_music_scene_render(&scene,out)==0);
                assert(scene.stage==VH_MUSIC_FADE_IN);
            }
            if(stage==1u) assert(scene.stage==VH_MUSIC_FADE_OUT);
        }
        assert(vh_music_scene_request(&scene,NULL,0)==
               (stage==0u ? 0 : -2));
        if(stage==0u) {
            /* Recreate an active owner to test the detach path. */
            assert(vh_music_scene_request(&scene,&first,0)==0);
            assert(vh_music_scene_render(&scene,out)==0);
        }
        const uint64_t blocks=scene.blocks_rendered;
        const uint32_t switches=scene.switches;
        assert(vh_music_scene_detach(&scene)==0);
        assert(scene.blocks_rendered==blocks);
        assert(scene.switches==switches+1u);
        assert_scene_fully_detached();

        /* Source memory is now logically invalid; clearing it must
         * never contaminate subsequent silence or the next cue. */
        memset(pcm_a,0xa5,sizeof pcm_a);
        memset(pcm_b,0x5a,sizeof pcm_b);
        memset(out,0x7f,sizeof out);
        assert(vh_music_scene_render(&scene,out)==0);
        assert(!has_signal(out));
        assert(vh_music_scene_detach(&scene)==0);
        assert(scene.switches==switches+1u);
        /* Restore the synthetic source before starting another pass. */
        for(unsigned i=0;i<128u;i++) {
            pcm_a[i]=(int16_t)(11000+(int)i*17);
            pcm_b[i]=(int16_t)(-10000-(int)i*13);
        }
    }
    assert(vh_music_scene_request(&scene,&second,0)==0);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.active.id==202u && synth.voice[0].pcm==pcm_b);
    assert(has_signal(out));
    assert(vh_music_scene_detach(&scene)==0);
    assert_scene_fully_detached();
}

/* The old director deliberately reset STUDIO_C between cues. Make
 * continuity opt-in so installed gameplay keeps the historical behavior.
 * All PCM and SEQ bytes in these regressions are synthetic. */
static VhSpuReverb switch_tail_before;
static int wet_nonzero(const VhSpuReverb *tail) {
    for(unsigned i=0;i<VH_REV_SAMPLES;i++)
        if(tail->work[i]!=0) return 1;
    return 0;
}
static void test_optional_wet_tail_direct_switch(void) {
    setup();
    VhMusicCue first=cue_a(),second=cue_b();
    assert(scene.keep_reverb_across_cues==0u);
    assert(vh_music_scene_set_reverb_continuity(NULL,1)==-1);
    assert(vh_music_scene_set_reverb_continuity(&scene,-1)==-1);
    assert(vh_music_scene_set_reverb_continuity(&scene,2)==-1);
    assert(scene.keep_reverb_across_cues==0u);
    assert(vh_music_scene_set_reverb_continuity(&scene,1)==0);
    assert(scene.keep_reverb_across_cues==1u);
    assert(vh_music_scene_request(&scene,&first,0u)==0);
    assert(vh_music_scene_set_reverb_continuity(&scene,0)==-1);
    for(unsigned frame=0;frame<64u;frame++)
        assert(vh_music_scene_render(&scene,out)==0);
    assert(vh_music_scene_active_id(&scene)==101u &&
           scene.seq.note_ons==1u &&
           synth.voice[0].pcm==pcm_a &&
           wet_nonzero(&synth.reverb));
    switch_tail_before=synth.reverb;
    VhMusicCue invalid={303u,broken,sizeof broken,1u,resolve,NULL};
    assert(vh_music_scene_request(&scene,&invalid,0u)==-1);
    assert(scene.active.id==101u && !scene.last_error);
    assert(!memcmp(&synth.reverb,&switch_tail_before,
                   sizeof switch_tail_before));
    assert(vh_music_scene_request(&scene,&second,0u)==0);
    assert(scene.active.id==202u && scene.stage==VH_MUSIC_PLAYING &&
           scene.switches==2u && scene.seq.note_ons==0u);
    assert(!memcmp(&synth.reverb,&switch_tail_before,
                   sizeof switch_tail_before));
    assert(synth.interpolation==VH_SPU_GAUSSIAN &&
           synth.reverb_enabled && synth.reverb_depth==0.5f);
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++)
        assert(!synth.voice[i].active && synth.voice[i].pcm==NULL);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.seq.note_ons==1u && synth.voice[0].pcm==pcm_b);
    assert(vh_music_scene_request(&scene,NULL,0u)==0);
    assert(scene.stage==VH_MUSIC_SILENT && !wet_nonzero(&synth.reverb));
    assert(scene.keep_reverb_across_cues==1u);
    assert(vh_music_scene_detach(&scene)==0);
    assert(scene.keep_reverb_across_cues==1u);
    assert(vh_music_scene_set_reverb_continuity(&scene,0)==0);
    assert(scene.keep_reverb_across_cues==0u);
}

static void test_default_reset_and_opted_fade_comparison(void) {
    setup();
    VhMusicCue first=cue_a(),second=cue_b();
    vh_native_spu_reset(&reference_synth);
    assert(vh_native_spu_set_interpolation(
        &reference_synth,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&reference_synth,1,0.5f)==0);
    vh_music_scene_init(&reference_scene,&reference_synth);
    assert(vh_music_scene_set_reverb_continuity(&scene,1)==0);
    assert(!reference_scene.keep_reverb_across_cues);
    assert(vh_music_scene_request(&scene,&first,0u)==0);
    assert(vh_music_scene_request(&reference_scene,&first,0u)==0);
    for(unsigned block=0u;block<64u;block++) {
        assert(vh_music_scene_render(&scene,out)==0);
        assert(vh_music_scene_render(&reference_scene,reference)==0);
        assert(!memcmp(out,reference,sizeof out));
    }
    assert(wet_nonzero(&synth.reverb));
    assert(!memcmp(&synth.reverb,&reference_synth.reverb,
                   sizeof synth.reverb));
    assert(vh_music_scene_request(&scene,&second,2u)==0);
    assert(vh_music_scene_request(&reference_scene,&second,2u)==0);
    for(unsigned block=0u;block<2u;block++) {
        assert(vh_music_scene_render(&scene,out)==0);
        assert(vh_music_scene_render(&reference_scene,reference)==0);
        assert(!memcmp(out,reference,sizeof out));
    }
    assert(scene.stage==VH_MUSIC_SWITCH_PENDING &&
           reference_scene.stage==VH_MUSIC_SWITCH_PENDING);
    assert(wet_nonzero(&synth.reverb));
    assert(vh_music_scene_render(&scene,out)==0);
    assert(vh_music_scene_render(&reference_scene,reference)==0);
    assert(scene.stage==VH_MUSIC_FADE_IN &&
           reference_scene.stage==VH_MUSIC_FADE_IN);
    assert(scene.active.id==202u && reference_scene.active.id==202u);
    assert(synth.voice[0].pcm==pcm_b &&
           reference_synth.voice[0].pcm==pcm_b);
    assert(wet_nonzero(&synth.reverb));
    assert(memcmp(&synth.reverb,&reference_synth.reverb,
                  sizeof synth.reverb)!=0);
    assert(vh_music_scene_detach(&scene)==0);
    assert(vh_music_scene_detach(&reference_scene)==0);
    assert(!wet_nonzero(&synth.reverb) &&
           !wet_nonzero(&reference_synth.reverb));
}

/* A queued cue may change in caller-owned storage between request and
 * the actual 512-frame transition. With continuity enabled, a corrupted
 * pending SEQ must be rejected BEFORE detaching the current PCM voices
 * or altering the precharged wet tail. Teardown is still permitted. */
static VhNativeSpu opted_failure_spu;
static VhNativeSeq opted_failure_seq;
static void test_opted_pending_corruption_preserves_active_bank(void) {
    setup();
    VhMusicCue first=cue_a();
    assert(vh_music_scene_set_reverb_continuity(&scene,1)==0);
    assert(vh_music_scene_request(&scene,&first,0u)==0);
    for(unsigned i=0;i<64u;i++)
        assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.seq.note_ons==1u &&
           synth.voice[0].pcm==pcm_a &&
           wet_nonzero(&synth.reverb));
    uint8_t bytes[sizeof song_b];
    memcpy(bytes,song_b,sizeof bytes);
    VhMusicCue pending=cue_b();
    pending.seq=bytes;
    assert(vh_music_scene_request(&scene,&pending,1u)==0);
    assert(scene.stage==VH_MUSIC_FADE_OUT);
    assert(vh_music_scene_render(&scene,out)==0);
    assert(scene.stage==VH_MUSIC_SWITCH_PENDING);
    bytes[0]='X'; /* simulated caller mutation after preflight */
    opted_failure_spu=synth;
    opted_failure_seq=scene.seq;
    memset(out,0x7f,sizeof out);
    assert(vh_music_scene_render(&scene,out)==-1);
    assert(scene.last_error && !has_signal(out));
    assert(scene.active.id==101u && scene.pending.id==202u);
    assert(!memcmp(&scene.seq,&opted_failure_seq,
                   sizeof opted_failure_seq));
    assert(!memcmp(&synth,&opted_failure_spu,
                   sizeof opted_failure_spu));
    assert(vh_music_scene_request(&scene,&first,0u)==-1);
    assert(vh_music_scene_detach(&scene)==0);
    assert(scene.stage==VH_MUSIC_SILENT &&
           !scene.active.id && !scene.pending.id &&
           scene.keep_reverb_across_cues==1u);
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++)
        assert(!synth.voice[i].active && synth.voice[i].pcm==NULL);
    assert(!wet_nonzero(&synth.reverb));
}

int main(void) {
    test_validation_and_zero_fade_restart();
    test_two_block_fade_and_silence();
    test_fade_ramp_matches_unscaled_audio();
    test_pending_corruption_fails_closed();
    test_forced_bank_detach_in_all_fade_stages();
    test_optional_wet_tail_direct_switch();
    test_default_reset_and_opted_fade_comparison();
    test_opted_pending_corruption_preserves_active_bank();
    puts("game scene music cues: fade / switch / silence / validation PASS");
    return 0;
}
