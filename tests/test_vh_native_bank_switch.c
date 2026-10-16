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
    for (unsigned scene=0;scene<2u;scene++) {
        /* Old bank sample pointers are no longer live after the reset. */
        if(scene) vh_native_seq_stop(&seq);
        vh_native_spu_reset(&spu);
        assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                                  vh_native_vab_resolve,&bank[scene],0)==0);
        for (unsigned block=0;block<16u;block++) {
            assert(vh_native_seq_advance_block(&seq)>=0);
            vh_native_spu_render(&spu,source,512u);
            size_t n=vh_audio_resample_process(
                &resampler,source,512u,out,640u);
            assert(n>=555u && n<=559u);
            output_frames+=n;
            for(size_t i=0;i<n*2u;i++)
                checksum[scene]=checksum[scene]*UINT64_C(1099511628211)
                                +(uint16_t)out[i]+1u;
        }
        assert(seq.note_ons>0u);
        assert(bank[scene].selected_program==7u);
        assert(bank[scene].selected_vag==1u);
    }
    /* Bank A and B must each trigger notes; no lost sequencer state. */
    assert(output_frames>17000u);
    assert(resampler.input_frames==32u*512u);
    const uint64_t expected=((uint64_t)32u*512u-1u)*160u/147u+1u;
    assert(output_frames+2u>=expected && output_frames<=expected+1u);
    assert(resampler.next_output_tick==output_frames*44100u);
    assert(checksum[0]!=checksum[1]);
    puts("two synthetic VAB banks: safe SEQ SPU switch, continuous PCM clock PASS");
    return 0;
}
