/* Synthetic end-to-end PS1 pQES -> 20 voices -> PCM FIFO tests. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_native_seq.h"

static VhAudioStream ring;
static VhNativeSpu spu;
static VhNativeSeq seq;
static int16_t sample[64];
static int16_t pcm[VH_AUDIO_BLOCK_FRAMES * 2u];

typedef struct {
    unsigned calls, program, note, velocity, volume, pan;
} ResolverLog;
static ResolverLog log_state;

static int resolve(void *ctx, unsigned program, unsigned note,
                   unsigned velocity, unsigned volume, unsigned pan,
                   VhSeqTone *out) {
    ResolverLog *log = ctx;
    ++log->calls;
    log->program=program;log->note=note;log->velocity=velocity;
    log->volume=volume;log->pan=pan;
    memset(out, 0, sizeof(*out));
    out->pcm = sample;
    out->frames = 64;
    out->loop_start = 0;out->loop_end = 64;
    out->pitch_step = 4096;
    out->adsr1 = 15;out->adsr2 = 0;
    out->gain_left = (float)velocity / 127.f;
    out->gain_right = (float)volume / 127.f;
    return 0;
}

#define HEADER 'p','Q','E','S',0,0,0,0,0x01,0xe0,0x07,0xa1,0x20,0,0
static const uint8_t controls_song[] = {
    HEADER,
    0,0xc0,7, 0,0xb0,7,80, 0,0xb0,10,0,
    0,0x90,60,100, 0x81,0x70,0x80,60,0, 0,0xff,0x2f
};
static const uint8_t running_song[] = {
    HEADER,
    0,0x90,60,100, 0,61,110, 10,0x80,60,0,
    0,0xff,0x51,0x03,0xd0,0x90, 10,0xff,0x2f
};
static const uint8_t loop_song[] = {
    HEADER,
    0,0x90,60,100, 10,0xff,0x2f
};
static const uint8_t steal_song[] = {
    HEADER,
    0,0x90,40,100,
    0,41,100,0,42,100,0,43,100,0,44,100,
    0,45,100,0,46,100,0,47,100,0,48,100,0,49,100,
    0,50,100,0,51,100,0,52,100,0,53,100,0,54,100,
    0,55,100,0,56,100,0,57,100,0,58,100,0,59,100,
    10,60,110, 0,0x80,40,0, 0,0x90,61,100,
    0x81,0x70,0xff,0x2f
};
static const uint8_t invalid_status[] = {HEADER,0,60,100,0,0xff,0x2f};
static const uint8_t invalid_tempo[] = {HEADER,0,0xff,0x51,0x03};
static const uint8_t invalid_vlq[] = {HEADER,0x81,0x80,0x80,0x80,0,0xff,0x2f};
static const uint8_t invalid_data[] = {HEADER,0,0x90,60,0xff,0x2f};
static const uint8_t zero_loop[] = {HEADER,0,0x90,60,90,0,0xff,0x2f};

static void setup(void) {
    for (size_t i=0;i<64;i++) sample[i] = 10000;
    vh_native_spu_reset(&spu);
    vh_audio_stream_reset(&ring);
    memset(&log_state,0,sizeof(log_state));
    assert(vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN)==0);
}

static void test_validation_and_source_immutability(void) {
    setup();
    const uint8_t *bad[] = {invalid_status,invalid_tempo,
                             invalid_vlq,invalid_data};
    const size_t lens[] = {sizeof invalid_status,sizeof invalid_tempo,
                           sizeof invalid_vlq,sizeof invalid_data};
    for (unsigned i=0;i<4;i++) {
        VhNativeSeq untouched;
        memset(&untouched,0x5a,sizeof(untouched));
        VhNativeSeq before=untouched;
        assert(vh_native_seq_init(&untouched,bad[i],lens[i],
                                  &spu,resolve,&log_state,1)==-1);
        assert(memcmp(&before,&untouched,sizeof before)==0);
    }
    assert(vh_native_seq_init(&seq,zero_loop,sizeof zero_loop,
                              &spu,resolve,&log_state,0)==-1);
    assert(vh_native_seq_init(&seq,loop_song,sizeof loop_song,
                              &spu,resolve,&log_state,65)==-1);
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve,&log_state,1)==0);
    assert(seq.ppqn==480 && seq.tempo==500000);
    assert(seq.volumes[0]==127 && seq.pans[0]==64);
}

static void test_512_block_controls_and_ring_pressure(void) {
    setup();
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve,&log_state,1)==0);
    int16_t silence[VH_AUDIO_RING_FRAMES*2u]={0};
    assert(vh_audio_stream_write(&ring,silence,VH_AUDIO_RING_FRAMES)
            == VH_AUDIO_RING_FRAMES);
    assert(vh_native_seq_pump(&seq,&ring)==0);
    assert(seq.blocks_advanced==0 && spu.frames_rendered==0);
    assert(vh_audio_stream_read(&ring,pcm,512)==512);
    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(seq.blocks_advanced==1 && spu.frames_rendered==512);
    assert(log_state.calls==1);
    assert(log_state.program==7 && log_state.note==60);
    assert(log_state.velocity==100 && log_state.volume==80);
    assert(log_state.pan==0);
    assert(seq.note_ons==1 && seq.playing==1);
    /* 480 PPQN, 500000 us/quarter: 512 frames advance 11.145... ticks.
     * NoteOff at tick240 becomes due at block 22 (zero-based index 21).
     */
    for(unsigned i=0;i<20;i++) {
        assert(vh_audio_stream_read(&ring,pcm,512)==512);
        assert(vh_native_seq_pump(&seq,&ring)==512);
    }
    assert(seq.blocks_advanced==21 && seq.note_offs==0 && seq.playing);
    assert(vh_audio_stream_read(&ring,pcm,512)==512);
    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(seq.blocks_advanced==22 && seq.note_offs==1);
    assert(seq.cycles_completed==1 && !seq.playing);
    assert(log_state.calls==1);
}

static void test_running_tempo_and_repeat_seam(void) {
    setup();
    assert(vh_native_seq_init(&seq,running_song,sizeof running_song,
                              &spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==2);
    assert(seq.note_offs==1);
    assert(seq.tempo==250000); /* PS1 FF51 has no SMF length */
    assert(seq.playing);
    assert(vh_native_seq_advance_block(&seq)>=0);
    assert(seq.blocks_advanced==2); /* tempo switched after first block */
    assert(!seq.playing && seq.cycles_completed==1);
    assert(seq.note_offs==2);
    setup();
    assert(vh_native_seq_init(&seq,loop_song,sizeof loop_song,
                              &spu,resolve,&log_state,2)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.cycles_completed==1);
    assert(seq.playing && seq.note_ons==2);
    assert(seq.note_offs==1); /* retrigger on clean loop */
    assert(vh_native_seq_advance_block(&seq)>=0);
    assert(seq.cycles_completed==2 && !seq.playing);
    assert(seq.note_offs==2);
}

static void test_voice_stealing_stale_note_off(void) {
    setup();
    assert(vh_native_seq_init(&seq,steal_song,sizeof steal_song,
                              &spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==22);
    assert(seq.note_slot[0][40]==-1); /* stale NoteOff didn't stop slot 0 */
    assert(seq.note_slot[0][60]==0);
    assert(seq.note_slot[0][61]==1);
    assert(seq.owner_note[0]==60 && seq.owner_note[1]==61);
    assert(vh_native_spu_voice_active(&spu,0));
    assert(vh_native_spu_voice_active(&spu,1));
}

static void test_512_pcm_event_to_spu_fifo(void) {
    setup();
    assert(vh_native_seq_init(&seq,loop_song,sizeof loop_song,
                              &spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(vh_audio_stream_read(&ring,pcm,512)==512);
    /* EOT at tick 10 falls in first block; Release is applied BEFORE PCM.
       For this synthetic case, key-on then key-off produces silence. */
    for(unsigned i=0;i<1024;i++) assert(pcm[i]==0);
    assert(seq.cycles_completed==1 && !seq.playing);
}


static void test_scene_switch_clears_release_and_reuses_slot(void) {
    setup();
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_slot[0][60]==0);
    assert(vh_native_spu_voice_active(&spu,0));

    /* A failed switch must leave the current music and voice intact. */
    assert(vh_native_seq_switch_scene(&seq,invalid_tempo,
               sizeof invalid_tempo,&spu,resolve,&log_state,1)==-1);
    assert(seq.playing && seq.note_slot[0][60]==0);
    assert(vh_native_spu_voice_active(&spu,0));

    /* Key-off alone retains the releasing voice until the envelope ends. */
    vh_native_seq_stop(&seq);
    assert(spu.voice[0].adsr.phase==VH_ADSR_RELEASE);
    assert(vh_native_spu_voice_active(&spu,0));

    /* Switching a track flushes the old release and resets ownership. */
    assert(vh_native_seq_switch_scene(&seq,loop_song,sizeof loop_song,
                                      &spu,resolve,&log_state,1)==0);
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
        assert(!vh_native_spu_voice_active(&spu,slot));
        assert(seq.owner_ch[slot]==-1 && seq.owner_note[slot]==-1);
    }
    assert(seq.note_slot[0][60]==-1);
    assert(seq.playing && seq.blocks_advanced==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==1 && seq.note_offs==1);
    assert(!seq.playing && seq.cycles_completed==1);
    assert(log_state.calls==2);
}


static void test_repeated_scene_switch_with_twenty_live_voices(void) {
    /* Generated pQES: twenty simultaneous notes and a deferred EOT. */
    uint8_t many[15u + 20u * 4u + 5u];
    const uint8_t header[] = {HEADER};
    memcpy(many, header, sizeof header);
    size_t length = sizeof header;
    for (unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++) {
        many[length++]=0u;
        many[length++]=0x90u;
        many[length++]=(uint8_t)(40u+i);
        many[length++]=100u;
    }
    many[length++]=0x81u;many[length++]=0x70u;
    many[length++]=0xffu;many[length++]=0x2fu;
    setup();
    for (unsigned iteration=0;iteration<32u;iteration++) {
        assert(vh_native_seq_switch_scene(&seq,many,length,&spu,
                                          resolve,&log_state,1)==0);
        assert(seq.playing && seq.blocks_advanced==0);
        for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(!vh_native_spu_voice_active(&spu,slot));
            assert(seq.owner_ch[slot]==-1 && seq.owner_note[slot]==-1);
        }
        assert(vh_native_seq_advance_block(&seq)>0);
        assert(seq.note_ons==VH_NATIVE_MUSIC_VOICES);
        for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(vh_native_spu_voice_active(&spu,slot));
            assert(seq.owner_ch[slot]==0);
            assert(seq.owner_note[slot]==(int)(40u+slot));
            assert(seq.note_slot[0][40u+slot]==(int)slot);
        }
        /* All 20 voices must enter Release without freeing the slot. */
        vh_native_seq_stop(&seq);
        for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(vh_native_spu_voice_active(&spu,slot));
            assert(spu.voice[slot].adsr.phase==VH_ADSR_RELEASE);
            assert(seq.note_slot[0][40u+slot]==-1);
        }
    }
    /* The next valid scene must reclaim even the final release tails. */
    assert(vh_native_seq_switch_scene(&seq,controls_song,
            sizeof controls_song,&spu,resolve,&log_state,1)==0);
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++)
        assert(!vh_native_spu_voice_active(&spu,slot));
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_slot[0][60]==0);
    assert(vh_native_spu_voice_active(&spu,0));
}


static void test_natural_adsr_release_reuses_free_slot(void) {
    setup();
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
        assert(vh_native_spu_note_on(&spu,slot,sample,64u,0,64,4096u,
                                     0x000fu,0x0000u,1.0f,1.0f)==0);
    }
    assert(vh_native_spu_allocate_slot(&spu)==0); /* full: steal candidate */
    vh_native_spu_render(&spu,pcm,512u);
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++)
        assert(vh_native_spu_voice_active(&spu,slot));
    vh_native_spu_note_off(&spu,7u);
    assert(vh_native_spu_voice_active(&spu,7u)); /* release is not instant */
    vh_native_spu_render(&spu,pcm,512u);
    assert(!vh_native_spu_voice_active(&spu,7u));
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
        if(slot!=7u) assert(vh_native_spu_voice_active(&spu,slot));
    }
    assert(vh_native_spu_allocate_slot(&spu)==7);
    assert(vh_native_spu_note_on(&spu,7u,sample,64u,0,64,4096u,
                                 0x000fu,0x0000u,1.0f,1.0f)==0);
    assert(vh_native_spu_voice_active(&spu,7u));
    assert(spu.voice[7].adsr.phase==VH_ADSR_ATTACK);
    assert(spu.voice[7].adsr.level==0);
}

static void test_invalid_switch_preserves_twenty_voices(void) {
    uint8_t many[15u + 20u * 4u + 4u];
    const uint8_t header[] = {HEADER};
    memcpy(many,header,sizeof header);
    size_t length=sizeof header;
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
        many[length++]=0u;many[length++]=0x90u;
        many[length++]=(uint8_t)(40u+slot);many[length++]=100u;
    }
    many[length++]=0x78u;many[length++]=0xffu;
    many[length++]=0x2fu;
    setup();
    assert(vh_native_seq_init(&seq,many,length,&spu,
                              resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==VH_NATIVE_MUSIC_VOICES && seq.playing);
    for(unsigned attempt=0;attempt<16u;attempt++) {
        const VhNativeSeq before_seq=seq;
        VhNativeVoice before_voices[VH_NATIVE_MUSIC_VOICES];
        memcpy(before_voices,spu.voice,sizeof before_voices);
        assert(vh_native_seq_switch_scene(&seq,invalid_tempo,
                 sizeof invalid_tempo,&spu,resolve,&log_state,1)==-1);
        assert(memcmp(&seq,&before_seq,sizeof seq)==0);
        assert(memcmp(spu.voice,before_voices,sizeof before_voices)==0);
        assert(seq.playing && seq.note_ons==VH_NATIVE_MUSIC_VOICES);
        for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(vh_native_spu_voice_active(&spu,slot));
            assert(seq.note_slot[0][40u+slot]==(int)slot);
            assert(seq.owner_note[slot]==(int)(40u+slot));
        }
    }
}


static void test_seq_reuses_naturally_released_slot_without_stale_owner(void) {
    uint8_t song[15u+20u*4u+4u+3u+4u+3u];
    const uint8_t header[]={HEADER};
    memcpy(song,header,sizeof header);
    size_t n=sizeof header;
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++) {
        song[n++]=0u; song[n++]=0x90u;
        song[n++]=(uint8_t)(40u+i); song[n++]=100u;
    }
    song[n++]=0u; song[n++]=0x80u; song[n++]=47u; song[n++]=0u;
    song[n++]=0x81u; song[n++]=0x70u; /* tick 240 */
    song[n++]=0x90u; song[n++]=60u; song[n++]=110u;
    song[n++]=0x81u; song[n++]=0x70u; /* tick 480 */
    song[n++]=0xffu; song[n++]=0x2fu;
    assert(n<=sizeof song);
    setup();
    assert(vh_native_seq_init(&seq,song,n,&spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==20 && seq.note_offs==1);
    assert(seq.note_slot[0][47]==-1);
    assert(spu.voice[7].adsr.phase==VH_ADSR_RELEASE);
    /* The voice expires through rendering; other nineteen remain held. */
    vh_native_spu_render(&spu,pcm,512u);
    assert(!vh_native_spu_voice_active(&spu,7u));
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++)
        if(i!=7u) assert(vh_native_spu_voice_active(&spu,i));
    for(unsigned block=1u;block<22u;block++) {
        vh_native_spu_render(&spu,pcm,512u);
        assert(vh_native_seq_advance_block(&seq)>=0);
    }
    /* Inspect the new attack before PCM rendering can advance its phase. */
    assert(seq.note_ons==21 && seq.note_offs==1);
    assert(seq.note_slot[0][60]==7);
    assert(seq.owner_ch[7]==0 && seq.owner_note[7]==60);
    assert(seq.note_slot[0][47]==-1);
    assert(vh_native_spu_voice_active(&spu,7u));
    assert(spu.voice[7].adsr.phase==VH_ADSR_ATTACK);
}


static void test_repeated_adsr_release_and_slot_reuse(void) {
    setup();
    /* Hold nineteen slots while the remaining slot repeatedly expires. */
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++)
        assert(vh_native_spu_note_on(&spu,slot,sample,64u,0,64,4096u,
                                     0x000fu,0x0000u,1.0f,1.0f)==0);
    for(unsigned cycle=0;cycle<128u;cycle++) {
        const unsigned slot=cycle%VH_NATIVE_MUSIC_VOICES;
        vh_native_spu_note_off(&spu,slot);
        assert(spu.voice[slot].adsr.phase==VH_ADSR_RELEASE);
        assert(vh_native_spu_voice_active(&spu,slot));
        vh_native_spu_render(&spu,pcm,512u);
        assert(!vh_native_spu_voice_active(&spu,slot));
        for(unsigned other=0;other<VH_NATIVE_MUSIC_VOICES;other++)
            if(other!=slot) assert(vh_native_spu_voice_active(&spu,other));
        assert(vh_native_spu_allocate_slot(&spu)==(int)slot);
        assert(vh_native_spu_note_on(&spu,slot,sample,64u,0,64,4096u,
                                     0x000fu,0x0000u,1.0f,1.0f)==0);
        assert(spu.voice[slot].adsr.phase==VH_ADSR_ATTACK);
        assert(spu.voice[slot].adsr.level==0);
    }
}


static void test_same_note_retrigger_after_release_reuses_slot(void) {
    /* Delayed same-pitch Note On must reclaim an expired release slot,
     * not inherit the previous note's envelope or ownership. */
    static const uint8_t retrigger_song[] = {
        HEADER,
        0,0x90,60,100,
        0,0x80,60,0,
        0x81,0x70,0x90,60,110,
        0x81,0x70,0xff,0x2f
    };
    setup();
    assert(vh_native_seq_init(&seq,retrigger_song,sizeof retrigger_song,
                              &spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==1 && seq.note_offs==1);
    assert(seq.note_slot[0][60]==-1);
    assert(spu.voice[0].adsr.phase==VH_ADSR_RELEASE);
    vh_native_spu_render(&spu,pcm,512u);
    assert(!vh_native_spu_voice_active(&spu,0u));
    for(unsigned block=1u;block<22u;block++) {
        vh_native_spu_render(&spu,pcm,512u);
        assert(vh_native_seq_advance_block(&seq)>=0);
    }
    assert(seq.note_ons==2 && seq.note_offs==1);
    assert(seq.note_slot[0][60]==0);
    assert(seq.owner_ch[0]==0 && seq.owner_note[0]==60);
    assert(vh_native_spu_voice_active(&spu,0u));
    assert(spu.voice[0].adsr.phase==VH_ADSR_ATTACK);
    assert(spu.voice[0].adsr.level==0);
    assert(log_state.calls==2);
}


static void test_immediate_same_note_retrigger_during_release(void) {
    /* Two same-pitch Note Ons in the first scheduler block, with Note Off
     * in between: a releasing voice must not own the newly triggered note. */
    static const uint8_t song[]={
        HEADER,
        0,0x90,60,100,
        0,0x80,60,0,
        0,0x90,60,110,
        0x81,0x70,0xff,0x2f
    };
    setup();
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==2 && seq.note_offs==1);
    /* Slot 0 is still in Release; next allocation takes free slot 1. */
    assert(spu.voice[0].adsr.phase==VH_ADSR_RELEASE);
    assert(seq.note_slot[0][60]==1);
    assert(seq.owner_ch[1]==0 && seq.owner_note[1]==60);
    assert(vh_native_spu_voice_active(&spu,1));
    assert(spu.voice[1].adsr.phase==VH_ADSR_ATTACK);
    assert(spu.voice[1].adsr.level==0);
    assert(log_state.calls==2);
}


static void test_full_spu_retrigger_and_stale_note_off(void) {
    /* All 20 voices are occupied. A released slot is still active,
     * so new notes must steal slots and invalidate old note mappings. */
    static const uint8_t song[] = {
        HEADER,
        0,0x90,40,100,
        0,41,100,0,42,100,0,43,100,0,44,100,
        0,45,100,0,46,100,0,47,100,0,48,100,0,49,100,
        0,50,100,0,51,100,0,52,100,0,53,100,0,54,100,
        0,55,100,0,56,100,0,57,100,0,58,100,0,59,100,
        0,0x80,40,0,   /* slot 0 enters Release, but is still occupied */
        0,0x90,60,110, /* full: steal slot 0 */
        0,0x80,40,0,   /* stale Note Off must not stop note 60 */
        0,0x90,61,100, /* full: steal slot 1 (formerly note 41) */
        0,0x80,41,0,   /* stale Note Off must not stop note 61 */
        0,0x90,60,105, /* retrigger 60: Release slot 0; steal slot 2 */
        0,0x80,41,0,   /* stale Note Off must not stop note 60 */
        0x81,0x70,0x90,62,100, /* after Release: reclaim slot 0 */
        0x81,0x70,0xff,0x2f
    };
    setup();
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,&log_state,1)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==23 && seq.note_offs==2);
    assert(seq.note_slot[0][40]==-1 && seq.note_slot[0][41]==-1);
    assert(seq.note_slot[0][42]==-1);
    assert(seq.note_slot[0][60]==2 && seq.note_slot[0][61]==1);
    assert(seq.owner_ch[0]==-1 && seq.owner_note[0]==-1);
    assert(seq.owner_ch[1]==0 && seq.owner_note[1]==61);
    assert(seq.owner_ch[2]==0 && seq.owner_note[2]==60);
    assert(spu.voice[0].adsr.phase==VH_ADSR_RELEASE);
    for(unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++)
        assert(vh_native_spu_voice_active(&spu,slot));

    vh_native_spu_render(&spu,pcm,512u);
    assert(!vh_native_spu_voice_active(&spu,0u));
    for(unsigned slot=1;slot<VH_NATIVE_MUSIC_VOICES;slot++)
        assert(vh_native_spu_voice_active(&spu,slot));
    for(unsigned block=1u;block<22u;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        if(block<21u) vh_native_spu_render(&spu,pcm,512u);
    }
    assert(seq.note_ons==24 && seq.note_offs==2);
    assert(seq.note_slot[0][62]==0);
    assert(seq.owner_ch[0]==0 && seq.owner_note[0]==62);
    assert(seq.note_slot[0][60]==2 && seq.note_slot[0][61]==1);
    assert(spu.voice[0].adsr.phase==VH_ADSR_ATTACK);
    assert(spu.voice[0].adsr.level==0);
    assert(vh_native_spu_voice_active(&spu,0u));
}

int main(void) {
    test_validation_and_source_immutability();
    test_512_block_controls_and_ring_pressure();
    test_running_tempo_and_repeat_seam();
    test_voice_stealing_stale_note_off();
    test_512_pcm_event_to_spu_fifo();
    test_scene_switch_clears_release_and_reuses_slot();
    test_repeated_scene_switch_with_twenty_live_voices();
    test_natural_adsr_release_reuses_free_slot();
    test_invalid_switch_preserves_twenty_voices();
    test_seq_reuses_naturally_released_slot_without_stale_owner();
    test_repeated_adsr_release_and_slot_reuse();
    test_same_note_retrigger_after_release_reuses_slot();
    test_immediate_same_note_retrigger_during_release();
    test_full_spu_retrigger_and_stale_note_off();
    puts("native pQES SEQ -> 20-voice SPU -> PCM ring: PASS");
    return 0;
}
