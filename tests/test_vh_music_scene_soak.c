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
    return 0;
}
