/* Full synthetic scene-cue transitions and libnx 48k rate conversion.
 * Follows the audout probe's 384/768 block cue schedule but runs in
 * portable host C so console and proprietary resources aren't required.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_music_scene.h"
#include "vh_audio_resample.h"

#define BLOCKS 1200u
#define HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0
static const uint8_t seq_a[]={HDR,0,0xc0,7,0,0x90,60,100,
    0x87,0x68,0x80,60,0,0,0xff,0x2f};
static const uint8_t seq_b[]={HDR,0,0xc0,7,0,0x90,64,100,
    0x87,0x68,0x80,64,0,0,0xff,0x2f};
static VhMusicScene scene;
static VhNativeSpu synth;
static VhAudioResample converter;
static int16_t sample[128], pcm[1024], out[1280];

static int lookup(void *context, unsigned program, unsigned note,
                  unsigned velocity, unsigned volume, unsigned pan,
                  VhSeqTone *tone) {
    (void)context;(void)volume;(void)pan;
    if (program!=7 || (note!=60 && note!=64) || !velocity) return -1;
    memset(tone,0,sizeof(*tone));
    tone->pcm=sample;
    tone->frames=128;
    tone->loop_start=0;tone->loop_end=128;
    tone->pitch_step=note==60?4096u:5161u;
    tone->adsr1=15;
    tone->gain_left=0.8f;
    tone->gain_right=0.6f;
    tone->reverb_send=1;
    return 0;
}
static int cue(uint32_t id, unsigned fade) {
    const VhMusicCue c={
        id,id==2?seq_b:seq_a,
        id==2?sizeof(seq_b):sizeof(seq_a),
        0,lookup,NULL
    };
    return vh_music_scene_request(&scene,&c,fade);
}
static void rapid_scene_stress(void) {
    /* Game publishes 40 changes per block while the audio owner
     * consumes only the latest scene ID, without queue growth.
     */
    vh_native_spu_reset(&synth);
    vh_audio_resample_reset(&converter);
    vh_music_scene_init(&scene,&synth);
    assert(vh_native_spu_set_interpolation(&synth,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&synth,1,0.5f)==0);
    assert(cue(1,0)==0);
    unsigned accepted=1, deferred=0, updates=0;
    uint64_t frames=0;
    for(unsigned block=0; block<3200; ++block) {
        unsigned desired=1;
        if (block<2500) {
            for(unsigned input=0; input<40; ++input) {
                desired=((block / 7u + input) & 1u) ? 1u : 2u;
                ++updates;
            }
        }
        if (desired!=accepted) {
            const int result=cue(desired,8u);
            assert(result==0 || result==-2);
            if (!result) accepted=desired;
            else ++deferred;
        }
        assert(vh_music_scene_render(&scene,pcm)==0);
        const size_t count=vh_audio_resample_process(
            &converter,pcm,512,out,640);
        assert(count>=555 && count<=559);
        frames+=count;
        assert(converter.input_frames==(uint64_t)(block+1)*512u);
        assert(!scene.last_error);
        assert(scene.active.id==1 || scene.active.id==2);
    }
    assert(updates==2500u*40u);
    assert(deferred>0 && scene.switches>2);
    assert(accepted==1 && scene.active.id==1);
    assert(scene.stage==VH_MUSIC_PLAYING);
    assert(scene.switches<256);
    const uint64_t expected=((uint64_t)3200u*512u-1u)*160u/147u+1u;
    assert(frames>=expected-2 && frames<=expected+2);
    printf("rapid scene switches: PASS %u requests, %u deferred, %u switches, %llu frames\n",
           updates,deferred,scene.switches,(unsigned long long)frames);
}

/* Compare legacy and opt-in directors under the SAME game cue
 * schedule through the real 44.1->48 kHz transport, rather than
 * comparing only the internal 44.1-kHz SPU buffer. */
static VhMusicScene wet_scene, dry_scene;
static VhNativeSpu wet_spu, dry_spu;
static VhAudioResample wet_rate, dry_rate;
static int16_t wet_raw[1024], dry_raw[1024];
static int16_t wet_48k[1280], dry_48k[1280];
static int16_t opt_sample_a[128], opt_sample_b[128];

static int lookup_opt(void *context, unsigned program, unsigned note,
                      unsigned velocity, unsigned volume, unsigned pan,
                      VhSeqTone *tone) {
    (void)context;(void)volume;(void)pan;
    if(program!=7u || !velocity || (note!=60u && note!=64u))
        return -1;
    memset(tone,0,sizeof(*tone));
    tone->pcm=note==60u?opt_sample_a:opt_sample_b;
    tone->frames=128u;
    tone->loop_start=0;
    tone->loop_end=128;
    tone->pitch_step=note==60u?4096u:5161u;
    tone->adsr1=15;
    tone->gain_left=0.8f;
    tone->gain_right=0.6f;
    tone->reverb_send=1;
    return 0;
}
static void request_opt_pair(unsigned which,unsigned fade) {
    const VhMusicCue next={
        which,which==2u?seq_b:seq_a,
        which==2u?sizeof seq_b:sizeof seq_a,
        0u,lookup_opt,NULL
    };
    assert(vh_music_scene_request(&wet_scene,&next,fade)==0);
    assert(vh_music_scene_request(&dry_scene,&next,fade)==0);
}
static void opt_in_48k_comparison(void) {
    for(unsigned i=0u;i<128u;i++) {
        opt_sample_a[i]=(int16_t)(-8000+(int)i*127);
        opt_sample_b[i]=(int16_t)(9000-(int)i*123);
    }
    vh_native_spu_reset(&wet_spu);
    vh_native_spu_reset(&dry_spu);
    assert(vh_native_spu_set_interpolation(
        &wet_spu,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_interpolation(
        &dry_spu,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&wet_spu,1,0.5f)==0);
    assert(vh_native_spu_set_reverb(&dry_spu,1,0.5f)==0);
    vh_music_scene_init(&wet_scene,&wet_spu);
    vh_music_scene_init(&dry_scene,&dry_spu);
    vh_audio_resample_reset(&wet_rate);
    vh_audio_resample_reset(&dry_rate);
    assert(vh_music_scene_set_reverb_continuity(&wet_scene,1)==0);
    assert(dry_scene.keep_reverb_across_cues==0u);
    request_opt_pair(1u,0u);
    uint64_t delivered=0u;
    unsigned divergent_blocks=0u,frame_drift=0u;
    unsigned divergence_near_transition=0u,changed=0u;
    for(unsigned block=0u;block<512u;block++) {
        if(block==64u || block==192u || block==320u) {
            request_opt_pair(block==192u?1u:2u,8u);
            ++changed;
        }
        assert(vh_music_scene_render(&wet_scene,wet_raw)==0);
        assert(vh_music_scene_render(&dry_scene,dry_raw)==0);
        assert(wet_scene.blocks_rendered==dry_scene.blocks_rendered &&
               wet_scene.blocks_rendered==(uint64_t)block+1u);
        assert(wet_scene.stage==dry_scene.stage &&
               wet_scene.fade_position==dry_scene.fade_position &&
               wet_scene.switches==dry_scene.switches &&
               wet_scene.active.id==dry_scene.active.id);
        assert(wet_scene.seq.blocks_advanced==
               dry_scene.seq.blocks_advanced);
        assert(wet_scene.seq.note_ons==dry_scene.seq.note_ons &&
               wet_scene.seq.note_offs==dry_scene.seq.note_offs);
        const size_t wet_count=vh_audio_resample_process(
            &wet_rate,wet_raw,512u,wet_48k,640u);
        const size_t dry_count=vh_audio_resample_process(
            &dry_rate,dry_raw,512u,dry_48k,640u);
        assert(wet_count==dry_count &&
               wet_count>=555u && wet_count<=559u);
        delivered+=wet_count;
        assert(wet_rate.input_frames==dry_rate.input_frames &&
               wet_rate.input_frames==((uint64_t)block+1u)*512u);
        /* PCM history samples naturally differ with retained wet
         * reverb. Only transport CLOCK phase/count must remain equal. */
        if(wet_rate.input_frames!=dry_rate.input_frames ||
           wet_rate.next_output_tick!=dry_rate.next_output_tick ||
           wet_rate.have_previous!=dry_rate.have_previous)
            ++frame_drift;
        if(memcmp(wet_48k,dry_48k,wet_count*2u*sizeof(int16_t))!=0) {
            ++divergent_blocks;
            if(block>=73u && block<104u)
                ++divergence_near_transition;
        }
        assert(!wet_scene.last_error && !dry_scene.last_error);
        for(unsigned voice=0u;voice<VH_NATIVE_MUSIC_VOICES;voice++) {
            const int16_t *a=wet_spu.voice[voice].pcm;
            const int16_t *b=dry_spu.voice[voice].pcm;
            assert(!a || a==opt_sample_a || a==opt_sample_b);
            assert(!b || b==opt_sample_a || b==opt_sample_b);
        }
    }
    assert(changed==3u && wet_scene.switches==4u &&
           dry_scene.switches==4u);
    assert(divergent_blocks>0u && divergence_near_transition>0u &&
           frame_drift==0u);
    const uint64_t expected=(((uint64_t)512u*512u)-1u)*160u/147u+1u;
    assert(delivered>=expected-2u && delivered<=expected+2u);
    assert(vh_music_scene_detach(&wet_scene)==0);
    assert(vh_music_scene_detach(&dry_scene)==0);
    assert(wet_scene.active.id==0u && dry_scene.active.id==0u);
    printf("opt-in STUDIO_C -> 48k: PASS %u blocks, %u divergent, %llu frames\\n",
           512u,divergent_blocks,(unsigned long long)delivered);
}

int main(void) {
    for(unsigned i=0;i<128;i++)sample[i]=(int16_t)(
        (int)(i*237u%24000u)-12000);
    vh_native_spu_reset(&synth);
    assert(vh_native_spu_set_interpolation(&synth,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&synth,1,0.5f)==0);
    vh_audio_resample_reset(&converter);
    vh_music_scene_init(&scene,&synth);
    assert(cue(1,0)==0);

    uint64_t frames=0,nonzero=0;
    uint64_t checksum=UINT64_C(1469598103934665603);
    for(unsigned block=0;block<BLOCKS;block++) {
        if(block==384) assert(cue(2,8)==0);
        if(block==768) assert(cue(1,8)==0);
        assert(vh_music_scene_render(&scene,pcm)==0);
        const size_t count=vh_audio_resample_process(
            &converter,pcm,512,out,640);
        assert(count>=555 && count<=559);
        frames+=count;
        for(size_t k=0;k<2u*count;k++) {
            checksum^=(uint16_t)out[k];
            checksum*=UINT64_C(1099511628211);
            if(out[k])nonzero++;
        }
        assert(scene.blocks_rendered==(uint64_t)block+1);
        assert(converter.input_frames==scene.blocks_rendered*512u);
        assert(scene.last_error==0);
        if(block==391)assert(scene.stage==VH_MUSIC_SWITCH_PENDING);
        if(block==392)assert(scene.active.id==2 && scene.stage==VH_MUSIC_FADE_IN);
        if(block==399)assert(scene.stage==VH_MUSIC_PLAYING);
        if(block==775)assert(scene.stage==VH_MUSIC_SWITCH_PENDING);
        if(block==776)assert(scene.active.id==1 && scene.stage==VH_MUSIC_FADE_IN);
        if(block==783)assert(scene.stage==VH_MUSIC_PLAYING);
    }
    const uint64_t in_frames=(uint64_t)BLOCKS*512u;
    const uint64_t expected=(in_frames-1u)*160u/147u+1u;
    assert(frames>=expected-2 && frames<=expected+2);
    assert(scene.switches==3 && scene.active.id==1u);
    assert(scene.stage==VH_MUSIC_PLAYING && scene.fade_position==8);
    assert(nonzero>100000 && checksum!=UINT64_C(1469598103934665603));
    printf("scene->SEQ->SPU->STUDIO_C->48k: PASS %u blocks, %llu frames, 2 fades, checksum %016llx\n",
           BLOCKS,(unsigned long long)frames,(unsigned long long)checksum);
    rapid_scene_stress();
    opt_in_48k_comparison();
    return 0;
}
