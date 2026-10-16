/* Two fully decoded synthetic VH/VB banks, one persistent output clock.
 * Switching only after stopping SEQ and resetting SPU avoids dangling
 * voices referencing the previous bank's caller-owned sample arena.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_native_vab.h"
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

#define VH_SIZE (32u + 128u*16u + 512u + 512u)
static uint8_t vh[2][VH_SIZE], vb[2][48];
static int16_t pcm[2][56];
static VhNativeVab bank[2];
static VhNativeSpu spu;
static VhNativeSeq seq;
static VhAudioResample resampler;
static int16_t source[512u*2u], out[640u*2u];
static const uint8_t song[]={
    'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
    0,0xc0,7,0,0x90,60,110,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static void make_bank(unsigned b) {
    uint8_t *h=vh[b],*v=vb[b];
    memcpy(h,"pBAV",4u);
    h[18]=8;h[20]=1;h[22]=1;h[24]=127;
    const size_t p=32u+7u*16u;
    h[p]=1;h[p+1]=127;h[p+4]=64;
    const size_t t=32u+128u*16u;
    h[t+2]=127;h[t+3]=64;h[t+4]=60;
    h[t+6]=40;h[t+7]=100;h[t+16]=15;
    h[t+20]=7;h[t+22]=1;
    h[t+512]=2;h[t+514]=4;
    v[16]=2;v[17]=4;
    memset(v+18,b ? 0x44 : 0x22,14u);
    v[32]=2;v[33]=3;
    memset(v+34,b ? 0xdd : 0xee,14u);
    assert(vh_native_vab_load(&bank[b],h,VH_SIZE,v,48u,pcm[b],56u)==0);
}
int main(void) {
    make_bank(0);make_bank(1);
    assert(bank[0].samples[1].pcm!=bank[1].samples[1].pcm);
    assert(memcmp(pcm[0],pcm[1],56u*sizeof(int16_t))!=0);
    vh_audio_resample_reset(&resampler);
    uint64_t output_frames=0, checksum[2]={0,0};
    uint32_t seam_deltas[3]={0,0,0};
    int16_t last_left=0,last_right=0;
    int have_last=0;
    for (unsigned transition=0;transition<4u;transition++) {
        const unsigned scene=transition%2u;
        if (!transition) {
            vh_native_spu_reset(&spu);
            assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
            assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                                      vh_native_vab_resolve,&bank[scene],0)==0);
        } else {
            /* Reject bad new music atomically: the old scene must still
             * own its voices and its reverb history.
             */
            static const uint8_t invalid_seq[]={'p','Q','E','S'};
            const uint64_t old_frames=spu.frames_rendered;
            const uint64_t old_notes=seq.note_ons;
            const uint8_t *old_bytes=seq.bytes;
            const int16_t *old_pcm=spu.voice[0].pcm;
            const int old_cursor=spu.reverb.cursor;
            const int old_phase=spu.reverb.phase;
            const int16_t old_work=spu.reverb.work[0];
            assert(vh_native_seq_switch_scene(
                &seq,invalid_seq,sizeof invalid_seq,&spu,
                vh_native_vab_resolve,&bank[scene],0)==-1);
            assert(seq.bytes==old_bytes && seq.note_ons==old_notes);
            assert(spu.frames_rendered==old_frames);
            assert(spu.voice[0].pcm==old_pcm);
            assert(spu.reverb.cursor==old_cursor);

            /* A different SPU is not the current voice owner. Refuse
             * the transition without detaching or mutating either mixer.
             */
            static VhNativeSpu unrelated_spu;
            vh_native_spu_reset(&unrelated_spu);
            assert(vh_native_seq_switch_scene(
                &seq,song,sizeof song,&unrelated_spu,
                vh_native_vab_resolve,&bank[scene],0)==-1);
            assert(seq.bytes==old_bytes && seq.note_ons==old_notes);
            assert(spu.voice[0].pcm==old_pcm);
            assert(spu.frames_rendered==old_frames);
            assert(unrelated_spu.frames_rendered==0u);
            assert(unrelated_spu.voice[0].pcm==NULL);

            /* Successful switch releases all old voices but preserves
             * STUDIO_C's delay/FIR history and its wet configuration.
             */
            assert(vh_native_seq_switch_scene(
                &seq,song,sizeof song,&spu,
                vh_native_vab_resolve,&bank[scene],0)==0);
            assert(seq.bytes==song && seq.note_ons==0u);
            assert(spu.reverb.cursor==old_cursor);
            assert(spu.reverb.phase==old_phase);
            assert(spu.reverb.work[0]==old_work);
            assert(spu.reverb_enabled && spu.reverb_depth==0.5f);
            assert(spu.frames_rendered==0u);
            for (unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
                assert(spu.voice[slot].pcm==NULL);
                assert(!spu.voice[slot].active);
            }
        }
        for (unsigned block=0;block<16u;block++) {
            assert(vh_native_seq_advance_block(&seq)>=0);
            if (block==0u) {
                /* The first note after each switch must bind to the new
                 * bank, never to the previous bank's decoded PCM arena.
                 */
                unsigned bound=0;
                for (unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
                    if (spu.voice[slot].pcm) {
                        assert(spu.voice[slot].pcm==bank[scene].samples[1].pcm);
                        if (scene)
                            assert(spu.voice[slot].pcm!=bank[0].samples[1].pcm);
                        ++bound;
                    }
                }
                assert(bound>0u);
            }
            vh_native_spu_render(&spu,source,512u);
            size_t n=vh_audio_resample_process(
                &resampler,source,512u,out,640u);
            assert(n>=555u && n<=559u);
            output_frames+=n;
            if (block==0u && transition>0u && have_last) {
                const int dl=(int)out[0]-(int)last_left;
                const int dr=(int)out[1]-(int)last_right;
                seam_deltas[transition-1u]=(uint32_t)(dl<0?-dl:dl);
                const unsigned right=(unsigned)(dr<0?-dr:dr);
                if(right>seam_deltas[transition-1u])
                    seam_deltas[transition-1u]=right;
            }
            last_left=out[2u*(n-1u)];
            last_right=out[2u*(n-1u)+1u];
            have_last=1;
            for(size_t i=0;i<n*2u;i++)
                checksum[scene]=checksum[scene]*UINT64_C(1099511628211)
                                +(uint16_t)out[i]+1u;
        }
        assert(spu.frames_rendered==16u*512u);
        assert(seq.note_ons>0u);
        assert(bank[scene].selected_program==7u);
        assert(bank[scene].selected_vag==1u);
    }
    /* Bank A and B must each trigger notes; no lost sequencer state. */
    assert(output_frames>34000u);
    assert(resampler.input_frames==64u*512u);
    const uint64_t expected=((uint64_t)64u*512u-1u)*160u/147u+1u;
    assert(output_frames+2u>=expected && output_frames<=expected+1u);
    assert(resampler.next_output_tick==output_frames*44100u);
    assert(checksum[0]!=checksum[1]);
    /* Synthetic-only guard: the known stable transitions stay below 1024
     * PCM16 steps. Never use this threshold as a PS1 accuracy claim.
     */
    for (unsigned seam=0;seam<3u;seam++)
        assert(seam_deltas[seam] <= 1024u);
    printf("VAB seam adjacent-sample deltas (PCM16): %u %u %u\n",
           seam_deltas[0],seam_deltas[1],seam_deltas[2]);
    puts("two synthetic VAB banks: safe SEQ SPU switch, continuous PCM clock PASS");
    return 0;
}
