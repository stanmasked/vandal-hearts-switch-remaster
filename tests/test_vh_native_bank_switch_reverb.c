/* Differential A/B VAB music-scene soak: EON-enabled STUDIO_C path
 * versus identical voices mixed dry. This is synthetic-only evidence.
 * No original game audio or Switch hardware is required.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_native_vab.h"
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

#define VH_SIZE (32u+128u*16u+512u+512u)
#define SCENES 16u
#define BLOCKS_PER_SCENE 16u

static uint8_t vh[2][VH_SIZE], vb[2][48];
static int16_t decoded[2][56];
static VhNativeVab banks[2];
static VhNativeSpu wet, dry;
static VhNativeSeq seq_wet, seq_dry;
static VhAudioResample resample_wet, resample_dry;
static int16_t raw_wet[512u*2u], raw_dry[512u*2u];
static int16_t pcm_wet[640u*2u], pcm_dry[640u*2u];
static uint32_t seam_wet[SCENES-1u], seam_dry[SCENES-1u];
static uint32_t seam_wet_contribution[SCENES-1u];
static uint32_t source_seam_wet[SCENES-1u], source_seam_dry[SCENES-1u];
static uint32_t output_fraction[SCENES-1u];
static const uint8_t song[]={
    'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
    0,0xc0,7,0,0x90,60,110,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};

static void load_bank(unsigned b) {
    uint8_t *h=vh[b], *v=vb[b];
    memcpy(h,"pBAV",4u);
    h[18]=8;h[20]=1;h[22]=1;h[24]=127;
    const size_t p=32u+7u*16u;
    h[p]=1;h[p+1]=127;h[p+4]=64;
    const size_t t=32u+128u*16u;
    h[t+1]=4; /* VagAtr.mode bit 2: send voice to STUDIO_C */
    h[t+2]=127;h[t+3]=64;h[t+4]=60;
    h[t+6]=40;h[t+7]=100;h[t+16]=15;
    h[t+20]=7;h[t+22]=1;
    h[t+512]=2;h[t+514]=4;
    v[16]=2;v[17]=4;
    memset(v+18,b ? 0x44 : 0x22,14u);
    v[32]=2;v[33]=3;
    memset(v+34,b ? 0xdd : 0xee,14u);
    assert(vh_native_vab_load(&banks[b],h,VH_SIZE,v,48u,
                              decoded[b],56u)==0);
    VhSeqTone tone={0};
    assert(vh_native_vab_resolve(
        &banks[b],7u,60u,110u,127u,64u,&tone)==0);
    assert(tone.reverb_send==1u);
    assert(tone.pcm==banks[b].samples[1].pcm);
}
static uint32_t magnitude(int value) {
    return (uint32_t)(value<0 ? -value : value);
}
static uint32_t max2(uint32_t a,uint32_t b) {
    return a>b?a:b;
}
static void print_seams(const char *label,const uint32_t *values) {
    printf("%s:",label);
    for(unsigned i=0;i<SCENES-1u;i++)
        printf(" %u",values[i]);
    putchar('\n');
}
int main(void) {
    load_bank(0u);
    load_bank(1u);
    assert(banks[0].samples[1].pcm!=banks[1].samples[1].pcm);
    vh_native_spu_reset(&wet);
    vh_native_spu_reset(&dry);
    assert(vh_native_spu_set_reverb(&wet,1,0.5f)==0);
    assert(vh_native_spu_set_reverb(&dry,0,0.0f)==0);
    vh_audio_resample_reset(&resample_wet);
    vh_audio_resample_reset(&resample_dry);

    int16_t last_wet[2]={0,0},last_dry[2]={0,0};
    int16_t last_raw_wet[2]={0,0},last_raw_dry[2]={0,0};
    uint64_t differing_samples=0;
    uint64_t output_frames=0;
    int have_last=0;
    for(unsigned scene_index=0;scene_index<SCENES;scene_index++) {
        const unsigned bank_index=scene_index%2u;
        if (!scene_index) {
            assert(vh_native_seq_init(&seq_wet,song,sizeof song,&wet,
                       vh_native_vab_resolve,&banks[bank_index],0)==0);
            assert(vh_native_seq_init(&seq_dry,song,sizeof song,&dry,
                       vh_native_vab_resolve,&banks[bank_index],0)==0);
        } else {
            const int old_cursor=wet.reverb.cursor;
            const int old_phase=wet.reverb.phase;
            const int16_t old_work=wet.reverb.work[0];
            assert(vh_native_seq_switch_scene(&seq_wet,song,sizeof song,
                       &wet,vh_native_vab_resolve,&banks[bank_index],0)==0);
            assert(vh_native_seq_switch_scene(&seq_dry,song,sizeof song,
                       &dry,vh_native_vab_resolve,&banks[bank_index],0)==0);
            assert(wet.reverb.cursor==old_cursor);
            assert(wet.reverb.phase==old_phase);
            assert(wet.reverb.work[0]==old_work);
            assert(wet.reverb_enabled && wet.reverb_depth==0.5f);
            assert(!dry.reverb_enabled);
            for(unsigned voice=0;voice<VH_NATIVE_MUSIC_VOICES;voice++) {
                assert(wet.voice[voice].pcm==NULL);
                assert(dry.voice[voice].pcm==NULL);
            }
        }
        for(unsigned block=0;block<BLOCKS_PER_SCENE;block++) {
            assert(vh_native_seq_advance_block(&seq_wet)>=0);
            assert(vh_native_seq_advance_block(&seq_dry)>=0);
            if (!block) {
                unsigned bound=0;
                for(unsigned voice=0;voice<VH_NATIVE_MUSIC_VOICES;voice++) {
                    if (wet.voice[voice].pcm) {
                        assert(wet.voice[voice].pcm==
                               banks[bank_index].samples[1].pcm);
                        assert(wet.voice[voice].reverb_send==1);
                        assert(dry.voice[voice].pcm==wet.voice[voice].pcm);
                        ++bound;
                    }
                }
                assert(bound>0u);
            }
            vh_native_spu_render(&wet,raw_wet,512u);
            vh_native_spu_render(&dry,raw_dry,512u);
            if (!block && scene_index && have_last) {
                uint32_t raw_w=0,raw_d=0;
                for(unsigned ch=0;ch<2u;ch++) {
                    raw_w=max2(raw_w,magnitude(
                        (int)raw_wet[ch]-(int)last_raw_wet[ch]));
                    raw_d=max2(raw_d,magnitude(
                        (int)raw_dry[ch]-(int)last_raw_dry[ch]));
                }
                source_seam_wet[scene_index-1u]=raw_w;
                source_seam_dry[scene_index-1u]=raw_d;
                output_fraction[scene_index-1u]=(uint32_t)(
                    resample_wet.next_output_tick % VH_NATIVE_AUDOUT_RATE);
            }
            last_raw_wet[0]=raw_wet[2u*511u];
            last_raw_wet[1]=raw_wet[2u*511u+1u];
            last_raw_dry[0]=raw_dry[2u*511u];
            last_raw_dry[1]=raw_dry[2u*511u+1u];
            const size_t n=vh_audio_resample_process(
                &resample_wet,raw_wet,512u,pcm_wet,640u);
            const size_t n_dry=vh_audio_resample_process(
                &resample_dry,raw_dry,512u,pcm_dry,640u);
            assert(n>=555u && n<=559u && n==n_dry);
            output_frames+=n;
            if (!block && scene_index && have_last) {
                uint32_t wm=0,dm=0,wet_part=0;
                for(unsigned ch=0;ch<2u;ch++) {
                    const int before_wet=last_wet[ch];
                    const int before_dry=last_dry[ch];
                    const int after_wet=pcm_wet[ch];
                    const int after_dry=pcm_dry[ch];
                    wm=max2(wm,magnitude(after_wet-before_wet));
                    dm=max2(dm,magnitude(after_dry-before_dry));
                    wet_part=max2(wet_part,magnitude(
                        (after_wet-after_dry)-(before_wet-before_dry)));
                }
                seam_wet[scene_index-1u]=wm;
                seam_dry[scene_index-1u]=dm;
                seam_wet_contribution[scene_index-1u]=wet_part;
            }
            for(size_t sample=0;sample<2u*n;sample++)
                differing_samples+=(pcm_wet[sample]!=pcm_dry[sample]);
            last_wet[0]=pcm_wet[2u*(n-1u)];
            last_wet[1]=pcm_wet[2u*(n-1u)+1u];
            last_dry[0]=pcm_dry[2u*(n-1u)];
            last_dry[1]=pcm_dry[2u*(n-1u)+1u];
            have_last=1;
        }
        assert(wet.frames_rendered==BLOCKS_PER_SCENE*512u);
        assert(dry.frames_rendered==BLOCKS_PER_SCENE*512u);
        assert(seq_wet.note_ons>0u && seq_dry.note_ons==seq_wet.note_ons);
    }
    assert(differing_samples>0u);
    assert(output_frames>130000u);
    assert(resample_wet.input_frames==(uint64_t)SCENES*BLOCKS_PER_SCENE*512u);
    assert(resample_dry.input_frames==resample_wet.input_frames);
    assert(resample_wet.next_output_tick==resample_dry.next_output_tick);
    assert(resample_wet.next_output_tick==output_frames*44100u);
    assert(seam_dry[0]==112u && seam_dry[1]==365u && seam_dry[2]==125u);
    print_seams("VAB differential dry seams PCM16",seam_dry);
    print_seams("VAB differential wet seams PCM16",seam_wet);
    print_seams("VAB differential wet-only adjacent changes PCM16",
                seam_wet_contribution);
    print_seams("VAB SPU dry scene seams 44100Hz PCM16",source_seam_dry);
    print_seams("VAB SPU wet scene seams 44100Hz PCM16",source_seam_wet);
    print_seams("VAB resampler boundary fractions 48000Hz",output_fraction);
    printf("VAB differential EON wet/dry: %llu differing samples, %u switches PASS\n",
           (unsigned long long)differing_samples,SCENES-1u);
    return 0;
}
