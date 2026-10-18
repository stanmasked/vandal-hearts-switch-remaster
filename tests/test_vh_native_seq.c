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

static VhSpuReverb expected_wet_tail;
static VhSpuReverb zero_send_wet_tail;
static VhNativeSpu dry_reference_spu;
static int16_t dry_reference_pcm[VH_AUDIO_BLOCK_FRAMES * 2u];

/* A synthetic tone that explicitly sends PCM to STUDIO_C. */
static int resolve_with_reverb(void *ctx, unsigned program, unsigned note,
                               unsigned velocity, unsigned volume,
                               unsigned pan, VhSeqTone *out) {
    const int result=resolve(ctx,program,note,velocity,volume,pan,out);
    if(!result) out->reverb_send=1u;
    return result;
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

/* Cross-branch regression: the target branch's read-only SEQ audit
 * must coexist with this branch's atomic scene-switch implementation.
 * Missing program/note coverage is diagnostic, not a SPU mutation.
 */
static int resolve_audit_missing(void *ctx, unsigned program, unsigned note,
                                 unsigned velocity, unsigned volume,
                                 unsigned pan, VhSeqTone *out) {
    if(note==61u) return -1;
    return resolve(ctx,program,note,velocity,volume,pan,out);
}
static void test_target_seq_audit_survives_scene_switch_integration(void) {
    setup();
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve,&log_state,1u)==0);
    assert(vh_native_seq_advance_block(&seq)>=0);
    const VhNativeSeq saved_seq=seq;
    const VhNativeSpu saved_spu=spu;
    const VhAudioStream saved_ring=ring;
    VhSeqAudit report={0};
    memset(&log_state,0,sizeof log_state);
    assert(vh_native_seq_audit(controls_song,sizeof controls_song,
                               resolve,&log_state,&report)==0);
    assert(report.events==6u && report.note_events==1u &&
           report.resolved_notes==1u && report.missing_notes==0u &&
           report.program_changes==1u && !report.has_missing);
    assert(log_state.calls==1u && log_state.program==7u &&
           log_state.volume==80u && log_state.pan==0u);
    assert(!memcmp(&seq,&saved_seq,sizeof seq));
    assert(!memcmp(&spu,&saved_spu,sizeof spu));
    assert(!memcmp(&ring,&saved_ring,sizeof ring));

    memset(&log_state,0,sizeof log_state);
    assert(vh_native_seq_audit(running_song,sizeof running_song,
                               resolve_audit_missing,
                               &log_state,&report)==0);
    assert(report.note_events==2u && report.resolved_notes==1u &&
           report.missing_notes==1u && report.has_missing &&
           report.first_missing_channel==0u &&
           report.first_missing_program==0u &&
           report.first_missing_note==61u &&
           report.tempo_changes==1u);
    const VhSeqAudit saved_report=report;
    assert(vh_native_seq_audit(invalid_data,sizeof invalid_data,
                               resolve,&log_state,&report)==-1);
    assert(vh_native_seq_audit(NULL,sizeof controls_song,
                               resolve,&log_state,&report)==-1);
    assert(vh_native_seq_audit(controls_song,sizeof controls_song,
                               NULL,&log_state,&report)==-1);
    assert(!memcmp(&report,&saved_report,sizeof report));
    assert(!memcmp(&seq,&saved_seq,sizeof seq));
    assert(!memcmp(&spu,&saved_spu,sizeof spu));
    assert(!memcmp(&ring,&saved_ring,sizeof ring));
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


static void test_long_full_spu_ownership_soak(void) {
    /* 64 waves of 20 notes. Every later wave steals all 20 voices and
     * dispatches stale Note Offs for the displaced wave. Check exact
     * ownership after each wave, rather than only at the final EOT.
     * Four disjoint pitch banks (40..119) are rotated deterministically. */
    enum { WAVES=64, NOTES=20, BANKS=4 };
    uint8_t song[15u+NOTES*4u+(WAVES-1u)*NOTES*8u+3u];
    const uint8_t header[]={HEADER};
    memcpy(song,header,sizeof header);
    size_t n=sizeof header;
    for(unsigned wave=0u;wave<WAVES;wave++) {
        const unsigned base=40u+(wave%BANKS)*NOTES;
        const unsigned previous=40u+((wave+BANKS-1u)%BANKS)*NOTES;
        for(unsigned i=0u;i<NOTES;i++) {
            song[n++]=(uint8_t)(wave && i==0u ? 32u : 0u);
            song[n++]=0x90u;
            song[n++]=(uint8_t)(base+i);
            song[n++]=100u;
            if(wave) {
                song[n++]=0u;
                song[n++]=0x80u;
                song[n++]=(uint8_t)(previous+i);
                song[n++]=0u;
            }
        }
    }
    song[n++]=32u; song[n++]=0xffu; song[n++]=0x2fu;
    assert(n==sizeof song);
    setup();
    assert(vh_native_seq_init(&seq,song,n,&spu,
                              resolve,&log_state,1)==0);
    for(unsigned wave=0u;wave<WAVES;wave++) {
        const unsigned base=40u+(wave%BANKS)*NOTES;
        const uint64_t expected_ons=(uint64_t)(wave+1u)*NOTES;
        unsigned attempts=0u;
        do {
            assert(++attempts<=8u);
            assert(vh_native_seq_advance_block(&seq)>=0);
            if(seq.note_ons==expected_ons) break;
            assert(seq.note_ons<expected_ons);
            vh_native_spu_render(&spu,pcm,512u);
        } while(1);
        assert(seq.playing && seq.cycles_completed==0);
        assert(seq.note_ons==expected_ons && seq.note_offs==0);
        assert(seq.dispatched_events==expected_ons+(uint64_t)wave*NOTES);
        assert(log_state.calls==expected_ons);
        assert(spu.steal_index==0u);
        for(unsigned slot=0u;slot<NOTES;slot++) {
            assert(vh_native_spu_voice_active(&spu,slot));
            assert(seq.owner_ch[slot]==0);
            assert(seq.owner_note[slot]==(int)(base+slot));
            assert(spu.voice[slot].adsr.phase==VH_ADSR_ATTACK);
            assert(spu.voice[slot].adsr.level==0);
        }
        for(unsigned note=40u;note<120u;note++) {
            const int expected=(note>=base && note<base+NOTES)
                ? (int)(note-base) : -1;
            assert(seq.note_slot[0][note]==expected);
        }
        vh_native_spu_render(&spu,pcm,512u);
        for(unsigned slot=0u;slot<NOTES;slot++)
            assert(vh_native_spu_voice_active(&spu,slot));
        assert(spu.frames_rendered==seq.blocks_advanced*512u);
    }
    unsigned attempts=0u;
    while(seq.playing) {
        assert(++attempts<=8u);
        assert(vh_native_seq_advance_block(&seq)>=0);
        if(!seq.playing) break;
        vh_native_spu_render(&spu,pcm,512u);
    }
    assert(seq.cycles_completed==1u && seq.note_offs==NOTES);
    assert(seq.note_ons==(uint64_t)WAVES*NOTES);
    assert(seq.dispatched_events==(uint64_t)NOTES+
                                  (uint64_t)(WAVES-1u)*NOTES*2u+1u);
    for(unsigned slot=0u;slot<NOTES;slot++) {
        assert(seq.owner_ch[slot]==-1 && seq.owner_note[slot]==-1);
        assert(spu.voice[slot].adsr.phase==VH_ADSR_RELEASE);
    }
    for(unsigned note=40u;note<120u;note++)
        assert(seq.note_slot[0][note]==-1);
    vh_native_spu_render(&spu,pcm,512u);
    for(unsigned slot=0u;slot<NOTES;slot++)
        assert(!vh_native_spu_voice_active(&spu,slot));
    assert(spu.frames_rendered==seq.blocks_advanced*512u);
}


static void test_scene_switch_with_stealing_and_expired_releases(void) {
    /* Cycle generated songs that fill all 20 slots, steal two voices,
     * reject stale Note Offs and let five genuine releases expire.
     * The following scene must discard the remaining 15 active voices. */
    uint8_t song[160u];
    const uint8_t header[]={HEADER};
    memcpy(song,header,sizeof header);
    size_t n=sizeof header;
    for(unsigned note=40u;note<60u;note++) {
        song[n++]=0u; song[n++]=0x90u;
        song[n++]=(uint8_t)note; song[n++]=100u;
    }
    for(unsigned note=60u;note<62u;note++) {
        song[n++]=0u; song[n++]=0x90u;
        song[n++]=(uint8_t)note; song[n++]=110u;
    }
    for(unsigned note=40u;note<42u;note++) {
        song[n++]=0u; song[n++]=0x80u;
        song[n++]=(uint8_t)note; song[n++]=0u;
    }
    for(unsigned note=42u;note<60u;note+=4u) {
        song[n++]=0u; song[n++]=0x80u;
        song[n++]=(uint8_t)note; song[n++]=0u;
    }
    song[n++]=0x81u; song[n++]=0x70u;
    song[n++]=0xffu; song[n++]=0x2fu;
    assert(n<=sizeof song);
    setup();
    memset(&seq,0,sizeof seq);
    for(unsigned iteration=0u;iteration<64u;iteration++) {
        assert(vh_native_seq_switch_scene(&seq,song,n,&spu,
                                          resolve,&log_state,1)==0);
        assert(seq.playing && seq.blocks_advanced==0u);
        assert(seq.note_ons==0u && seq.note_offs==0u);
        assert(spu.frames_rendered==0u && spu.steal_index==0u);
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(!vh_native_spu_voice_active(&spu,slot));
            assert(seq.owner_ch[slot]==-1 && seq.owner_note[slot]==-1);
        }
        assert(vh_native_seq_advance_block(&seq)>0);
        assert(seq.note_ons==22u && seq.note_offs==5u);
        assert(seq.dispatched_events==29u);
        assert(spu.steal_index==2u);
        assert(log_state.calls==(iteration+1u)*22u);
        for(unsigned note=40u;note<62u;note++) {
            int expected;
            if(note>=60u) expected=(int)(note-60u);
            else if(note<42u || (note-42u)%4u==0u) expected=-1;
            else expected=(int)(note-40u);
            assert(seq.note_slot[0][note]==expected);
        }
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            const int released=(slot>=2u && (slot-2u)%4u==0u);
            const int owner=slot==0u ? 60 :
                            (slot==1u ? 61 : (released ? -1 : (int)(40u+slot)));
            assert(seq.owner_ch[slot]==(owner==-1 ? -1 : 0));
            assert(seq.owner_note[slot]==owner);
            assert(vh_native_spu_voice_active(&spu,slot));
            if(released) assert(spu.voice[slot].adsr.phase==VH_ADSR_RELEASE);
        }
        vh_native_spu_render(&spu,pcm,512u);
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            const int released=(slot>=2u && (slot-2u)%4u==0u);
            assert(vh_native_spu_voice_active(&spu,slot)==!released);
        }
        assert(vh_native_spu_allocate_slot(&spu)==2);
        assert(spu.frames_rendered==512u);
        if(iteration%8u==7u) {
            const VhNativeSeq before=seq;
            VhNativeVoice voices[VH_NATIVE_MUSIC_VOICES];
            memcpy(voices,spu.voice,sizeof voices);
            assert(vh_native_seq_switch_scene(&seq,invalid_tempo,
                    sizeof invalid_tempo,&spu,resolve,&log_state,1)==-1);
            assert(memcmp(&before,&seq,sizeof seq)==0);
            assert(memcmp(voices,spu.voice,sizeof voices)==0);
            assert(spu.frames_rendered==512u);
        }
    }
    /* Final scene switch must also clear every remaining active voice. */
    assert(vh_native_seq_switch_scene(&seq,controls_song,
            sizeof controls_song,&spu,resolve,&log_state,1)==0);
    for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++)
        assert(!vh_native_spu_voice_active(&spu,slot));
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==1u && seq.note_slot[0][60]==0);
}


static void test_scene_switch_preserves_live_studio_c_tail(void) {
    /* Keep a synthetic note sounding long enough to charge STUDIO_C.
     * The next valid scene starts far in the future (1920 PPQN ticks),
     * leaving a genuinely silent 96-block interval for the old wet tail.
     * A parallel processor fed only zero send is the sample-exact oracle.
     */
    static const uint8_t previous_song[] = {
        HEADER,0,0x90,60,100,0x8fu,0x00u,0x80,60,0,
        0,0xff,0x2f
    };
    static const uint8_t delayed_song[] = {
        HEADER,0x8fu,0x00u,0x90,60,100,
        0x81u,0x70u,0xff,0x2f
    };
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,previous_song,sizeof previous_song,
                &spu,resolve_with_reverb,&log_state,1)==0);
    for(unsigned block=0u;block<16u;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,pcm,512u);
    }
    assert(seq.note_ons==1u && seq.note_offs==0u);
    assert(vh_native_spu_voice_active(&spu,0u));
    assert(spu.voice[0].reverb_send);
    assert(spu.reverb.cursor>0);
    memcpy(&expected_wet_tail,&spu.reverb,sizeof expected_wet_tail);
    assert(vh_native_seq_switch_scene(&seq,invalid_tempo,
                sizeof invalid_tempo,&spu,resolve,&log_state,1)==-1);
    assert(memcmp(&spu.reverb,&expected_wet_tail,
                  sizeof expected_wet_tail)==0);
    assert(vh_native_spu_voice_active(&spu,0u));

    assert(vh_native_seq_switch_scene(&seq,delayed_song,
                sizeof delayed_song,&spu,resolve,&log_state,1)==0);
    assert(spu.reverb_enabled && spu.reverb_depth==0.75f);
    assert(spu.interpolation==VH_SPU_GAUSSIAN);
    assert(spu.frames_rendered==0u && spu.steal_index==0u);
    assert(memcmp(&spu.reverb,&expected_wet_tail,
                  sizeof expected_wet_tail)==0);
    for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
        assert(!vh_native_spu_voice_active(&spu,slot));
        assert(spu.voice[slot].pcm==NULL);
        assert(!spu.voice[slot].reverb_send);
        assert(seq.owner_ch[slot]==-1 && seq.owner_note[slot]==-1);
    }

    uint64_t tail_energy=0u;
    for(unsigned block=0u;block<96u;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        assert(seq.note_ons==0u && seq.playing);
        vh_native_spu_render(&spu,pcm,512u);
        for(unsigned frame=0u;frame<512u;frame++) {
            int wet_left=0,wet_right=0;
            vh_spu_reverb_process(&expected_wet_tail,0,0,0.75f,
                                  &wet_left,&wet_right);
            assert(pcm[frame*2u]==wet_left);
            assert(pcm[frame*2u+1u]==wet_right);
            tail_energy+=(uint64_t)(wet_left<0 ? -wet_left : wet_left);
            tail_energy+=(uint64_t)(wet_right<0 ? -wet_right : wet_right);
        }
        assert(memcmp(&spu.reverb,&expected_wet_tail,
                      sizeof expected_wet_tail)==0);
    }
    assert(tail_energy>0u);
    assert(spu.frames_rendered==96u*512u);
    assert(seq.note_ons==0u && seq.note_offs==0u);
}


static void test_new_scene_dry_and_wet_notes_mix_with_old_tail(void) {
    /* Independently render the new scene's single dry note and advance
     * a separate STUDIO_C processor, starting with the previous scene's
     * actual history. Test both a voice with EON=0 and one with EON=1.
     * No borrowed voice/PCM state from the previous scene may survive. */
    static const uint8_t sustained_song[] = {
        HEADER,0,0x90,60,100,
        0x8fu,0x00u,0x80,60,0,
        0,0xff,0x2f
    };
    const unsigned blocks_per_scene[]={24u,48u};
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,sustained_song,sizeof sustained_song,
                              &spu,resolve_with_reverb,&log_state,1)==0);
    for(unsigned block=0u;block<16u;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,pcm,512u);
    }
    assert(seq.note_ons==1u && spu.voice[0].reverb_send);
    memcpy(&expected_wet_tail,&spu.reverb,sizeof expected_wet_tail);
    uint64_t inherited_wet_energy=0u;
    uint64_t new_send_energy=0u;
    for(unsigned scene=0u;scene<2u;scene++) {
        const int send=scene==1u;
        const VhSeqResolve resolver=send ? resolve_with_reverb : resolve;
        assert(vh_native_seq_switch_scene(&seq,sustained_song,
                          sizeof sustained_song,&spu,resolver,
                          &log_state,1)==0);
        assert(spu.reverb_enabled && spu.reverb_depth==0.75f);
        assert(spu.frames_rendered==0u && spu.steal_index==0u);
        assert(memcmp(&spu.reverb,&expected_wet_tail,
                      sizeof expected_wet_tail)==0);
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(!vh_native_spu_voice_active(&spu,slot));
            assert(spu.voice[slot].pcm==NULL);
        }
        vh_native_spu_reset(&dry_reference_spu);
        assert(vh_native_spu_set_interpolation(&dry_reference_spu,
                                                VH_SPU_GAUSSIAN)==0);
        assert(vh_native_spu_note_on(&dry_reference_spu,0u,
                    sample,64u,0,64,4096u,15u,0u,100.f/127.f,1.f)==0);
        assert(vh_native_seq_advance_block(&seq)>0);
        assert(seq.note_ons==1u && seq.note_offs==0u);
        assert(seq.note_slot[0][60]==0 && seq.owner_note[0]==60);
        assert(spu.voice[0].reverb_send==send);
        if(send) memcpy(&zero_send_wet_tail,&expected_wet_tail,
                        sizeof zero_send_wet_tail);
        for(unsigned block=0u;block<blocks_per_scene[scene];block++) {
            if(block) assert(vh_native_seq_advance_block(&seq)>=0);
            assert(seq.playing && seq.note_ons==1u && seq.note_offs==0u);
            vh_native_spu_render(&dry_reference_spu,dry_reference_pcm,512u);
            vh_native_spu_render(&spu,pcm,512u);
            for(unsigned frame=0u;frame<512u;frame++) {
                const unsigned left=2u*frame, right=left+1u;
                int wet_l=0,wet_r=0;
                vh_spu_reverb_process(&expected_wet_tail,
                         send ? (int)dry_reference_pcm[left] : 0,
                         send ? (int)dry_reference_pcm[right] : 0,
                         0.75f,&wet_l,&wet_r);
                int mixed_l=(int)dry_reference_pcm[left]+wet_l;
                int mixed_r=(int)dry_reference_pcm[right]+wet_r;
                if(mixed_l>INT16_MAX) mixed_l=INT16_MAX;
                if(mixed_l<INT16_MIN) mixed_l=INT16_MIN;
                if(mixed_r>INT16_MAX) mixed_r=INT16_MAX;
                if(mixed_r<INT16_MIN) mixed_r=INT16_MIN;
                assert(pcm[left]==mixed_l && pcm[right]==mixed_r);
                if(!send) {
                    inherited_wet_energy+=(uint64_t)(wet_l<0?-wet_l:wet_l);
                    inherited_wet_energy+=(uint64_t)(wet_r<0?-wet_r:wet_r);
                } else {
                    new_send_energy+=(uint64_t)(wet_l<0?-wet_l:wet_l);
                    new_send_energy+=(uint64_t)(wet_r<0?-wet_r:wet_r);
                    int ignored_l=0,ignored_r=0;
                    vh_spu_reverb_process(&zero_send_wet_tail,
                         0,0,0.75f,&ignored_l,&ignored_r);
                }
            }
            assert(memcmp(&spu.reverb,&expected_wet_tail,
                          sizeof expected_wet_tail)==0);
            assert(spu.frames_rendered==(uint64_t)(block+1u)*512u);
            assert(dry_reference_spu.frames_rendered==
                                      (uint64_t)(block+1u)*512u);
        }
        if(send) assert(memcmp(&expected_wet_tail,&zero_send_wet_tail,
                              sizeof expected_wet_tail)!=0);
    }
    assert(inherited_wet_energy>0u);
    assert(new_send_energy>0u);
}


static VhNativeSpu pressure_reference_spu;
static VhNativeSpu pressure_before_spu;
static VhNativeSeq pressure_reference_seq;
static VhNativeSeq pressure_before_seq;
static VhAudioStream pressure_expected_ring;
static int16_t pressure_padding[(VH_AUDIO_RING_FRAMES-1024u)*2u];
static int16_t pressure_expected_pcm[VH_AUDIO_BLOCK_FRAMES*2u];

static void test_full_pcm_ring_scene_switch_backpressure(void) {
    /* Fill the transport with two genuine old-scene blocks and marked
     * padding. The new SEQ must start at zero even though old PCM is
     * still queued; a blocked pump may mutate neither scheduler nor DSP. */
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                    &spu,resolve_with_reverb,&log_state,1)==0);
    for(unsigned i=0u;i<2u;i++)
        assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(seq.note_ons==1u && seq.blocks_advanced==2u);
    assert(spu.voice[0].active && spu.voice[0].reverb_send);
    for(size_t i=0u;i<sizeof pressure_padding/sizeof pressure_padding[0];i++)
        pressure_padding[i]=(int16_t)((int)(i%200u)-100);
    assert(vh_audio_stream_write(&ring,pressure_padding,
                        VH_AUDIO_RING_FRAMES-1024u)
                        ==VH_AUDIO_RING_FRAMES-1024u);
    assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
    assert(ring.write_index==ring.read_index);
    memcpy(&pressure_expected_ring,&ring,sizeof ring);
    const uint64_t previous_reverb_frames=spu.frames_rendered;
    const int previous_reverb_cursor=spu.reverb.cursor;

    assert(vh_native_seq_switch_scene(&seq,running_song,sizeof running_song,
                           &spu,resolve,&log_state,1)==0);
    assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(seq.blocks_advanced==0u && seq.note_ons==0u);
    assert(seq.playing && seq.cycles_completed==0u);
    assert(spu.frames_rendered==0u && spu.reverb.cursor==previous_reverb_cursor);
    assert(previous_reverb_frames==1024u);
    for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++)
        assert(!vh_native_spu_voice_active(&spu,slot));

    memcpy(&pressure_before_seq,&seq,sizeof seq);
    memcpy(&pressure_before_spu,&spu,sizeof spu);
    const unsigned calls_before=log_state.calls;
    for(unsigned attempt=0u;attempt<128u;attempt++) {
        assert(vh_native_seq_pump(&seq,&ring)==0);
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        assert(log_state.calls==calls_before);
    }

    /* Drain exactly one page. Construct an independent reference block
     * with the same preserved wet history and fresh music scheduler. */
    const unsigned drains[]={255u,256u,1u};
    unsigned drained=0u;
    for(unsigned i=0u;i<3u;i++) {
        const unsigned count=drains[i];
        assert(vh_audio_stream_read(&pressure_expected_ring,
                                    pressure_expected_pcm,count)==count);
        assert(vh_audio_stream_read(&ring,pcm,count)==count);
        assert(memcmp(pcm,pressure_expected_pcm,
                      count*VH_AUDIO_CHANNELS*sizeof(int16_t))==0);
        drained+=count;
        assert(vh_audio_stream_queued(&ring)==
               VH_AUDIO_RING_FRAMES-drained);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        if(drained<512u) {
            assert(vh_native_seq_pump(&seq,&ring)==0);
            assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
            assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
            assert(log_state.calls==calls_before);
        }
    }
    assert(drained==512u);
    memcpy(&pressure_reference_spu,&spu,sizeof spu);
    memcpy(&pressure_reference_seq,&seq,sizeof seq);
    pressure_reference_seq.spu=&pressure_reference_spu;
    ResolverLog reference_log=log_state;
    pressure_reference_seq.context=&reference_log;
    assert(vh_native_seq_advance_block(&pressure_reference_seq)>0);
    vh_native_spu_render(&pressure_reference_spu,pressure_expected_pcm,512u);
    assert(pressure_reference_seq.note_ons==2u);

    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(seq.blocks_advanced==1u && seq.note_ons==2u);
    assert(seq.note_offs==1u && seq.playing);
    assert(spu.frames_rendered==512u);
    assert(seq.tempo==250000u);
    assert(log_state.calls==calls_before+2u);
    assert(vh_audio_stream_write(&pressure_expected_ring,
                        pressure_expected_pcm,512u)==512u);
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);

    /* Even after the resumed block filled the ring again, subsequent
     * blocked attempts cannot dispatch the next SEQ event. */
    memcpy(&pressure_before_seq,&seq,sizeof seq);
    memcpy(&pressure_before_spu,&spu,sizeof spu);
    for(unsigned i=0u;i<32u;i++) {
        assert(vh_native_seq_pump(&seq,&ring)==0);
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
    }

    /* Compare the original queued PCM, the wraparound write and
     * the new scene's output in exact FIFO order (8 x 512 frames). */
    for(unsigned i=0u;i<8u;i++) {
        assert(vh_audio_stream_read(&pressure_expected_ring,
                        pressure_expected_pcm,512u)==512u);
        assert(vh_audio_stream_read(&ring,pcm,512u)==512u);
        assert(memcmp(pcm,pressure_expected_pcm,sizeof pressure_expected_pcm)==0);
    }
    assert(vh_audio_stream_queued(&ring)==0u);
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(ring.overrun_frames==0u && ring.underrun_frames==0u);
    assert(seq.blocks_advanced==1u && spu.frames_rendered==512u);
}


static void test_repeated_scene_switch_with_full_pcm_fifo(void) {
    /* Existing PCM belongs to the transport, not the current scene.
     * Exercise 64 valid switches, 64 rejected switches and repeated
     * blocked pumps without consuming or changing that queued audio.
     * Once 512 frames are drained, only the final scene may dispatch. */
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve_with_reverb,&log_state,1)==0);
    for(unsigned i=0u;i<2u;i++)
        assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(seq.note_ons==1u && spu.voice[0].reverb_send);
    assert(spu.frames_rendered==1024u);
    for(size_t i=0u;i<sizeof pressure_padding/sizeof pressure_padding[0];i++)
        pressure_padding[i]=(int16_t)((int)(i%307u)-153);
    assert(vh_audio_stream_write(&ring,pressure_padding,
               VH_AUDIO_RING_FRAMES-1024u)==VH_AUDIO_RING_FRAMES-1024u);
    assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
    memcpy(&pressure_expected_ring,&ring,sizeof ring);
    memcpy(&pressure_reference_spu,&spu,sizeof spu);
    const unsigned old_calls=log_state.calls;

    for(unsigned iteration=0u;iteration<64u;iteration++) {
        const int final_type=!!(iteration&1u);
        const uint8_t *music=final_type ? controls_song : running_song;
        const size_t bytes=final_type
            ? sizeof controls_song : sizeof running_song;
        const VhSeqResolve resolver=final_type ? resolve_with_reverb : resolve;
        assert(vh_native_seq_switch_scene(&seq,music,bytes,
                                      &spu,resolver,&log_state,1)==0);
        assert(spu.frames_rendered==0u && spu.steal_index==0u);
        assert(seq.blocks_advanced==0u && seq.note_ons==0u);
        assert(seq.note_offs==0u && seq.playing);
        assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        assert(memcmp(&spu.reverb,&pressure_reference_spu.reverb,
                      sizeof spu.reverb)==0);
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(!vh_native_spu_voice_active(&spu,slot));
            assert(spu.voice[slot].pcm==NULL);
            assert(seq.owner_note[slot]==-1 && seq.owner_ch[slot]==-1);
        }
        memcpy(&pressure_before_seq,&seq,sizeof seq);
        memcpy(&pressure_before_spu,&spu,sizeof spu);
        const uint8_t *bad=final_type ? invalid_tempo : invalid_data;
        const size_t bad_len=final_type
            ? sizeof invalid_tempo : sizeof invalid_data;
        assert(vh_native_seq_switch_scene(&seq,bad,bad_len,
                             &spu,resolve,&log_state,1)==-1);
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
        for(unsigned retry=0u;retry<8u;retry++) {
            assert(vh_native_seq_pump(&seq,&ring)==0);
            assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
            assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
        }
        assert(log_state.calls==old_calls);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    }

    /* Final selected scene is controls_song with EON enabled, and only
     * this scene may contribute the first new PCM page after backpressure. */
    assert(seq.bytes==controls_song && seq.resolver==resolve_with_reverb);
    assert(vh_audio_stream_read(&pressure_expected_ring,
                       pressure_expected_pcm,512u)==512u);
    assert(vh_audio_stream_read(&ring,pcm,512u)==512u);
    assert(memcmp(pcm,pressure_expected_pcm,
                  sizeof pressure_expected_pcm)==0);
    memcpy(&pressure_reference_spu,&spu,sizeof spu);
    memcpy(&pressure_reference_seq,&seq,sizeof seq);
    pressure_reference_seq.spu=&pressure_reference_spu;
    ResolverLog reference_log=log_state;
    pressure_reference_seq.context=&reference_log;
    assert(vh_native_seq_advance_block(&pressure_reference_seq)>0);
    assert(pressure_reference_seq.note_ons==1u);
    assert(pressure_reference_spu.voice[0].reverb_send);
    vh_native_spu_render(&pressure_reference_spu,
                         pressure_expected_pcm,512u);

    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(seq.note_ons==1u && seq.blocks_advanced==1u);
    assert(seq.note_offs==0u && spu.frames_rendered==512u);
    assert(spu.voice[0].reverb_send);
    assert(log_state.calls==old_calls+1u);
    assert(memcmp(&spu.reverb,&pressure_reference_spu.reverb,
                  sizeof spu.reverb)==0);
    assert(vh_audio_stream_write(&pressure_expected_ring,
                             pressure_expected_pcm,512u)==512u);
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(vh_native_seq_pump(&seq,&ring)==0);
    for(unsigned i=0u;i<VH_AUDIO_RING_FRAMES/512u;i++) {
        assert(vh_audio_stream_read(&pressure_expected_ring,
                                   pressure_expected_pcm,512u)==512u);
        assert(vh_audio_stream_read(&ring,pcm,512u)==512u);
        assert(memcmp(pcm,pressure_expected_pcm,
                      sizeof pressure_expected_pcm)==0);
    }
    assert(!vh_audio_stream_queued(&ring));
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(!ring.underrun_frames && !ring.overrun_frames);
}


static void test_chunked_pcm_drain_scene_switch_soak(void) {
    /* The consumer drains a full 4096-frame FIFO in irregular chunks.
     * Repeatedly switching scenes must preserve old PCM, while only
     * exactly 512 available frames allow the next SEQ/SPU block.
     * A detached SPU+SEQ clone supplies the next expected PCM page. */
    static const unsigned drains[6][4] = {
        {1u,511u,0u,0u},
        {255u,256u,1u,0u},
        {127u,128u,257u,0u},
        {509u,2u,1u,0u},
        {32u,64u,128u,288u},
        {128u,128u,128u,128u}
    };
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve_with_reverb,&log_state,1)==0);
    for(unsigned block=0u;block<2u;block++)
        assert(vh_native_seq_pump(&seq,&ring)==512);
    for(size_t i=0u;i<sizeof pressure_padding/sizeof pressure_padding[0];i++)
        pressure_padding[i]=(int16_t)((int)(i%379u)-189);
    assert(vh_audio_stream_write(&ring,pressure_padding,
                       VH_AUDIO_RING_FRAMES-1024u)==
                       VH_AUDIO_RING_FRAMES-1024u);
    memcpy(&pressure_expected_ring,&ring,sizeof ring);
    assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);

    for(unsigned cycle=0u;cycle<48u;cycle++) {
        if(cycle%6u==0u) {
            const int use_running=cycle%12u==6u;
            const uint8_t *song=use_running ? running_song : controls_song;
            const size_t length=use_running
                ? sizeof running_song : sizeof controls_song;
            const VhSeqResolve resolver=use_running
                ? resolve : resolve_with_reverb;
            assert(vh_native_seq_switch_scene(&seq,song,length,
                          &spu,resolver,&log_state,1)==0);
            assert(seq.blocks_advanced==0u && spu.frames_rendered==0u);
            assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        }
        if(cycle%7u==3u) {
            memcpy(&pressure_before_seq,&seq,sizeof seq);
            memcpy(&pressure_before_spu,&spu,sizeof spu);
            assert(vh_native_seq_switch_scene(&seq,invalid_tempo,
                 sizeof invalid_tempo,&spu,resolve,&log_state,1)==-1);
            assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
            assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        }
        memcpy(&pressure_before_seq,&seq,sizeof seq);
        memcpy(&pressure_before_spu,&spu,sizeof spu);
        const unsigned resolver_calls=log_state.calls;
        assert(vh_native_seq_pump(&seq,&ring)==0);
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);

        unsigned drained=0u;
        for(unsigned part=0u;part<4u;part++) {
            const unsigned frames=drains[cycle%6u][part];
            if(!frames) continue;
            assert(vh_audio_stream_read(&pressure_expected_ring,
                              pressure_expected_pcm,frames)==frames);
            assert(vh_audio_stream_read(&ring,pcm,frames)==frames);
            assert(memcmp(pcm,pressure_expected_pcm,
                   (size_t)frames*2u*sizeof(int16_t))==0);
            drained+=frames;
            assert(drained<=512u);
            assert(vh_audio_stream_queued(&ring)==
                                     VH_AUDIO_RING_FRAMES-drained);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
            if(drained<512u) {
                assert(vh_native_seq_pump(&seq,&ring)==0);
                assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
                assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
                assert(log_state.calls==resolver_calls);
            }
        }
        assert(drained==512u);
        memcpy(&pressure_reference_spu,&spu,sizeof spu);
        memcpy(&pressure_reference_seq,&seq,sizeof seq);
        pressure_reference_seq.spu=&pressure_reference_spu;
        ResolverLog reference_log=log_state;
        pressure_reference_seq.context=&reference_log;
        assert(vh_native_seq_advance_block(&pressure_reference_seq)>=0);
        vh_native_spu_render(&pressure_reference_spu,
                             pressure_expected_pcm,512u);

        assert(vh_native_seq_pump(&seq,&ring)==512);
        assert(seq.blocks_advanced==pressure_reference_seq.blocks_advanced);
        assert(seq.note_ons==pressure_reference_seq.note_ons);
        assert(seq.note_offs==pressure_reference_seq.note_offs);
        assert(seq.dispatched_events==pressure_reference_seq.dispatched_events);
        assert(seq.tempo==pressure_reference_seq.tempo);
        assert(seq.playing==pressure_reference_seq.playing);
        assert(seq.cycles_completed==pressure_reference_seq.cycles_completed);
        assert(spu.frames_rendered==pressure_reference_spu.frames_rendered);
        assert(!memcmp(&spu.reverb,&pressure_reference_spu.reverb,
                       sizeof spu.reverb));
        assert(log_state.calls==reference_log.calls);
        assert(vh_audio_stream_write(&pressure_expected_ring,
                                  pressure_expected_pcm,512u)==512u);
        assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        assert(!ring.underrun_frames && !ring.overrun_frames);
    }
    for(unsigned page=0u;page<VH_AUDIO_RING_FRAMES/512u;page++) {
        assert(vh_audio_stream_read(&pressure_expected_ring,
                               pressure_expected_pcm,512u)==512u);
        assert(vh_audio_stream_read(&ring,pcm,512u)==512u);
        assert(memcmp(pcm,pressure_expected_pcm,
                      sizeof pressure_expected_pcm)==0);
    }
    assert(vh_audio_stream_queued(&ring)==0u);
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(!ring.underrun_frames && !ring.overrun_frames);
}

static int16_t underrun_pcm[(VH_AUDIO_BLOCK_FRAMES+256u)*2u];

static void test_pcm_underrun_silence_without_seq_time_drift(void) {
    /* Genuine underruns must zero-fill only the unqueued part. The audio
     * callback must not synthesize extra time or advance the sequencer.
     * Every subsequent 512-frame refill is matched with a detached
     * SEQ+SPU reference, including across FIFO wrap and scene changes. */
    static const uint8_t sustained_song[]={
        HEADER,0,0x90,60,100,0x8fu,0x00u,0x80,60,0,
        0,0xff,0x2f
    };
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,sustained_song,sizeof sustained_song,
                     &spu,resolve_with_reverb,&log_state,1)==0);
    uint64_t expected_underruns=0u;
    for(unsigned cycle=0u;cycle<36u;cycle++) {
        if(cycle && cycle%9u==0u) {
            const VhSeqResolve resolver=(cycle%18u)==0u
                ? resolve_with_reverb : resolve;
            assert(vh_native_seq_switch_scene(&seq,sustained_song,
                 sizeof sustained_song,&spu,resolver,&log_state,1)==0);
            assert(seq.note_ons==0u && seq.blocks_advanced==0u);
            assert(spu.frames_rendered==0u);
        }
        assert(vh_audio_stream_queued(&ring)==0u);
        assert(ring.overrun_frames==0u);
        memcpy(&pressure_before_seq,&seq,sizeof seq);
        memcpy(&pressure_before_spu,&spu,sizeof spu);
        const unsigned calls_before=log_state.calls;
        if(cycle%4u==0u) {
            for(size_t i=0u;i<62u;i++) underrun_pcm[i]=1234;
            assert(vh_audio_stream_read(&ring,underrun_pcm,31u)==0u);
            for(unsigned i=0u;i<62u;i++) assert(underrun_pcm[i]==0);
            expected_underruns+=31u;
            assert(ring.underrun_frames==expected_underruns);
            assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
            assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
            assert(log_state.calls==calls_before);
        }
        memcpy(&pressure_reference_seq,&seq,sizeof seq);
        memcpy(&pressure_reference_spu,&spu,sizeof spu);
        pressure_reference_seq.spu=&pressure_reference_spu;
        ResolverLog reference_log=log_state;
        pressure_reference_seq.context=&reference_log;
        assert(vh_native_seq_advance_block(&pressure_reference_seq)>=0);
        vh_native_spu_render(&pressure_reference_spu,
                             pressure_expected_pcm,512u);
        assert(vh_native_seq_pump(&seq,&ring)==512);
        assert(seq.blocks_advanced==pressure_reference_seq.blocks_advanced);
        assert(seq.note_ons==pressure_reference_seq.note_ons);
        assert(seq.note_offs==pressure_reference_seq.note_offs);
        assert(seq.dispatched_events==pressure_reference_seq.dispatched_events);
        assert(seq.tempo==pressure_reference_seq.tempo);
        assert(seq.playing==pressure_reference_seq.playing);
        assert(spu.frames_rendered==pressure_reference_spu.frames_rendered);
        assert(memcmp(&spu.reverb,&pressure_reference_spu.reverb,
                      sizeof spu.reverb)==0);
        assert(log_state.calls==reference_log.calls);
        assert(vh_audio_stream_queued(&ring)==512u);

        memcpy(&pressure_before_seq,&seq,sizeof seq);
        memcpy(&pressure_before_spu,&spu,sizeof spu);
        for(size_t i=0u;i<sizeof underrun_pcm/sizeof underrun_pcm[0];i++)
            underrun_pcm[i]=1234;
        assert(vh_audio_stream_read(&ring,underrun_pcm,
                        VH_AUDIO_BLOCK_FRAMES+256u)==512u);
        assert(memcmp(underrun_pcm,pressure_expected_pcm,
                      sizeof pressure_expected_pcm)==0);
        for(unsigned i=VH_AUDIO_BLOCK_FRAMES*2u;
              i<(VH_AUDIO_BLOCK_FRAMES+256u)*2u;i++)
            assert(underrun_pcm[i]==0);
        expected_underruns+=256u;
        assert(ring.underrun_frames==expected_underruns);
        assert(vh_audio_stream_queued(&ring)==0u);
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
        assert(ring.overrun_frames==0u);
    }
    assert(seq.note_ons==1u && seq.note_offs==0u);
    assert(spu.frames_rendered==9u*512u);
    assert(ring.underrun_frames==36u*256u+9u*31u);
}


static int16_t variable_underrun_actual[2048u*2u];
static int16_t variable_underrun_expected[2048u*2u];

static void test_variable_underrun_recovery_across_scene_switches(void) {
    /* Drive producer and consumer at different rates, including empty
     * reads, partial reads, bursts and recovered full reads. A detached
     * SEQ/SPU renders the expected PCM before it enters a second FIFO. */
    static const unsigned produced_pages[12] = {
        0u,1u,2u,1u,0u,3u,1u,2u,0u,1u,2u,1u
    };
    static const unsigned requested_frames[12] = {
        64u,1024u,1u,769u,17u,2048u,511u,128u,1536u,3u,512u,897u
    };
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                             &spu,resolve_with_reverb,&log_state,0)==0);
    vh_audio_stream_reset(&pressure_expected_ring);
    memcpy(&pressure_reference_spu,&spu,sizeof spu);
    memcpy(&pressure_reference_seq,&seq,sizeof seq);
    pressure_reference_seq.spu=&pressure_reference_spu;
    ResolverLog reference_log=log_state;
    pressure_reference_seq.context=&reference_log;
    unsigned starved=0u,recovered=0u,positive_samples=0u;
    uint64_t total_missing=0u, total_consumed=0u;
    for(unsigned iteration=0u;iteration<120u;iteration++) {
        if(iteration==40u || iteration==80u) {
            const int middle=iteration==40u;
            const uint8_t *song=middle ? running_song : controls_song;
            const size_t length=middle
                ? sizeof running_song : sizeof controls_song;
            const VhSeqResolve resolver=middle
                ? resolve : resolve_with_reverb;
            const VhAudioStream ring_before=ring;
            assert(vh_native_seq_switch_scene(&seq,song,length,
                             &spu,resolver,&log_state,0)==0);
            assert(vh_native_seq_switch_scene(&pressure_reference_seq,
                             song,length,&pressure_reference_spu,
                             resolver,&reference_log,0)==0);
            assert(memcmp(&ring,&ring_before,sizeof ring)==0);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
            assert(seq.blocks_advanced==0u && spu.frames_rendered==0u);
            assert(spu.reverb_enabled && spu.reverb_depth==0.75f);
        }
        const unsigned pages=produced_pages[iteration%12u];
        for(unsigned page=0u;page<pages;page++) {
            const size_t free_frames=VH_AUDIO_RING_FRAMES-
                                         vh_audio_stream_queued(&ring);
            if(free_frames<VH_AUDIO_BLOCK_FRAMES) {
                memcpy(&pressure_before_seq,&seq,sizeof seq);
                memcpy(&pressure_before_spu,&spu,sizeof spu);
                assert(vh_native_seq_pump(&seq,&ring)==0);
                assert(memcmp(&pressure_before_seq,&seq,sizeof seq)==0);
                assert(memcmp(&pressure_before_spu,&spu,sizeof spu)==0);
            } else {
                assert(vh_native_seq_advance_block(
                                       &pressure_reference_seq)>=0);
                vh_native_spu_render(&pressure_reference_spu,
                                     pressure_expected_pcm,512u);
                assert(vh_audio_stream_write(&pressure_expected_ring,
                                      pressure_expected_pcm,512u)==512u);
                assert(vh_native_seq_pump(&seq,&ring)==512);
            }
            assert(seq.note_ons==pressure_reference_seq.note_ons);
            assert(seq.note_offs==pressure_reference_seq.note_offs);
            assert(seq.dispatched_events==
                                      pressure_reference_seq.dispatched_events);
            assert(seq.blocks_advanced==pressure_reference_seq.blocks_advanced);
            assert(seq.tempo==pressure_reference_seq.tempo);
            assert(seq.playing==pressure_reference_seq.playing);
            assert(spu.frames_rendered==pressure_reference_spu.frames_rendered);
            assert(memcmp(&spu.reverb,&pressure_reference_spu.reverb,
                          sizeof spu.reverb)==0);
            assert(log_state.calls==reference_log.calls);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        }
        const unsigned requested=requested_frames[iteration%12u];
        const size_t queued=vh_audio_stream_queued(&ring);
        const size_t actual=queued<requested ? queued : requested;
        memcpy(&pressure_before_seq,&seq,sizeof seq);
        memcpy(&pressure_before_spu,&spu,sizeof spu);
        for(unsigned i=0u;i<requested*2u;i++) {
            variable_underrun_actual[i]=1234;
            variable_underrun_expected[i]=-1234;
        }
        assert(vh_audio_stream_read(&ring,variable_underrun_actual,
                                    requested)==actual);
        assert(vh_audio_stream_read(&pressure_expected_ring,
                                    variable_underrun_expected,
                                    requested)==actual);
        assert(memcmp(variable_underrun_actual,variable_underrun_expected,
                      requested*2u*sizeof(int16_t))==0);
        for(size_t i=actual*2u;i<(size_t)requested*2u;i++)
            assert(variable_underrun_actual[i]==0);
        for(size_t i=0u;i<actual*2u;i++)
            if(variable_underrun_actual[i]!=0) positive_samples++;
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
        if(actual<requested) starved++;
        else recovered++;
        total_missing+=(uint64_t)(requested-actual);
        total_consumed+=actual;
        assert(ring.underrun_frames==total_missing);
        assert(ring.overrun_frames==0u);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    }
    assert(starved>0u && recovered>0u && positive_samples>0u);
    assert(total_missing>0u && total_consumed>0u);
    /* All queued frames are eventually delivered in original order. */
    while(vh_audio_stream_queued(&ring)) {
        const size_t available=vh_audio_stream_queued(&ring);
        const size_t frames=available>2048u ? 2048u : available;
        assert(vh_audio_stream_read(&pressure_expected_ring,
                         variable_underrun_expected,frames)==frames);
        assert(vh_audio_stream_read(&ring,
                         variable_underrun_actual,frames)==frames);
        assert(memcmp(variable_underrun_actual,variable_underrun_expected,
                      frames*2u*sizeof(int16_t))==0);
    }
    assert(!vh_audio_stream_queued(&pressure_expected_ring));
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(ring.underrun_frames==total_missing);
    assert(ring.overrun_frames==0u);
}


static int16_t alternating_actual[VH_AUDIO_RING_FRAMES*2u];
static int16_t alternating_expected[VH_AUDIO_RING_FRAMES*2u];

static void test_tempo_note_events_under_alternating_backpressure(void) {
    /* The deliberately event-rich song changes tempo three times, keys
     * notes on and off, and loops at FF2F. The PCM consumer alternates
     * between starvation and large drains while the producer repeatedly
     * hits the 512-frame backpressure threshold. A detached SEQ/SPU
     * reference advances only when a whole output page is accepted. */
    static const uint8_t tempo_song[]={
        HEADER,
        0,0xc0,7,
        0,0x90,60,100,
        32,0x80,60,0,
        0,0xff,0x51,0x03,0xd0,0x90,
        32,0x90,60,100,
        24,0x80,60,0,
        0,0xff,0x51,0x07,0xa1,0x20,
        64,0x90,60,100,
        32,0x80,60,0,
        0,0xff,0x51,0x04,0x93,0xe0,
        96,0x90,60,90,
        32,0x80,60,0,
        0x81,0x70,0xff,0x2f
    };
    static const unsigned produce[12]={
        10u,0u,0u,2u,1u,6u,0u,2u,1u,0u,9u,1u
    };
    static const unsigned consume[12]={
        64u,768u,1024u,4096u,17u,1536u,
        255u,3500u,128u,511u,4096u,33u
    };
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,tempo_song,sizeof tempo_song,
                          &spu,resolve_with_reverb,&log_state,0)==0);
    vh_audio_stream_reset(&pressure_expected_ring);
    memcpy(&pressure_reference_spu,&spu,sizeof spu);
    memcpy(&pressure_reference_seq,&seq,sizeof seq);
    pressure_reference_seq.spu=&pressure_reference_spu;
    ResolverLog reference_log=log_state;
    pressure_reference_seq.context=&reference_log;

    /* Begin fully backed up. The initial bytes are known old queued PCM,
     * independent of the new SEQ, and must retain their FIFO order. */
    memset(pcm,0,sizeof pcm);
    for(unsigned page=0u;page<8u;page++) {
        assert(vh_audio_stream_write(&ring,pcm,512u)==512u);
        assert(vh_audio_stream_write(&pressure_expected_ring,
                                     pcm,512u)==512u);
    }
    unsigned stalled=0u,starved=0u,recovered=0u;
    unsigned note_on_seen=0u,note_off_seen=0u,loop_seen=0u;
    unsigned tempo_seen=0u;
    uint64_t produced=0u,read_frames=0u,missing_frames=0u;
    for(unsigned cycle=0u;cycle<240u;cycle++) {
        if(cycle==80u || cycle==160u) {
            const VhSeqResolve resolver=cycle==80u
                                       ? resolve : resolve_with_reverb;
            assert(vh_native_seq_switch_scene(&seq,tempo_song,
                    sizeof tempo_song,&spu,resolver,&log_state,0)==0);
            assert(vh_native_seq_switch_scene(&pressure_reference_seq,
                    tempo_song,sizeof tempo_song,&pressure_reference_spu,
                    resolver,&reference_log,0)==0);
            assert(seq.blocks_advanced==0u && spu.frames_rendered==0u);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
            assert(memcmp(&spu.reverb,&pressure_reference_spu.reverb,
                          sizeof spu.reverb)==0);
        }
        for(unsigned attempt=0u;attempt<produce[cycle%12u];attempt++) {
            const size_t queued=vh_audio_stream_queued(&ring);
            if(VH_AUDIO_RING_FRAMES-queued<512u) {
                memcpy(&pressure_before_seq,&seq,sizeof seq);
                memcpy(&pressure_before_spu,&spu,sizeof spu);
                assert(vh_native_seq_pump(&seq,&ring)==0);
                assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
                assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
                stalled++;
            } else {
                const uint64_t old_ons=seq.note_ons;
                const uint64_t old_offs=seq.note_offs;
                const unsigned old_cycles=seq.cycles_completed;
                assert(vh_native_seq_advance_block(
                                       &pressure_reference_seq)>=0);
                vh_native_spu_render(&pressure_reference_spu,
                                     pressure_expected_pcm,512u);
                assert(vh_audio_stream_write(&pressure_expected_ring,
                                    pressure_expected_pcm,512u)==512u);
                assert(vh_native_seq_pump(&seq,&ring)==512);
                if(seq.note_ons>old_ons) note_on_seen++;
                if(seq.note_offs>old_offs) note_off_seen++;
                if(seq.cycles_completed>old_cycles) loop_seen++;
                if(seq.tempo==250000u) tempo_seen|=1u;
                if(seq.tempo==500000u) tempo_seen|=2u;
                if(seq.tempo==300000u) tempo_seen|=4u;
                produced++;
            }
            assert(seq.blocks_advanced==pressure_reference_seq.blocks_advanced);
            assert(seq.dispatched_events==
                                      pressure_reference_seq.dispatched_events);
            assert(seq.note_ons==pressure_reference_seq.note_ons);
            assert(seq.note_offs==pressure_reference_seq.note_offs);
            assert(seq.tempo==pressure_reference_seq.tempo);
            assert(seq.cycles_completed==pressure_reference_seq.cycles_completed);
            assert(seq.playing==pressure_reference_seq.playing);
            assert(seq.tick_budget==pressure_reference_seq.tick_budget);
            assert(spu.frames_rendered==pressure_reference_spu.frames_rendered);
            assert(memcmp(spu.voice,pressure_reference_spu.voice,
                          sizeof spu.voice)==0);
            assert(memcmp(&spu.reverb,&pressure_reference_spu.reverb,
                          sizeof spu.reverb)==0);
            assert(log_state.calls==reference_log.calls);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        }

        const unsigned requested=consume[cycle%12u];
        const size_t queued=vh_audio_stream_queued(&ring);
        const size_t actual=queued<requested ? queued : requested;
        memcpy(&pressure_before_seq,&seq,sizeof seq);
        memcpy(&pressure_before_spu,&spu,sizeof spu);
        memset(alternating_actual,0x5a,sizeof alternating_actual);
        memset(alternating_expected,0xa5,sizeof alternating_expected);
        assert(vh_audio_stream_read(&ring,alternating_actual,
                                     requested)==actual);
        assert(vh_audio_stream_read(&pressure_expected_ring,
                                     alternating_expected,
                                     requested)==actual);
        assert(memcmp(alternating_actual,alternating_expected,
                      (size_t)requested*2u*sizeof(int16_t))==0);
        for(size_t n=actual*2u;n<(size_t)requested*2u;n++)
            assert(alternating_actual[n]==0);
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
        if(actual<requested) starved++; else recovered++;
        read_frames+=actual;
        missing_frames+=(uint64_t)(requested-actual);
        assert(ring.underrun_frames==missing_frames);
        assert(!ring.overrun_frames);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    }
    assert(stalled>0u && starved>0u && recovered>0u);
    assert(note_on_seen>0u && note_off_seen>0u && loop_seen>0u);
    assert(tempo_seen==7u);
    assert(produced>50u && read_frames>0u && missing_frames>0u);
    while(vh_audio_stream_queued(&ring)) {
        const size_t remaining=vh_audio_stream_queued(&ring);
        const size_t count=remaining>4096u ? 4096u : remaining;
        assert(vh_audio_stream_read(&pressure_expected_ring,
                               alternating_expected,count)==count);
        assert(vh_audio_stream_read(&ring,alternating_actual,count)==count);
        assert(memcmp(alternating_actual,alternating_expected,
                      count*2u*sizeof(int16_t))==0);
    }
    assert(!vh_audio_stream_queued(&pressure_expected_ring));
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(!ring.overrun_frames);
}


static void test_full_pcm_queue_scene_switch_alternating_eon(void) {
    /* Old PCM pages are immutable across scene changes. Each new note
     * starts from a cleared voice, but the STUDIO_C tail and wet settings
     * persist. A separate dry SPU and wet network form a sample-exact
     * oracle for the newly appended block, with EON alternating. */
    static const uint8_t sustained_song[] = {
        HEADER,0,0x90,60,100,0x8fu,0x00u,0x80,60,0,
        0,0xff,0x2f
    };
    setup();
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    assert(vh_native_seq_init(&seq,sustained_song,sizeof sustained_song,
                              &spu,resolve_with_reverb,&log_state,1)==0);
    for(unsigned i=0u;i<VH_AUDIO_RING_FRAMES/VH_AUDIO_BLOCK_FRAMES;i++)
        assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
    assert(seq.note_ons==1u && seq.note_offs==0u);
    assert(spu.voice[0].reverb_send && spu.reverb.cursor>0);
    memcpy(&pressure_expected_ring,&ring,sizeof ring);
    memcpy(&expected_wet_tail,&spu.reverb,sizeof expected_wet_tail);
    uint64_t heard_wet=0u;

    for(unsigned iteration=0u;iteration<48u;iteration++) {
        const int send=(iteration&1u)!=0u;
        const VhSeqResolve resolver=send ? resolve_with_reverb : resolve;
        assert(vh_native_seq_switch_scene(&seq,sustained_song,
                    sizeof sustained_song,&spu,resolver,&log_state,1)==0);
        assert(seq.blocks_advanced==0u && seq.note_ons==0u);
        assert(seq.note_offs==0u && seq.playing);
        assert(spu.frames_rendered==0u && spu.steal_index==0u);
        assert(spu.reverb_enabled && spu.reverb_depth==0.75f);
        assert(memcmp(&spu.reverb,&expected_wet_tail,
                      sizeof expected_wet_tail)==0);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(!vh_native_spu_voice_active(&spu,slot));
            assert(spu.voice[slot].pcm==NULL);
            assert(!spu.voice[slot].reverb_send);
            assert(seq.owner_ch[slot]==-1 && seq.owner_note[slot]==-1);
        }

        memcpy(&pressure_before_seq,&seq,sizeof seq);
        memcpy(&pressure_before_spu,&spu,sizeof spu);
        assert(vh_native_seq_pump(&seq,&ring)==0);
        assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);

        /* Both partial reads must remain FIFO-exact; 511 free frames
         * are insufficient to dispatch the scene's first Note On. */
        const unsigned first=iteration%3u==0u ? 1u :
                             (iteration%3u==1u ? 255u : 511u);
        const unsigned parts[2]={first,512u-first};
        for(unsigned part=0u;part<2u;part++) {
            const unsigned frames=parts[part];
            assert(vh_audio_stream_read(&pressure_expected_ring,
                                        pressure_expected_pcm,frames)==frames);
            assert(vh_audio_stream_read(&ring,pcm,frames)==frames);
            assert(memcmp(pcm,pressure_expected_pcm,
                          frames*2u*sizeof(int16_t))==0);
            if(!part) {
                assert(vh_native_seq_pump(&seq,&ring)==0);
                assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
                assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
            }
        }
        assert(vh_audio_stream_queued(&ring)==
               VH_AUDIO_RING_FRAMES-VH_AUDIO_BLOCK_FRAMES);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);

        /* Compute the first new PCM page using separate dry synthesis
         * and a wet processor inherited from the old scene. A second
         * zero-send network tests that EON=0 never contributes send. */
        vh_native_spu_reset(&dry_reference_spu);
        assert(vh_native_spu_set_interpolation(&dry_reference_spu,
                                                VH_SPU_GAUSSIAN)==0);
        assert(vh_native_spu_note_on(&dry_reference_spu,0u,
                      sample,64u,0,64,4096u,15u,0u,100.f/127.f,1.f)==0);
        vh_native_spu_render(&dry_reference_spu,dry_reference_pcm,512u);
        memcpy(&zero_send_wet_tail,&expected_wet_tail,
               sizeof zero_send_wet_tail);
        for(unsigned frame=0u;frame<512u;frame++) {
            const unsigned left=frame*2u,right=left+1u;
            const int dry_l=dry_reference_pcm[left];
            const int dry_r=dry_reference_pcm[right];
            int wet_l=0,wet_r=0,ignored_l=0,ignored_r=0;
            vh_spu_reverb_process(&expected_wet_tail,
                     send ? dry_l : 0,send ? dry_r : 0,
                     0.75f,&wet_l,&wet_r);
            vh_spu_reverb_process(&zero_send_wet_tail,0,0,0.75f,
                                  &ignored_l,&ignored_r);
            int mixed_l=dry_l+wet_l,mixed_r=dry_r+wet_r;
            if(mixed_l>INT16_MAX) mixed_l=INT16_MAX;
            if(mixed_l<INT16_MIN) mixed_l=INT16_MIN;
            if(mixed_r>INT16_MAX) mixed_r=INT16_MAX;
            if(mixed_r<INT16_MIN) mixed_r=INT16_MIN;
            pressure_expected_pcm[left]=(int16_t)mixed_l;
            pressure_expected_pcm[right]=(int16_t)mixed_r;
            heard_wet+=(uint64_t)(wet_l<0 ? -wet_l : wet_l);
            heard_wet+=(uint64_t)(wet_r<0 ? -wet_r : wet_r);
        }
        if(send) {
            assert(memcmp(&expected_wet_tail,&zero_send_wet_tail,
                          sizeof expected_wet_tail)!=0);
        } else {
            assert(memcmp(&expected_wet_tail,&zero_send_wet_tail,
                          sizeof expected_wet_tail)==0);
        }

        const unsigned old_calls=log_state.calls;
        assert(vh_native_seq_pump(&seq,&ring)==512);
        assert(seq.blocks_advanced==1u && spu.frames_rendered==512u);
        assert(seq.note_ons==1u && seq.note_offs==0u);
        assert(seq.note_slot[0][60]==0 && seq.owner_note[0]==60);
        assert(spu.voice[0].reverb_send==send);
        assert(log_state.calls==old_calls+1u);
        assert(memcmp(&spu.reverb,&expected_wet_tail,
                      sizeof expected_wet_tail)==0);
        assert(vh_audio_stream_write(&pressure_expected_ring,
                           pressure_expected_pcm,512u)==512u);
        assert(vh_audio_stream_queued(&ring)==VH_AUDIO_RING_FRAMES);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        assert(!ring.overrun_frames && !ring.underrun_frames);
    }
    assert(heard_wet>0u);
    for(unsigned i=0u;i<VH_AUDIO_RING_FRAMES/VH_AUDIO_BLOCK_FRAMES;i++) {
        assert(vh_audio_stream_read(&pressure_expected_ring,
                           pressure_expected_pcm,512u)==512u);
        assert(vh_audio_stream_read(&ring,pcm,512u)==512u);
        assert(memcmp(pcm,pressure_expected_pcm,
                      sizeof pressure_expected_pcm)==0);
    }
    assert(vh_audio_stream_queued(&ring)==0u);
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
}


static void test_long_eon_tempo_scene_switch_under_variable_pcm_load(void) {
    /* Each SEQ has one voice, rapid FF51 changes and NoteOff. For
     * 24 scenes the consumer makes irregular reads (including underruns)
     * while the producer repeatedly meets a full ring. Compare every
     * accepted PCM frame to a separately clocked dry SPU plus an
     * independently advanced STUDIO_C wet network. The current epoch
     * may replace voices but never invalidate old enqueued PCM. */
    static const uint8_t song_a[]={
        HEADER,
        0,0x90,60,100,
        11,0xff,0x51,0x03,0xd0,0x90, /* 250000 */
        24,0x80,60,0,
        1,0xff,0x51,0x07,0xa1,0x20, /* 500000 */
        35,0xff,0x51,0x04,0x93,0xe0, /* 300000 */
        70,0xff,0x51,0x06,0x1a,0x80, /* 400000 */
        0x83,0x10,0xff,0x2f
    };
    static const uint8_t song_b[]={
        HEADER,
        0,0x90,60,100,
        10,0xff,0x51,0x04,0x93,0xe0, /* 300000 */
        25,0x80,60,0,
        1,0xff,0x51,0x03,0xd0,0x90, /* 250000 */
        35,0xff,0x51,0x07,0xa1,0x20, /* 500000 */
        70,0xff,0x51,0x06,0x1a,0x80, /* 400000 */
        0x83,0x10,0xff,0x2f
    };
    static const unsigned requests[24]={
        0u,0u,255u,257u,0u,1024u,32u,0u,
        4096u,0u,0u,1536u,1u,511u,128u,128u,
        384u,0u,2048u,0u,512u,64u,640u,0u
    };
    setup();
    vh_audio_stream_reset(&pressure_expected_ring);
    memset(&seq,0,sizeof seq);
    memset(&pressure_reference_seq,0,sizeof pressure_reference_seq);
    assert(vh_native_spu_set_reverb(&spu,1,0.75f)==0);
    vh_native_spu_reset(&dry_reference_spu);
    assert(vh_native_spu_set_interpolation(&dry_reference_spu,
                                            VH_SPU_GAUSSIAN)==0);
    memset(&expected_wet_tail,0,sizeof expected_wet_tail);
    ResolverLog reference_log={0};
    for(size_t i=0u;i<VH_AUDIO_RING_FRAMES*2u;i++)
        alternating_expected[i]=(int16_t)((int)(i%317u)-158);
    assert(vh_audio_stream_write(&ring,alternating_expected,
                         VH_AUDIO_RING_FRAMES)==VH_AUDIO_RING_FRAMES);
    assert(vh_audio_stream_write(&pressure_expected_ring,
                         alternating_expected,VH_AUDIO_RING_FRAMES)
                         ==VH_AUDIO_RING_FRAMES);

    uint64_t total_missing=0u,total_pcm=0u,total_on=0u,total_off=0u;
    unsigned blocked=0u,underruns=0u,nonempty_switches=0u;
    unsigned wet_scenes=0u,dry_scenes=0u;
    for(unsigned epoch=0u;epoch<24u;epoch++) {
        const int send=!!(epoch&1u);
        const uint8_t *music=(epoch%4u)<2u ? song_a : song_b;
        const size_t music_size=(epoch%4u)<2u
                                ? sizeof song_a : sizeof song_b;
        const VhSeqResolve tone_resolver=send
                                    ? resolve_with_reverb : resolve;
        if(vh_audio_stream_queued(&ring)) nonempty_switches++;
        assert(vh_native_seq_switch_scene(&seq,music,music_size,&spu,
                                  tone_resolver,&log_state,1)==0);
        assert(vh_native_seq_switch_scene(&pressure_reference_seq,
                music,music_size,&dry_reference_spu,
                resolve,&reference_log,1)==0);
        assert(spu.frames_rendered==0u &&
               dry_reference_spu.frames_rendered==0u);
        assert(seq.blocks_advanced==0u && seq.note_ons==0u);
        assert(seq.note_offs==0u && seq.playing);
        assert(memcmp(&spu.reverb,&expected_wet_tail,
                      sizeof expected_wet_tail)==0);
        assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(!vh_native_spu_voice_active(&spu,slot));
            assert(!spu.voice[slot].reverb_send);
            assert(seq.owner_ch[slot]==-1 && seq.owner_note[slot]==-1);
        }

        if(epoch%5u==3u) {
            memcpy(&pressure_before_seq,&seq,sizeof seq);
            memcpy(&pressure_before_spu,&spu,sizeof spu);
            assert(vh_native_seq_switch_scene(&seq,invalid_tempo,
                    sizeof invalid_tempo,&spu,resolve,&log_state,1)==-1);
            assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
            assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        }
        unsigned tempo_mask=0u,accepted=0u;
        for(unsigned step=0u;step<24u;step++) {
            const size_t free_frames=VH_AUDIO_RING_FRAMES-
                                         vh_audio_stream_queued(&ring);
            if(free_frames<512u) {
                memcpy(&pressure_before_seq,&seq,sizeof seq);
                memcpy(&pressure_before_spu,&spu,sizeof spu);
                assert(vh_native_seq_pump(&seq,&ring)==0);
                assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
                assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
                blocked++;
            } else {
                assert(vh_native_seq_advance_block(
                                       &pressure_reference_seq)>=0);
                vh_native_spu_render(&dry_reference_spu,
                                     dry_reference_pcm,512u);
                for(unsigned frame=0u;frame<512u;frame++) {
                    const unsigned l=frame*2u,r=l+1u;
                    const int dry_l=dry_reference_pcm[l];
                    const int dry_r=dry_reference_pcm[r];
                    int wet_l=0,wet_r=0;
                    vh_spu_reverb_process(&expected_wet_tail,
                        send ? dry_l : 0,send ? dry_r : 0,
                        0.75f,&wet_l,&wet_r);
                    int mixed_l=dry_l+wet_l,mixed_r=dry_r+wet_r;
                    if(mixed_l>INT16_MAX) mixed_l=INT16_MAX;
                    if(mixed_l<INT16_MIN) mixed_l=INT16_MIN;
                    if(mixed_r>INT16_MAX) mixed_r=INT16_MAX;
                    if(mixed_r<INT16_MIN) mixed_r=INT16_MIN;
                    pressure_expected_pcm[l]=(int16_t)mixed_l;
                    pressure_expected_pcm[r]=(int16_t)mixed_r;
                }
                assert(vh_native_seq_pump(&seq,&ring)==512);
                assert(vh_audio_stream_write(&pressure_expected_ring,
                                     pressure_expected_pcm,512u)==512u);
                accepted++;
                total_pcm+=512u;
            }
            assert(seq.note_ons==pressure_reference_seq.note_ons);
            assert(seq.note_offs==pressure_reference_seq.note_offs);
            assert(seq.dispatched_events==
                   pressure_reference_seq.dispatched_events);
            assert(seq.tempo==pressure_reference_seq.tempo);
            assert(seq.blocks_advanced==pressure_reference_seq.blocks_advanced);
            assert(seq.cycles_completed==pressure_reference_seq.cycles_completed);
            assert(seq.tick_budget==pressure_reference_seq.tick_budget);
            assert(seq.playing==pressure_reference_seq.playing);
            assert(spu.frames_rendered==dry_reference_spu.frames_rendered);
            assert(memcmp(&spu.reverb,&expected_wet_tail,
                          sizeof expected_wet_tail)==0);
            assert(log_state.calls==reference_log.calls);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
            if(seq.tempo==250000u) tempo_mask|=1u;
            if(seq.tempo==300000u) tempo_mask|=2u;
            if(seq.tempo==400000u) tempo_mask|=4u;
            if(seq.tempo==500000u) tempo_mask|=8u;

            const unsigned request=requests[step];
            const size_t present=vh_audio_stream_queued(&ring);
            const size_t actual=present<request ? present : request;
            memcpy(&pressure_before_seq,&seq,sizeof seq);
            memcpy(&pressure_before_spu,&spu,sizeof spu);
            assert(vh_audio_stream_read(&pressure_expected_ring,
                                 alternating_expected,request)==actual);
            assert(vh_audio_stream_read(&ring,
                                 alternating_actual,request)==actual);
            assert(memcmp(alternating_actual,alternating_expected,
                          request*2u*sizeof(int16_t))==0);
            for(size_t i=actual*2u;i<request*2u;i++)
                assert(alternating_actual[i]==0);
            assert(memcmp(&seq,&pressure_before_seq,sizeof seq)==0);
            assert(memcmp(&spu,&pressure_before_spu,sizeof spu)==0);
            total_missing+=(uint64_t)(request-actual);
            if(actual<request) underruns++;
            assert(ring.underrun_frames==total_missing);
            assert(ring.overrun_frames==0u);
            assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
        }
        assert(accepted>=16u);
        assert(seq.note_ons==1u && seq.note_offs==1u);
        assert(tempo_mask==15u);
        total_on+=seq.note_ons;
        total_off+=seq.note_offs;
        if(send) wet_scenes++;else dry_scenes++;
    }
    assert(total_pcm>200000u && total_on==24u && total_off==24u);
    assert(blocked>0u && underruns>0u && nonempty_switches==24u);
    assert(wet_scenes==12u && dry_scenes==12u);
    while(vh_audio_stream_queued(&ring)) {
        const size_t n=vh_audio_stream_queued(&ring);
        assert(n<=VH_AUDIO_RING_FRAMES);
        assert(vh_audio_stream_read(&pressure_expected_ring,
                                  alternating_expected,n)==n);
        assert(vh_audio_stream_read(&ring,alternating_actual,n)==n);
        assert(memcmp(alternating_actual,alternating_expected,
                      n*2u*sizeof(int16_t))==0);
    }
    assert(vh_audio_stream_queued(&pressure_expected_ring)==0u);
    assert(memcmp(&ring,&pressure_expected_ring,sizeof ring)==0);
    assert(!ring.overrun_frames && ring.underrun_frames==total_missing);
}

int main(void) {
    test_target_seq_audit_survives_scene_switch_integration();
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
    test_long_full_spu_ownership_soak();
    test_scene_switch_with_stealing_and_expired_releases();
    test_scene_switch_preserves_live_studio_c_tail();
    test_new_scene_dry_and_wet_notes_mix_with_old_tail();
    test_full_pcm_ring_scene_switch_backpressure();
    test_repeated_scene_switch_with_full_pcm_fifo();
    test_chunked_pcm_drain_scene_switch_soak();
    test_pcm_underrun_silence_without_seq_time_drift();
    test_variable_underrun_recovery_across_scene_switches();
    test_tempo_note_events_under_alternating_backpressure();
    test_full_pcm_queue_scene_switch_alternating_eon();
    test_long_eon_tempo_scene_switch_under_variable_pcm_load();
    puts("native pQES SEQ -> 20-voice SPU -> PCM ring: PASS");
    return 0;
}
