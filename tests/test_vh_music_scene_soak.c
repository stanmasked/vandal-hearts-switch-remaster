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
    return 0;
}
