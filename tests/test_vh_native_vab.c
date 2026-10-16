/* Native sparse VH/VB, note selection, PsyQ gain and SEQ integration.
 * All buffers are generated here. No proprietary game assets included.
 */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_native_vab.h"
#include "vh_spu_adpcm.h"

#define VH_BYTES (32u + 128u*16u + 3u*512u + 512u)
static uint8_t vh[VH_BYTES], vb[112];
static int16_t arena[8u*28u];
static VhNativeVab bank, blank;
static VhNativeSpu spu;
static VhNativeSeq seq;
static VhAudioStream fifo;
static int16_t output[1024];

static void w16(uint8_t *buf, size_t at, unsigned value) {
    buf[at] = (uint8_t)value;
    buf[at+1] = (uint8_t)(value >> 8);
}

static void tone(unsigned block, unsigned idx, unsigned prog,
                 unsigned low, unsigned high, unsigned center,
                 unsigned shift, unsigned vag) {
    const size_t off = 2080u + block*512u + idx*32u;
    vh[off + 2] = 117; vh[off + 3] = 64;
    vh[off + 4] = (uint8_t)center; vh[off + 5] = (uint8_t)shift;
    vh[off + 6] = (uint8_t)low; vh[off + 7] = (uint8_t)high;
    w16(vh, off+16, 15); w16(vh, off+18, 0);
    w16(vh, off+20, prog); w16(vh, off+22, vag);
}

static void fixture(void) {
    memset(vh, 0, sizeof vh);
    memset(vb, 0, sizeof vb);
    memcpy(vh, "pBAV", 4);
    w16(vh, 18, 3); w16(vh, 20, 4); w16(vh, 22, 4);
    vh[24] = 127;
    const unsigned ps[] = {0, 7, 10};
    const unsigned n[] = {2, 1, 1};
    for (unsigned i=0;i<3;i++) {
        size_t at=32u+ps[i]*16u;
        vh[at] = (uint8_t)n[i];
        vh[at+1] = 127; vh[at+4] = 64;
    }
    tone(0,0,0,40,60,60,0,1);
    tone(0,1,0,40,70,70,128,2);
    tone(1,0,7,80,100,254,128,3);
    vh[2080u + 512u + 1u] = 4; /* music program 7: VagAtr.mode EON */
    tone(2,0,10,40,50,55,0,4);
    const size_t sizes = 2080u + 3u*512u;
    w16(vh, sizes + 0, 2); /* slot zero participates in VB offset */
    w16(vh, sizes + 2, 2);
    w16(vh, sizes + 4, 4); /* two-block looping VAG */
    w16(vh, sizes + 6, 2);
    w16(vh, sizes + 8, 2);
    /* VB: zero-entry padding 16, VAG1 16, VAG2 32, VAG3/4 16. */
    const unsigned starts[] = {16,32,64,80};
    for (unsigned vag=0;vag<4;vag++) {
        unsigned off=starts[vag];
        vb[off] = 2;
        vb[off+1] = vag==1 ? 4 : 1;
        for (unsigned i=2;i<16;i++) vb[off+i]=0x22;
    }
    vb[48]=2; vb[49]=3;
    for(unsigned i=50;i<64;i++) vb[i]=0xee;
}

static void test_metadata_selection_and_audio(void) {
    fixture();
    memset(&bank,0,sizeof bank);
    memset(arena,0,sizeof arena);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,
                              sizeof arena/sizeof arena[0]) == 0);
    assert(bank.active && bank.vag_count==4);
    assert(bank.required_pcm_frames == (1u+2u+1u+1u)*28u);
    assert(bank.program_tones[0]==2 && bank.program_tones[7]==1 &&
           bank.program_tones[10]==1);
    assert(bank.samples[1].vb_offset==16 && bank.samples[1].frames==28);
    assert(bank.samples[2].vb_offset==32 && bank.samples[2].frames==56);
    assert(bank.samples[2].loop_start==0 && bank.samples[2].loop_end==56);
    assert(bank.samples[3].vb_offset==64);
    assert(bank.samples[4].vb_offset==80);
    assert(bank.samples[1].pcm[0]==2048);
    assert(bank.samples[2].pcm[28]==-2048);
    VhSeqTone out;
    assert(vh_native_vab_resolve(&bank,0,45,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_tone==0 &&
           bank.selected_vag==1);
    assert(out.pcm==bank.samples[1].pcm && out.pitch_step>0);
    assert(vh_native_vab_resolve(&bank,0,65,127,127,64,&out)==0);
    assert(bank.selected_vag==2 && out.loop_end==56);
    assert(vh_native_vab_resolve(&bank,7,45,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_vag==1);
    assert(vh_native_vab_resolve(&bank,99,90,127,127,64,&out)==0);
    assert(bank.selected_program==7 && bank.selected_vag==3);
    assert(out.reverb_send == 1);
    assert(vh_native_vab_resolve(&bank,0,75,127,127,64,&out)==0);
    assert(bank.selected_program==7 && bank.selected_vag==3);
    assert(vh_native_vab_resolve(&bank,99,15,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_vag==1);
    assert(vh_native_vab_resolve(&bank,0,60,127,127,64,&out)==0);
    assert(out.pitch_step==4096);
    const float gain = 117.f / 127.f;
    assert(fabsf(out.gain_left-gain*gain*1.012f)<0.00001f);
    assert(fabsf(out.gain_right-out.gain_left)<0.00001f);
    assert(vh_native_vab_resolve(&bank,0,60,127,127,0,&out)==0);
    assert(out.gain_right==0.f && out.gain_left>0.f);
    assert(vh_native_vab_resolve(&bank,0,60,127,127,127,&out)==0);
    assert(out.gain_left==0.f && out.gain_right>0.f);
    assert(vh_native_vab_resolve(&bank,0,60,0,127,64,&out)==0);
    assert(out.gain_left==0.f && out.gain_right==0.f);
    assert(vh_native_vab_resolve(&bank,128,60,100,100,64,&out)==-1);
}

/* Exact inclusivity, sparse-program priority, and PC-port-compatible
 * nearest-low-bound selection. These cases are independent of SEQ timing.
 */
static void test_tone_range_boundaries_and_nearest_ties(void) {
    fixture();
    memset(&bank,0,sizeof bank);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==0);
    struct Selection {
        unsigned requested, note, chosen_program, chosen_tone, chosen_vag;
    };
    static const struct Selection cases[] = {
        {0,  0, 0, 0, 1},   /* outside every range: nearest low=40 */
        {0, 40, 0, 0, 1},   /* shared lower bound: first local tone */
        {0, 60, 0, 0, 1},   /* inclusive upper bound for first tone */
        {0, 61, 0, 1, 2},   /* second overlapping local tone */
        {0, 70, 0, 1, 2},   /* inclusive upper bound for second tone */
        {0, 71, 7, 0, 3},   /* nearest low=80, not nearest upper end */
        {7, 79, 7, 0, 3},   /* same requested program, outside its range */
        {7, 80, 7, 0, 3},   /* inclusive lower bound */
        {7,100, 7, 0, 3},   /* inclusive upper bound */
        {7,101, 7, 0, 3},   /* nearest global lower bound */
        {10,40,10, 0, 4},   /* requested program beats global p0 match */
        {10,50,10, 0, 4},
        {10,51, 0, 0, 1},   /* first global range after local miss */
        {99,40, 0, 0, 1},   /* sparse absent program */
        {99,70, 0, 1, 2},
        {99,75, 7, 0, 3},
        {99,127,7, 0, 3},
    };
    for(size_t i=0;i<sizeof cases/sizeof cases[0];++i) {
        const struct Selection *c=&cases[i];
        VhSeqTone out={0};
        assert(vh_native_vab_resolve(&bank,c->requested,c->note,
                                     127,127,64,&out)==0);
        assert(bank.selected_program==c->chosen_program);
        assert(bank.selected_tone==c->chosen_tone);
        assert(bank.selected_vag==c->chosen_vag);
        assert(out.pcm==bank.samples[c->chosen_vag].pcm);
        assert(out.frames==bank.samples[c->chosen_vag].frames);
    }

    /* No range contains 40. Lower boundaries (10 vs 50), not
     * distances to the upper endpoints (35 vs 50), choose VAG3. */
    bank.tones[0][0].low=10; bank.tones[0][0].high=35;
    bank.tones[0][1].low=0;  bank.tones[0][1].high=5;
    bank.tones[7][0].low=50; bank.tones[7][0].high=55;
    bank.tones[10][0].low=80; bank.tones[10][0].high=90;
    VhSeqTone out={0};
    assert(vh_native_vab_resolve(&bank,99,40,127,127,64,&out)==0);
    assert(bank.selected_program==7 && bank.selected_vag==3);

    /* Equal distances to key_min keep first packed-table order. */
    bank.tones[0][0].low=10; bank.tones[0][0].high=15;
    bank.tones[0][1].low=30; bank.tones[0][1].high=35;
    bank.tones[7][0].low=50; bank.tones[7][0].high=55;
    bank.tones[10][0].low=70; bank.tones[10][0].high=75;
    assert(vh_native_vab_resolve(&bank,99,20,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_tone==0);
    assert(vh_native_vab_resolve(&bank,99,40,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_tone==1);
    assert(vh_native_vab_resolve(&bank,99,60,127,127,64,&out)==0);
    assert(bank.selected_program==7 && bank.selected_tone==0);

    const unsigned p=bank.selected_program, t=bank.selected_tone;
    const unsigned vag=bank.selected_vag;
    assert(vh_native_vab_resolve(&bank,128,60,127,127,64,&out)==-1);
    assert(vh_native_vab_resolve(&bank,99,128,127,127,64,&out)==-1);
    assert(bank.selected_program==p && bank.selected_tone==t &&
           bank.selected_vag==vag);
}

static void test_strict_invalid_banks_and_no_publish(void) {
    fixture();
    memset(&bank,0x5a,sizeof bank);
    blank=bank;
    assert(vh_native_vab_load(&bank,vh,200,vb,96,arena,224)==-1);
    assert(!memcmp(&blank,&bank,sizeof bank));
    vh[0]='X';
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    vh[0]='p';
    vh[12]=1; /* declared VAB size below 32-byte header */
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    vh[12]=0;
    const size_t ton=2080;
    vh[ton+6]=110; vh[ton+7]=70;
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    vh[ton+6]=40; vh[ton+7]=60;
    w16(vh,ton+20,12);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    w16(vh,ton+20,0);
    w16(vh,ton+22,5);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    w16(vh,ton+22,1);
    const size_t size0=2080+3*512;
    w16(vh,size0+2,1); /* 8 bytes not a complete ADPCM block */
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    w16(vh,size0+2,2);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,95,arena,224)==-1);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,139)==-1);
    vb[16]=0x50;
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    vb[16]=0x02;
    assert(!memcmp(&blank,&bank,sizeof bank));
}

static void test_actual_native_seq_to_vab_to_spu_pcm(void) {
    fixture();
    memset(&bank,0,sizeof bank);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==0);
    vh_native_spu_reset(&spu);
    vh_audio_stream_reset(&fifo);
    assert(vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN)==0);
    const uint8_t seqdata[]={
        'p','Q','E','S',0,0,0,0, 0x01,0xe0,0x07,0xa1,0x20,0,0,
        0,0xc0,7, 0,0xb0,10,0,
        0,0x90,90,110, 0x81,0x70,0x80,90,0,
        0,0xff,0x2f,
    };
    assert(vh_native_seq_init(&seq,seqdata,sizeof seqdata,
                              &spu,vh_native_vab_resolve,&bank,1)==0);
    assert(vh_native_seq_pump(&seq,&fifo)==512);
    assert(bank.selected_program==7 && bank.selected_vag==3);
    assert(seq.note_ons==1 && seq.playing);
    assert(spu.voice[0].reverb_send);
    assert(vh_audio_stream_read(&fifo,output,512)==512);
    unsigned audible=0;
    for(unsigned i=0;i<512;i++) {
        if (output[2u*i]!=0) ++audible;
        assert(output[2u*i+1u]==0);
    }
    assert(audible>0); /* note 90, VAG3, hard-left ch pan */
    /* Source files are copied to memory only; never modified. */
    assert(vh[0]=='p' && vb[64]==2);
}

int main(void) {
    test_metadata_selection_and_audio();
    test_tone_range_boundaries_and_nearest_ties();
    test_strict_invalid_banks_and_no_publish();
    test_actual_native_seq_to_vab_to_spu_pcm();
    puts("native sparse VH/VB -> SEQ -> SPU stereo PCM: PASS");
    return 0;
}
