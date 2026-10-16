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
    assert(bank.selected_program==1 && bank.selected_vag==3);
    assert(out.reverb_send == 1);
    assert(vh_native_vab_resolve(&bank,0,75,127,127,64,&out)==0);
    assert(bank.selected_program==1 && bank.selected_vag==3);
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
        {0, 71, 1, 0, 3},   /* nearest low=80, not nearest upper end */
        {7, 79, 1, 0, 3},   /* same requested program, outside its range */
        {7, 80, 7, 0, 3},   /* inclusive lower bound */
        {7,100, 7, 0, 3},   /* inclusive upper bound */
        {7,101, 1, 0, 3},   /* nearest global lower bound */
        {10,40,10, 0, 4},   /* requested program beats global p0 match */
        {10,50,10, 0, 4},
        {10,51, 0, 0, 1},   /* first global range after local miss */
        {99,40, 0, 0, 1},   /* sparse absent program */
        {99,70, 0, 1, 2},
        {99,75, 1, 0, 3},
        {99,127,1, 0, 3},
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
    /* These in-memory aliases were copied at load time: update their
     * synthetic ranges when changing the owning packed block. */
    for(unsigned p=1;p<7;++p) {
        bank.tones[p][0].low=50; bank.tones[p][0].high=55;
    }
    for(unsigned p=8;p<10;++p) {
        bank.tones[p][0].low=80; bank.tones[p][0].high=90;
    }
    VhSeqTone out={0};
    assert(vh_native_vab_resolve(&bank,99,40,127,127,64,&out)==0);
    assert(bank.selected_program==1 && bank.selected_vag==3);

    /* Equal distances to key_min keep first packed-table order. */
    bank.tones[0][0].low=10; bank.tones[0][0].high=15;
    bank.tones[0][1].low=30; bank.tones[0][1].high=35;
    bank.tones[7][0].low=50; bank.tones[7][0].high=55;
    bank.tones[10][0].low=70; bank.tones[10][0].high=75;
    for(unsigned p=8;p<10;++p) {
        bank.tones[p][0].low=70; bank.tones[p][0].high=75;
    }
    assert(vh_native_vab_resolve(&bank,99,20,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_tone==0);
    assert(vh_native_vab_resolve(&bank,99,40,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_tone==1);
    assert(vh_native_vab_resolve(&bank,99,60,127,127,64,&out)==0);
    assert(bank.selected_program==1 && bank.selected_tone==0);

    const unsigned p=bank.selected_program, t=bank.selected_tone;
    const unsigned vag=bank.selected_vag;
    assert(vh_native_vab_resolve(&bank,128,60,127,127,64,&out)==-1);
    assert(vh_native_vab_resolve(&bank,99,128,127,127,64,&out)==-1);
    assert(bank.selected_program==p && bank.selected_tone==t &&
           bank.selected_vag==vag);
}

/* The reference loader maps empty programs to the following packed
 * block and keeps nonzero inactive slots in its 16-tone selection table.
 */
/* PC-port tone aliases own their ProgAtr gain/pan even when their
 * sample and tone metadata are borrowed from the next packed block.
 * Check exact squared gains and observable dry PCM channel routing.
 */
static void test_shadow_program_gain_pan_and_pcm(void) {
    fixture();
    vh[32u+1u*16u+1u]=95;   /* empty program #1: volume 95 */
    vh[32u+1u*16u+4u]=0;    /* alias #1: hard left */
    vh[32u+7u*16u+1u]=127; /* populated source: full volume */
    vh[32u+7u*16u+4u]=127; /* source: hard right */
    vh[32u+8u*16u+1u]=63;  /* alias #8 has independent volume */
    vh[32u+8u*16u+4u]=64;  /* alias #8: centered */
    vh[32u+10u*16u+4u]=127;/* source #10: hard right */
    memset(&bank,0,sizeof bank);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==0);
    assert(bank.program_tones[1]==0 && bank.program_tones[8]==0);
    assert(bank.program_volume[1]==95 && bank.program_pan[1]==0);
    assert(bank.program_volume[7]==127 && bank.program_pan[7]==127);
    assert(bank.program_volume[8]==63 && bank.program_pan[8]==64);

    VhSeqTone alias={0}, source={0};
    assert(vh_native_vab_resolve(&bank,1,90,100,90,64,&alias)==0);
    assert(bank.selected_program==1 && bank.selected_vag==3);
    /* (100*90/127)=70, (70*95/127)=52, (52*117/127)=47 */
    const float alias_left=47.f/127.f;
    assert(fabsf(alias.gain_left-alias_left*alias_left*1.012f)<0.000001f);
    assert(alias.gain_right==0.f);
    assert(vh_native_vab_resolve(&bank,7,90,100,90,64,&source)==0);
    assert(bank.selected_program==7 && bank.selected_vag==3);
    assert(alias.pcm==source.pcm && alias.frames==source.frames);
    /* (70*127/127)=70, (70*117/127)=64 */
    const float source_right=64.f/127.f;
    assert(source.gain_left==0.f);
    assert(fabsf(source.gain_right-source_right*source_right*1.012f)<0.000001f);
    assert(source.gain_right>alias.gain_left);

    VhSeqTone center={0}, hard_right={0};
    assert(vh_native_vab_resolve(&bank,8,45,100,90,64,&center)==0);
    assert(bank.selected_program==8 && bank.selected_vag==4);
    /* 70*63/127=34; 34*117/127=31, with centered pans */
    const float center_gain=31.f/127.f;
    assert(fabsf(center.gain_left-center_gain*center_gain*1.012f)<0.000001f);
    assert(fabsf(center.gain_right-center.gain_left)<0.000001f);
    assert(vh_native_vab_resolve(&bank,10,45,100,90,64,&hard_right)==0);
    assert(bank.selected_program==10 && bank.selected_vag==4);
    assert(center.pcm==hard_right.pcm);
    assert(hard_right.gain_left==0.f && hard_right.gain_right>0.f);

    /* Empty programs with default zero mvol still choose a VAG but
     * correctly produce silence. Do not inherit source-program volume. */
    VhSeqTone muted={0};
    assert(vh_native_vab_resolve(&bank,2,90,100,90,64,&muted)==0);
    assert(bank.selected_program==2 && bank.selected_vag==3);
    assert(muted.gain_left==0.f && muted.gain_right==0.f);

    /* End-to-end: the SPU should route identical VAG3 PCM to opposite
     * stereo channels depending solely on the selected program's pan. */
    for (unsigned k=0; k<2u; ++k) {
        const VhSeqTone *tone_to_play=k ? &source : &alias;
        vh_native_spu_reset(&spu);
        assert(vh_native_spu_note_on(
            &spu,0,tone_to_play->pcm,tone_to_play->frames,
            tone_to_play->loop_start,tone_to_play->loop_end,
            tone_to_play->pitch_step,tone_to_play->adsr1,
            tone_to_play->adsr2,tone_to_play->gain_left,
            tone_to_play->gain_right)==0);
        vh_native_spu_render(&spu,output,16);
        unsigned left=0,right=0;
        for(unsigned i=0;i<16u;++i) {
            if(output[i*2u]) ++left;
            if(output[i*2u+1u]) ++right;
        }
        if(!k) assert(left>0 && right==0);
        else assert(left==0 && right>0);
    }
}

static void test_shadow_tones_and_aliases(void) {
    fixture();
    const size_t shadow=2080u+2u*32u;
    vh[shadow+2]=127;
    vh[shadow+3]=64;
    vh[shadow+4]=117;
    vh[shadow+6]=115;
    vh[shadow+7]=120;
    w16(vh,shadow+20,0);
    w16(vh,shadow+22,2);
    memset(&bank,0,sizeof bank);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==0);
    assert(bank.program_tones[0]==2);
    assert(bank.tones[0][2].present && bank.tones[0][2].vag==2);
    assert(bank.program_tones[1]==0 && bank.tones[1][0].present);
    assert(bank.tones[1][0].vag==3);
    assert(bank.program_tones[8]==0 && bank.tones[8][0].vag==4);
    VhSeqTone out={0};
    assert(vh_native_vab_resolve(&bank,0,117,127,127,64,&out)==0);
    assert(bank.selected_program==0 && bank.selected_tone==2 &&
           bank.selected_vag==2 && out.pcm==bank.samples[2].pcm);
    assert(vh_native_vab_resolve(&bank,1,90,127,127,64,&out)==0);
    assert(bank.selected_program==1 && bank.selected_tone==0 &&
           bank.selected_vag==3 && out.pcm==bank.samples[3].pcm);
    assert(vh_native_vab_resolve(&bank,8,45,127,127,64,&out)==0);
    assert(bank.selected_program==8 && bank.selected_tone==0 &&
           bank.selected_vag==4 && out.pcm==bank.samples[4].pcm);

    /* A malformed hidden record must not bypass VAG validation or
     * replace the published bank. */
    blank=bank;
    w16(vh,shadow+22,5); /* bank contains only VAGs 1..4 */
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    assert(!memcmp(&bank,&blank,sizeof bank));
    w16(vh,shadow+22,2);
    vh[shadow+6]=121;
    vh[shadow+7]=120;
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==-1);
    assert(!memcmp(&bank,&blank,sizeof bank));
}

/* Full SEQ -> sparse VAB -> voice gains -> rendered SPU -> PCM FIFO.
 * Notes are deliberately spaced so the previous one-shot VAG has ended
 * before the next instrument starts, isolating stereo routing.
 */
static void test_seq_shadow_program_changes_stereo_pcm(void) {
    fixture();
    /* The two programs share VAG3 and its reverb flag, but NOT ProgAtr. */
    vh[32u+1u*16u+1u]=95;
    vh[32u+1u*16u+4u]=0;
    vh[32u+7u*16u+1u]=127;
    vh[32u+7u*16u+4u]=127;
    vh[32u+8u*16u+1u]=63;
    vh[32u+8u*16u+4u]=64;
    memset(&bank,0,sizeof bank);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==0);
    vh_native_spu_reset(&spu);
    vh_audio_stream_reset(&fifo);

    static const uint8_t song[] = {
        'p','Q','E','S',0,0,0,0, 1,0xe0,7,0xa1,0x20,0,0,
        0,0xc0,1,             /* ch0 -> empty program1 (VAG3), left */
        0,0xb0,7,90,          /* volume channel0 */
        0,0xb0,10,64,         /* centered channel pan */
        0,0x90,90,100,        /* alias VAG3 note-on */
        0x78,0x80,90,0,       /* release after 120 ticks */
        0x78,0xb0,10,127,     /* new hard-right channel pan */
        0,0xc0,7,             /* p7 shares the VAG3 but is hard-right */
        0,0x90,90,100,
        0x78,0x80,90,0,
        0x78,0xb0,10,64,      /* restore center pan */
        0,0xc0,8,             /* empty program8 -> VAG4 */
        0,0x90,45,100,
        0x78,0x80,45,0,
        0x78,0xff,0x2f
    };
    VhSeqAudit audit={0};
    assert(vh_native_seq_audit(song,sizeof song,vh_native_vab_resolve,
                               &bank,&audit)==0);
    assert(audit.note_events==3 && audit.resolved_notes==3);
    assert(audit.missing_notes==0 && audit.program_changes==3);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                              vh_native_vab_resolve,&bank,1)==0);
    const unsigned expected_programs[] = {1,7,8};
    const unsigned expected_vags[] = {3,3,4};
    const unsigned expected_notes[] = {90,90,45};
    unsigned observed=0;
    unsigned pumps=0;
    while(seq.playing && pumps++ < 100u) {
        const uint64_t before=seq.note_ons;
        assert(vh_native_seq_pump(&seq,&fifo)==512);
        assert(vh_audio_stream_read(&fifo,output,512)==512);
        if(seq.note_ons==before) continue;
        assert(seq.note_ons==before+1u);
        assert(observed<3u);
        const unsigned expected=expected_programs[observed];
        const unsigned vag=expected_vags[observed];
        assert(bank.selected_program==expected);
        assert(bank.selected_vag==vag);
        assert(seq.programs[0]==expected);
        const int slot=seq.note_slot[0][expected_notes[observed]];
        assert(slot>=0 && slot<(int)VH_NATIVE_MUSIC_VOICES);
        assert(spu.voice[slot].pcm==bank.samples[vag].pcm);
        if(observed<2u) assert(spu.voice[slot].reverb_send==1);
        else assert(spu.voice[slot].reverb_send==0);
        /* Current voice gains remain observable even if its short
         * sample has already ended within this 512-frame block. */
        const float left=spu.voice[slot].gain_left;
        const float right=spu.voice[slot].gain_right;
        if(observed==0u) assert(left>0.f && right==0.f);
        else if(observed==1u) assert(left==0.f && right>0.f);
        else assert(left>0.f && fabsf(left-right)<0.000001f);

        unsigned audible_left=0,audible_right=0;
        for(unsigned i=0;i<512u;++i) {
            if(output[2u*i]) ++audible_left;
            if(output[2u*i+1u]) ++audible_right;
        }
        if(observed==0u)
            assert(audible_left>0 && audible_right==0);
        else if(observed==1u)
            assert(audible_left==0 && audible_right>0);
        else
            assert(audible_left>0 && audible_right>0);
        ++observed;
    }
    assert(observed==3u && !seq.playing);
    assert(seq.cycles_completed==1u && seq.note_ons==3u);
    assert(seq.note_offs==3u && seq.last_error==0);
    assert(seq.pans[0]==64u && seq.volumes[0]==90u);
    assert(vh_audio_stream_queued(&fifo)==0u);
}

/* Two simultaneous MIDI channels may request the same VAG/note with
 * different ProgAtr and CC levels. Their stereo gains and note-off
 * ownership must remain independent throughout SEQ -> SPU playback.
 */
static void test_seq_concurrent_shadow_and_source_channels(void) {
    fixture();
    vh[32u+1u*16u+1u]=95;
    vh[32u+1u*16u+4u]=0;
    vh[32u+7u*16u+1u]=127;
    vh[32u+7u*16u+4u]=127;
    memset(&bank,0,sizeof bank);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==0);
    vh_native_spu_reset(&spu);
    vh_audio_stream_reset(&fifo);
    static const uint8_t song[] = {
        'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
        0,0xc0,1,          /* ch0 aliases VAG3 with hard-left pan */
        0,0xc1,7,          /* ch1 owns VAG3 with hard-right pan */
        0,0xb0,7,90,       /* ch0 volume */
        0,0xb1,7,40,       /* ch1 volume, independent */
        0,0x90,90,100,
        0,0x91,90,100,
        0x78,0x80,90,0,    /* ch0 note-off must not release ch1 */
        0x78,0x81,90,0,
        0x78,0xff,0x2f
    };
    VhSeqAudit report={0};
    assert(vh_native_seq_audit(song,sizeof song,vh_native_vab_resolve,
                               &bank,&report)==0);
    assert(report.note_events==2 && report.resolved_notes==2 &&
           report.missing_notes==0 && report.program_changes==2);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                              vh_native_vab_resolve,&bank,1)==0);
    assert(vh_native_seq_pump(&seq,&fifo)==512);
    assert(vh_audio_stream_read(&fifo,output,512)==512);
    assert(seq.note_ons==2 && seq.note_offs==0);
    const int left_slot=seq.note_slot[0][90];
    const int right_slot=seq.note_slot[1][90];
    assert(left_slot>=0 && right_slot>=0 && left_slot!=right_slot);
    assert(seq.owner_ch[left_slot]==0 && seq.owner_ch[right_slot]==1);
    assert(spu.voice[left_slot].pcm==bank.samples[3].pcm &&
           spu.voice[right_slot].pcm==bank.samples[3].pcm);
    assert(spu.voice[left_slot].gain_left>0.f &&
           spu.voice[left_slot].gain_right==0.f);
    assert(spu.voice[right_slot].gain_left==0.f &&
           spu.voice[right_slot].gain_right>0.f);
    assert(spu.voice[left_slot].gain_left >
           spu.voice[right_slot].gain_right);
    unsigned left=0,right=0;
    for(unsigned i=0;i<512u;++i) {
        if(output[2u*i]) ++left;
        if(output[2u*i+1u]) ++right;
    }
    assert(left>0 && right>0);

    unsigned blocks=0;
    while(seq.note_offs==0 && blocks++<40u) {
        assert(vh_native_seq_pump(&seq,&fifo)==512);
        assert(vh_audio_stream_read(&fifo,output,512)==512);
    }
    assert(seq.note_offs==1);
    assert(seq.note_slot[0][90]==-1);
    assert(seq.note_slot[1][90]==right_slot);
    assert(seq.owner_ch[right_slot]==1 && seq.owner_note[right_slot]==90);

    while(seq.playing && blocks++<100u) {
        assert(vh_native_seq_pump(&seq,&fifo)==512);
        assert(vh_audio_stream_read(&fifo,output,512)==512);
    }
    assert(seq.note_offs==2 && seq.note_ons==2 && !seq.playing);
    assert(seq.note_slot[1][90]==-1);
    assert(seq.cycles_completed==1u && seq.last_error==0);
}

/* SEQ timing seam: tempo at tick15 takes effect for the NEXT 512-frame
 * budget, while CC7, CC10 and program changes are used immediately for
 * note-ons at the same tick. PCM shows left -> right -> centered sound.
 */
static void test_seq_tempo_and_controls_across_pcm_blocks(void) {
    fixture();
    vh[32u+1u*16u+1u]=95;   /* ghost program #1 */
    vh[32u+1u*16u+4u]=0;    /* left */
    vh[32u+7u*16u+1u]=127;
    vh[32u+7u*16u+4u]=127;  /* right */
    vh[32u+8u*16u+1u]=63;   /* ghost program #8 */
    vh[32u+8u*16u+4u]=64;   /* center */
    memset(&bank,0,sizeof bank);
    assert(vh_native_vab_load(&bank,vh,sizeof vh,vb,96,arena,224)==0);
    vh_native_spu_reset(&spu);
    vh_audio_stream_reset(&fifo);

    static const uint8_t song[] = {
        'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
        0,0xc0,1,          /* channel 0: ghost program 1 */
        0,0xb0,7,90,
        0,0xb0,10,64,
        0,0x90,90,100,      /* tick 0: left VAG3 */
        15,0xff,0x51,3,0xd0,0x90, /* tick15: 250000 us/quarter */
        0,0xb0,7,40,
        0,0xb0,10,127,
        0,0xc0,7,
        0,0x90,92,100,      /* tick15: right VAG3 */
        30,0xb0,7,100,
        0,0xb0,10,64,
        0,0xc0,8,
        0,0x90,45,100,      /* tick45: center VAG4 */
        120,0x80,90,0,
        0,0x80,92,0,
        0,0x80,45,0,
        120,0xff,0x2f
    };
    VhSeqAudit audit={0};
    assert(vh_native_seq_audit(song,sizeof song,vh_native_vab_resolve,
                               &bank,&audit)==0);
    assert(audit.note_events==3u && audit.resolved_notes==3u);
    assert(audit.missing_notes==0u && audit.program_changes==3u);
    assert(audit.tempo_changes==1u);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                              vh_native_vab_resolve,&bank,1)==0);

    const unsigned note_ons[]={1u,2u,2u,3u};
    const unsigned program[]={1u,7u,7u,8u};
    const unsigned volumes[]={90u,40u,40u,100u};
    const unsigned pans[]={64u,127u,127u,64u};
    const unsigned tempo[]={500000u,250000u,250000u,250000u};
    const unsigned vag[]={3u,3u,3u,4u};
    for (unsigned block=0;block<4u;++block) {
        assert(vh_native_seq_pump(&seq,&fifo)==512);
        assert(vh_audio_stream_read(&fifo,output,512)==512);
        assert(seq.blocks_advanced==block+1u);
        assert(seq.note_ons==note_ons[block]);
        assert(seq.note_offs==0u && seq.playing);
        assert(seq.programs[0]==program[block]);
        assert(seq.volumes[0]==volumes[block]);
        assert(seq.pans[0]==pans[block]);
        assert(seq.tempo==tempo[block]);
        assert(bank.selected_program==program[block]);
        assert(bank.selected_vag==vag[block]);
        unsigned audible_l=0,audible_r=0;
        for (unsigned i=0;i<512u;++i) {
            if (output[2u*i]) ++audible_l;
            if (output[2u*i+1u]) ++audible_r;
        }
        if (block==0u) assert(audible_l>0u && audible_r==0u);
        if (block==1u) assert(audible_l==0u && audible_r>0u);
        if (block==2u) assert(audible_l==0u && audible_r==0u);
        if (block==3u) assert(audible_l>0u && audible_r>0u);
    }
    /* Tempo changed at tick15 *inside* block2. The new faster
     * tick rate advances only the later block budgets. */
    assert(seq.tick_budget>20.0 && seq.tick_budget<22.0);
    unsigned blocks=4u;
    while(seq.playing && blocks++<80u) {
        assert(vh_native_seq_pump(&seq,&fifo)==512);
        assert(vh_audio_stream_read(&fifo,output,512)==512);
    }
    assert(!seq.playing && seq.cycles_completed==1u);
    /* One-shot VAG3 voices end inside earlier 512-frame blocks and
     * their slot is reused. Stale MIDI note-offs must not release
     * the newer VAG4 owner or count as active-voice key-offs. */
    assert(seq.note_ons==3u && seq.note_offs==1u);
    assert(seq.note_slot[0][90]==-1 &&
           seq.note_slot[0][92]==-1 &&
           seq.note_slot[0][45]==-1);
    assert(seq.last_error==0 && vh_audio_stream_queued(&fifo)==0u);
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
    test_shadow_tones_and_aliases();
    test_shadow_program_gain_pan_and_pcm();
    test_strict_invalid_banks_and_no_publish();
    test_actual_native_seq_to_vab_to_spu_pcm();
    test_seq_shadow_program_changes_stereo_pcm();
    test_seq_concurrent_shadow_and_source_channels();
    test_seq_tempo_and_controls_across_pcm_blocks();
    puts("native sparse VH/VB -> SEQ -> SPU stereo PCM: PASS");
    return 0;
}
