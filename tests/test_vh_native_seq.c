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
/* Twenty simultaneous sustained voices must all detach from the old
 * bank before its caller-owned sample storage can be freed. */
static const uint8_t full_voice_scene_song[]={
    HEADER,
    0,0xc0,7,
    0,0x90,60,100,
    0,61,100, 0,62,100, 0,63,100, 0,64,100,
    0,65,100, 0,66,100, 0,67,100, 0,68,100,
    0,69,100, 0,70,100, 0,71,100, 0,72,100,
    0,73,100, 0,74,100, 0,75,100, 0,76,100,
    0,77,100, 0,78,100, 0,79,100,
    0x87,0x68,0xff,0x2f
};
/* A SEQ which first contains a plausible complete NOTE-ON event
 * sequence, then an incomplete tempo payload without terminal EOT.
 * A preflight which inspected only the first notes could incorrectly
 * clear all twenty live voices before discovering the corruption. */
static const uint8_t late_invalid_scene_song[]={
    HEADER,
    0,0xc0,7,
    0,0x90,60,100,
    0,61,100, 0,62,100, 0,63,100, 0,64,100,
    0,65,100, 0,66,100, 0,67,100, 0,68,100,
    0,69,100, 0,70,100, 0,71,100, 0,72,100,
    0,73,100, 0,74,100, 0,75,100, 0,76,100,
    0,77,100, 0,78,100, 0,79,100,
    0x81,0x70,0xff,0x51,0x03
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

/* Sustain three independent voices through FF51 and CC7/CC10 changes.
 * The existing voice keeps its original per-note gains, while each new
 * note uses the most recent controls. FIFO backpressure must not cause
 * a tempo jump or interrupt the already-playing voice.
 */
static int resolve_pan_sensitive(void *ctx, unsigned program, unsigned note,
                                 unsigned velocity, unsigned volume,
                                 unsigned pan, VhSeqTone *out) {
    if (resolve(ctx,program,note,velocity,volume,pan,out)) return -1;
    const float base=(float)velocity/127.f*(float)volume/127.f;
    const float left=pan<64u ? 1.f:(127.f-(float)pan)/63.f;
    const float right=pan<64u ? (float)pan/63.f:1.f;
    out->gain_left=base*left;
    out->gain_right=base*right;
    return 0;
}

static void test_sustained_voices_across_tempo_pan_and_backpressure(void) {
    static const uint8_t song[] = {
        HEADER,
        0,0xc0,7, 0,0xb0,7,100, 0,0xb0,10,0,
        0,0x90,60,127,      /* tick 0: sustained hard-left voice */
        15,0xff,0x51,3,0xd0,0x90, /* tempo doubles at tick15 */
        0,0xb0,7,40, 0,0xb0,10,127,
        0,0x90,61,127,      /* tick 15: independent hard-right voice */
        30,0xb0,7,80, 0,0xb0,10,64,
        0,0x90,62,127,      /* tick 45: new centered voice */
        0x81,0x70,0xff,0x2f
    };
    setup();
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                              resolve_pan_sensitive,&log_state,1)==0);

    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(vh_audio_stream_read(&ring,pcm,512)==512);
    assert(seq.note_ons==1u && seq.tempo==500000u);
    const int slot0=seq.note_slot[0][60];
    assert(slot0>=0);
    assert(spu.voice[slot0].gain_left>0.f);
    assert(spu.voice[slot0].gain_right==0.f);
    assert(vh_native_spu_voice_active(&spu,(unsigned)slot0));
    const int left_before=pcm[(512u-1u)*2u];
    assert(left_before>0);
    for(unsigned i=0;i<512u;++i) assert(pcm[2u*i+1u]==0);

    /* Simulate a full callback ring. A blocked pump must not dispatch
     * CC/tempo events or synthesize any output samples. */
    int16_t zeros[VH_AUDIO_RING_FRAMES*2u]={0};
    assert(vh_audio_stream_write(&ring,zeros,VH_AUDIO_RING_FRAMES)
           ==VH_AUDIO_RING_FRAMES);
    assert(vh_native_seq_pump(&seq,&ring)==0);
    assert(seq.blocks_advanced==1u && seq.note_ons==1u);
    assert(seq.tempo==500000u && seq.volumes[0]==100u &&
           seq.pans[0]==0u && spu.frames_rendered==512u);
    vh_audio_stream_reset(&ring);

    /* Second block includes tempo and pan changes, plus note 61.
     * Voice 60 must remain hard left at exactly its prior gain. */
    const float held_left=spu.voice[slot0].gain_left;
    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(vh_audio_stream_read(&ring,pcm,512)==512);
    assert(seq.blocks_advanced==2u && seq.note_ons==2u);
    assert(seq.tempo==250000u && seq.volumes[0]==40u &&
           seq.pans[0]==127u);
    const int slot1=seq.note_slot[0][61];
    assert(slot1>=0 && slot1!=slot0);
    assert(spu.voice[slot0].gain_left==held_left);
    assert(spu.voice[slot0].gain_right==0.f);
    assert(vh_native_spu_voice_active(&spu,(unsigned)slot0));
    assert(spu.voice[slot1].gain_left==0.f &&
           spu.voice[slot1].gain_right>0.f);
    const int boundary_delta=pcm[0]-left_before;
    assert(boundary_delta>=-1 && boundary_delta<=1);
    unsigned l=0,r=0;
    for(unsigned i=0;i<512u;++i) {
        if(pcm[2u*i]) ++l;
        if(pcm[2u*i+1u]) ++r;
    }
    assert(l>0u && r>0u);

    /* At the new tick rate, the 30-tick delay to note 62 spans a
     * complete quiet-in-events block; held sound must not disappear. */
    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(vh_audio_stream_read(&ring,pcm,512)==512);
    assert(seq.note_ons==2u);
    assert(vh_native_spu_voice_active(&spu,(unsigned)slot0));
    assert(vh_native_spu_voice_active(&spu,(unsigned)slot1));
    l=r=0;
    for(unsigned i=0;i<512u;++i) {
        if(pcm[2u*i]) ++l;
        if(pcm[2u*i+1u]) ++r;
    }
    assert(l>0u && r>0u);

    assert(vh_native_seq_pump(&seq,&ring)==512);
    assert(vh_audio_stream_read(&ring,pcm,512)==512);
    assert(seq.blocks_advanced==4u && seq.note_ons==3u);
    assert(seq.tempo==250000u && seq.volumes[0]==80u &&
           seq.pans[0]==64u);
    assert(log_state.calls==3u && log_state.note==62u);
    assert(log_state.volume==80u && log_state.pan==64u);
    const int slot2=seq.note_slot[0][62];
    assert(slot2>=0 && slot2!=slot0 && slot2!=slot1);
    assert(spu.voice[slot2].gain_left>0.f);
    assert(spu.voice[slot2].gain_right>0.f);
    assert(spu.voice[slot0].gain_left==held_left &&
           spu.voice[slot0].gain_right==0.f);
    vh_native_seq_stop(&seq);
    assert(!seq.playing && seq.note_offs==3u);
    assert(seq.last_error==0);
}

/* A clean FF2F seam rewinds the event reader, not the musical
 * channel state: PC-port SeqEndOfTrack retains tempo, chProg, CC7,
 * CC10 and held voices, and resets running status and tick budget.
 */
typedef struct {
    unsigned calls;
    unsigned program[8], note[8], volume[8], pan[8];
} LoopTrace;

static int resolve_loop_trace(void *ctx, unsigned program, unsigned note,
                              unsigned velocity, unsigned volume,
                              unsigned pan, VhSeqTone *out) {
    LoopTrace *trace=ctx;
    if (trace->calls >= 8u) return -1;
    const unsigned n=trace->calls++;
    trace->program[n]=program;
    trace->note[n]=note;
    trace->volume[n]=volume;
    trace->pan[n]=pan;
    return resolve_pan_sensitive(&log_state,program,note,velocity,
                                 volume,pan,out);
}

static void test_two_cycle_tempo_control_and_held_voice_seam(void) {
    static const uint8_t song[] = {
        HEADER,
        0,0x90,60,100,               /* first cycle uses p0 defaults */
        15,0xc0,9,                   /* p9 persists over clean FF2F */
        0,0xb0,7,40,                 /* channel volume 40 */
        0,0xb0,10,127,               /* hard right */
        0,0xff,0x51,0x03,0xd0,0x90, /* tempo 250000 */
        0,0x90,61,100,               /* held over the loop */
        30,0xff,0x2f                /* clean EOT at tick45 */
    };
    LoopTrace trace={0};
    setup();
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                              resolve_loop_trace,&trace,2)==0);
    for(unsigned block=1;block<=7u;++block) {
        assert(vh_native_seq_pump(&seq,&ring)==512);
        assert(vh_audio_stream_read(&ring,pcm,512)==512);
        assert(seq.blocks_advanced==block);
        assert(spu.frames_rendered==(uint64_t)block*512u);
        assert(vh_audio_stream_queued(&ring)==0);
        if(block==1u) {
            assert(trace.calls==1u && seq.note_ons==1u);
            assert(seq.tempo==500000u);
            assert(trace.program[0]==0u && trace.note[0]==60u);
            assert(trace.volume[0]==127u && trace.pan[0]==64u);
        }
        if(block==2u) {
            assert(trace.calls==2u && seq.note_ons==2u);
            assert(seq.tempo==250000u && seq.programs[0]==9u);
            assert(seq.volumes[0]==40u && seq.pans[0]==127u);
            assert(trace.program[1]==9u && trace.note[1]==61u);
            assert(trace.volume[1]==40u && trace.pan[1]==127u);
        }
        if(block==3u) {
            assert(trace.calls==2u && seq.cycles_completed==0u);
            assert(seq.playing);
        }
        if(block==4u) {
            /* EOT resets the tick accumulator; the zero-delta
             * first note of pass 2 immediately retriggers note60. */
            assert(seq.cycles_completed==1u && seq.playing);
            assert(seq.note_ons==3u && trace.calls==3u);
            assert(seq.tempo==250000u && seq.programs[0]==9u);
            assert(seq.volumes[0]==40u && seq.pans[0]==127u);
            assert(seq.pending_delta==15u);
            assert(seq.running==0x90u);
            assert(seq.tick_budget==0.0);
            assert(trace.program[2]==9u && trace.note[2]==60u);
            assert(trace.volume[2]==40u && trace.pan[2]==127u);
            assert(seq.note_slot[0][61]>=0);
        }
        if(block==5u) {
            assert(seq.note_ons==4u && trace.calls==4u);
            assert(trace.program[3]==9u && trace.note[3]==61u);
            assert(trace.volume[3]==40u && trace.pan[3]==127u);
            assert(seq.cycles_completed==1u);
        }
        if(block==6u) {
            assert(seq.playing && seq.cycles_completed==1u);
            assert(trace.calls==4u);
        }
        if(block==7u) {
            assert(!seq.playing && seq.cycles_completed==2u);
            assert(seq.note_ons==4u && seq.note_offs==4u);
            assert(seq.note_slot[0][60]==-1);
            assert(seq.note_slot[0][61]==-1);
            assert(seq.last_error==0);
        }
    }
}

static void test_infinite_clean_eot_soak_with_fifo_backpressure(void) {
    static const uint8_t song[] = {
        HEADER,
        0,0x90,64,100, 30,0xc0,7,
        0,0xb0,7,90, 0,0xb0,10,0,
        0,0xff,0x51,0x03,0xd0,0x90,
        0,0xff,0x2f
    };
    setup();
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                              resolve_pan_sensitive,&log_state,0)==0);
    int16_t zeros[VH_AUDIO_RING_FRAMES*2u]={0};
    for(unsigned block=0;block<160u;++block) {
        if(block==64u) {
            const uint64_t frames=spu.frames_rendered;
            const uint64_t events=seq.dispatched_events;
            const uint32_t cycles=seq.cycles_completed;
            assert(vh_audio_stream_write(&ring,zeros,VH_AUDIO_RING_FRAMES)
                   ==VH_AUDIO_RING_FRAMES);
            assert(vh_native_seq_pump(&seq,&ring)==0);
            assert(spu.frames_rendered==frames);
            assert(seq.dispatched_events==events);
            assert(seq.cycles_completed==cycles);
            vh_audio_stream_reset(&ring);
        }
        assert(vh_native_seq_pump(&seq,&ring)==512);
        assert(vh_audio_stream_read(&ring,pcm,512)==512);
        assert(seq.playing && seq.last_error==0);
        assert(seq.blocks_advanced==block+1u);
        assert(vh_audio_stream_queued(&ring)==0);
        assert(seq.note_ons>=seq.cycles_completed);
        if(seq.cycles_completed) {
            assert(seq.tempo==250000u);
            assert(seq.programs[0]==7u);
            assert(seq.volumes[0]==90u && seq.pans[0]==0u);
        }
    }
    assert(seq.cycles_completed>=25u);
    assert(seq.note_ons==seq.cycles_completed+1u);
    assert(spu.frames_rendered==160u*512u);
    const uint64_t note_on_before=seq.note_ons;
    vh_native_seq_stop(&seq);
    assert(!seq.playing);
    assert(seq.note_ons==note_on_before && seq.last_error==0);
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

static int resolve_with_missing(void *ctx, unsigned program,
                                unsigned note, unsigned velocity,
                                unsigned volume, unsigned pan,
                                VhSeqTone *out) {
    if (note==61u) return -1;
    return resolve(ctx,program,note,velocity,volume,pan,out);
}

/* Keep the target branch's read-only coverage audit AND the newly
 * backported scene-switch API working against the same native SEQ/SPU.
 * Invalid switches are fully atomic; valid ones detach every voice
 * from the old bank without clearing STUDIO_C's persistent wet tail.
 */
static int16_t next_scene_sample[64];
static VhNativeSpu before_scene_spu, foreign_scene_spu;
/* Independent post-switch oracle: an unmodified prior reverb snapshot
 * with manually cleared voices, not the scene-switch API under test. */
static VhNativeSpu oracle_scene_spu;
static VhNativeSeq oracle_scene_seq;
static int16_t oracle_scene_pcm[VH_AUDIO_BLOCK_FRAMES*2u];
/* The counterfactual renderer starts from the same SPU but with its
 * historical wet buffer reset, to establish an audible difference. */
static VhNativeSpu reset_tail_spu;
static VhNativeSeq reset_tail_seq;
static int16_t reset_tail_pcm[VH_AUDIO_BLOCK_FRAMES*2u];
static int resolve_scene_reverb(void *ctx,unsigned program,unsigned note,
                                unsigned velocity,unsigned volume,
                                unsigned pan,VhSeqTone *tone) {
    if(resolve(ctx,program,note,velocity,volume,pan,tone)) return -1;
    tone->reverb_send=1u;
    return 0;
}
static int resolve_next_scene(void *ctx,unsigned program,unsigned note,
                              unsigned velocity,unsigned volume,
                              unsigned pan,VhSeqTone *tone) {
    if(resolve_scene_reverb(ctx,program,note,velocity,volume,pan,tone))
        return -1;
    tone->pcm=next_scene_sample;
    return 0;
}
static void test_scene_switch_preserves_audit_and_wet_tail(void) {
    setup();
    for(unsigned i=0;i<64u;i++)
        next_scene_sample[i]=(int16_t)(-10000+(int)i*23);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve_scene_reverb,
                              &log_state,1u)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(spu.voice[0].pcm==sample && spu.voice[0].reverb_send);
    vh_native_spu_render(&spu,pcm,VH_AUDIO_BLOCK_FRAMES);
    const VhNativeSeq prior_seq=seq;
    before_scene_spu=spu;
    assert(spu.frames_rendered==VH_AUDIO_BLOCK_FRAMES);
    assert(vh_native_seq_switch_scene(
        &seq,invalid_data,sizeof invalid_data,&spu,
        resolve_next_scene,&log_state,1u)==-1);
    assert(!memcmp(&seq,&prior_seq,sizeof seq));
    assert(!memcmp(&spu,&before_scene_spu,sizeof spu));
    vh_native_spu_reset(&foreign_scene_spu);
    assert(vh_native_seq_switch_scene(
        &seq,controls_song,sizeof controls_song,&foreign_scene_spu,
        resolve_next_scene,&log_state,1u)==-1);
    assert(!memcmp(&seq,&prior_seq,sizeof seq));
    assert(!memcmp(&spu,&before_scene_spu,sizeof spu));

    VhSeqAudit audit={0};
    assert(vh_native_seq_audit(controls_song,sizeof controls_song,
                               resolve_next_scene,&log_state,&audit)==0);
    assert(audit.note_events==1u && audit.resolved_notes==1u &&
           audit.missing_notes==0u);
    assert(!memcmp(&seq,&prior_seq,sizeof seq));
    assert(!memcmp(&spu,&before_scene_spu,sizeof spu));

    assert(vh_native_seq_switch_scene(
        &seq,controls_song,sizeof controls_song,&spu,
        resolve_next_scene,&log_state,1u)==0);
    assert(seq.spu==&spu && seq.blocks_advanced==0u &&
           seq.note_ons==0u);
    assert(spu.frames_rendered==0u);
    assert(spu.reverb_enabled && spu.reverb_depth==0.5f);
    assert(!memcmp(&spu.reverb,&before_scene_spu.reverb,
                   sizeof spu.reverb));
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++)
        assert(!spu.voice[i].pcm && !spu.voice[i].active);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(spu.voice[0].pcm==next_scene_sample &&
           spu.voice[0].reverb_send);
    vh_native_spu_render(&spu,pcm,VH_AUDIO_BLOCK_FRAMES);
    assert(spu.frames_rendered==VH_AUDIO_BLOCK_FRAMES);
}

/* A music bank may change many times in one session. Prove every
 * transition detaches old PCM pointers while retaining the complete
 * wet-tail buffer, including when a read-only preflight is interleaved
 * with the live sequencer. */
static void test_repeated_scene_switch_preserves_wet_tail(void) {
    setup();
    for(unsigned i=0;i<64u;i++)
        next_scene_sample[i]=(int16_t)(-11000+(int)i*29);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    assert(vh_native_seq_init(&seq,controls_song,sizeof controls_song,
                              &spu,resolve_scene_reverb,
                              &log_state,1u)==0);
    for(unsigned iteration=0;iteration<32u;iteration++) {
        const VhSeqResolve incoming=(iteration%2u)
            ? resolve_scene_reverb : resolve_next_scene;
        const int16_t *expected=(iteration%2u)
            ? sample : next_scene_sample;
        VhSeqAudit report={0};
        const VhNativeSeq live_seq=seq;
        before_scene_spu=spu;
        assert(vh_native_seq_audit(controls_song,sizeof controls_song,
                                   incoming,&log_state,&report)==0);
        assert(report.note_events==1u && report.resolved_notes==1u &&
               report.missing_notes==0u);
        assert(!memcmp(&seq,&live_seq,sizeof seq));
        assert(!memcmp(&spu,&before_scene_spu,sizeof spu));
        assert(vh_native_seq_switch_scene(
            &seq,invalid_data,sizeof invalid_data,&spu,
            incoming,&log_state,1u)==-1);
        assert(!memcmp(&seq,&live_seq,sizeof seq));
        assert(!memcmp(&spu,&before_scene_spu,sizeof spu));

        assert(vh_native_seq_switch_scene(
            &seq,controls_song,sizeof controls_song,&spu,
            incoming,&log_state,1u)==0);
        assert(seq.spu==&spu && seq.blocks_advanced==0u &&
               seq.note_ons==0u && seq.note_offs==0u);
        assert(spu.frames_rendered==0u);
        assert(spu.reverb_enabled && spu.reverb_depth==0.5f);
        assert(!memcmp(&spu.reverb,&before_scene_spu.reverb,
                       sizeof spu.reverb));
        for(unsigned voice=0;voice<VH_NATIVE_MUSIC_VOICES;voice++)
            assert(!spu.voice[voice].pcm &&
                   !spu.voice[voice].active);
        assert(vh_native_seq_advance_block(&seq)>0);
        assert(seq.note_ons==1u && seq.blocks_advanced==1u);
        assert(spu.voice[0].pcm==expected &&
               spu.voice[0].reverb_send);
        vh_native_spu_render(&spu,pcm,VH_AUDIO_BLOCK_FRAMES);
        assert(spu.frames_rendered==VH_AUDIO_BLOCK_FRAMES);
    }
}

static void test_full_twenty_voice_scene_switch_detaches_bank(void) {
    setup();
    for(unsigned i=0;i<64u;i++)
        next_scene_sample[i]=(int16_t)(-7000+(int)i*17);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    assert(vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN)==0);
    VhSeqAudit full_audit={0};
    assert(vh_native_seq_audit(
        full_voice_scene_song,sizeof full_voice_scene_song,
        resolve_scene_reverb,&log_state,&full_audit)==0);
    assert(full_audit.note_events==VH_NATIVE_MUSIC_VOICES &&
           full_audit.resolved_notes==VH_NATIVE_MUSIC_VOICES &&
           full_audit.missing_notes==0u);
    assert(vh_native_seq_init(
        &seq,full_voice_scene_song,sizeof full_voice_scene_song,
        &spu,resolve_scene_reverb,&log_state,1u)==0);
    assert(vh_native_seq_advance_block(&seq)>0);
    assert(seq.note_ons==VH_NATIVE_MUSIC_VOICES);
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++)
        assert(spu.voice[i].active && spu.voice[i].pcm==sample &&
               spu.voice[i].reverb_send);
    /* Charge the genuine STUDIO_C delay/FIR history before changing
     * banks. An empty history would make the wet-tail comparison
     * trivially pass even if switching accidentally reset reverb. */
    for(unsigned warm=0u;warm<64u;warm++) {
        if(warm) assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,pcm,VH_AUDIO_BLOCK_FRAMES);
    }
    assert(seq.note_ons==VH_NATIVE_MUSIC_VOICES &&
           spu.frames_rendered==64u*VH_AUDIO_BLOCK_FRAMES);
    unsigned nonzero_wet_cells=0u;
    for(unsigned i=0;i<VH_REV_SAMPLES;i++)
        nonzero_wet_cells+=(spu.reverb.work[i]!=0);
    assert(nonzero_wet_cells>0u);
    const VhNativeSeq saved=seq;
    before_scene_spu=spu;
    const uint8_t *bad_songs[]={
        invalid_status,invalid_tempo,invalid_vlq,invalid_data,
        late_invalid_scene_song
    };
    const size_t bad_sizes[]={
        sizeof invalid_status,sizeof invalid_tempo,
        sizeof invalid_vlq,sizeof invalid_data,
        sizeof late_invalid_scene_song
    };
    for(unsigned bad=0u;bad<5u;bad++) {
        assert(vh_native_seq_switch_scene(
            &seq,bad_songs[bad],bad_sizes[bad],&spu,
            resolve_next_scene,&log_state,1u)==-1);
        assert(!memcmp(&seq,&saved,sizeof saved));
        assert(!memcmp(&spu,&before_scene_spu,sizeof spu));
    }
    assert(vh_native_seq_switch_scene(
        &seq,controls_song,sizeof controls_song,&spu,
        resolve_next_scene,&log_state,VH_SEQ_MAX_REPEATS+1u)==-1);
    /* An infinitely repeated zero-length track is invalid; rejecting
     * it must not change even a fully occupied live SPU. */
    assert(vh_native_seq_switch_scene(
        &seq,zero_loop,sizeof zero_loop,&spu,
        resolve_next_scene,&log_state,0u)==-1);
    assert(vh_native_seq_switch_scene(
        &seq,controls_song,sizeof controls_song,&spu,
        NULL,&log_state,1u)==-1);
    assert(vh_native_seq_switch_scene(
        &seq,NULL,sizeof controls_song,&spu,
        resolve_next_scene,&log_state,1u)==-1);
    assert(!memcmp(&seq,&saved,sizeof saved));
    assert(!memcmp(&spu,&before_scene_spu,sizeof spu));

    assert(vh_native_seq_switch_scene(
        &seq,controls_song,sizeof controls_song,&spu,
        resolve_next_scene,&log_state,1u)==0);
    assert(seq.note_ons==0u && seq.note_offs==0u &&
           seq.blocks_advanced==0u);
    assert(spu.frames_rendered==0u);
    assert(spu.reverb_enabled && spu.reverb_depth==0.5f &&
           spu.interpolation==VH_SPU_GAUSSIAN);
    assert(!memcmp(&spu.reverb,&before_scene_spu.reverb,
                   sizeof spu.reverb));
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++)
        assert(!spu.voice[i].active && !spu.voice[i].pcm);
    /* Build the oracle DIRECTLY from the old, fully populated SPU.
     * Do not use clear_voices_keep_reverb or switch_scene: this
     * independently preserves the wet tail but releases old voices.
     * Compare 48 mixed blocks, including the post-EOT decay interval,
     * so equal pointer bookkeeping alone cannot prove PCM continuity. */
    oracle_scene_spu=before_scene_spu;
    memset(oracle_scene_spu.voice,0,sizeof oracle_scene_spu.voice);
    oracle_scene_spu.steal_index=0u;
    oracle_scene_spu.frames_rendered=0u;
    assert(vh_native_seq_init(
        &oracle_scene_seq,controls_song,sizeof controls_song,
        &oracle_scene_spu,resolve_next_scene,&log_state,1u)==0);
    reset_tail_spu=oracle_scene_spu;
    vh_spu_reverb_reset(&reset_tail_spu.reverb);
    assert(vh_native_seq_init(
        &reset_tail_seq,controls_song,sizeof controls_song,
        &reset_tail_spu,resolve_next_scene,&log_state,1u)==0);
    unsigned audible_blocks=0u, wet_tail_effect_blocks=0u;
    for(unsigned block=0u;block<48u;block++) {
        const int actual=vh_native_seq_advance_block(&seq);
        const int expected=vh_native_seq_advance_block(&oracle_scene_seq);
        const int empty_wet=vh_native_seq_advance_block(&reset_tail_seq);
        assert(actual>=0 && actual==expected && actual==empty_wet);
        assert(seq.note_ons==oracle_scene_seq.note_ons &&
               seq.note_offs==oracle_scene_seq.note_offs &&
               seq.blocks_advanced==oracle_scene_seq.blocks_advanced);
        vh_native_spu_render(&spu,pcm,VH_AUDIO_BLOCK_FRAMES);
        vh_native_spu_render(
            &oracle_scene_spu,oracle_scene_pcm,VH_AUDIO_BLOCK_FRAMES);
        vh_native_spu_render(
            &reset_tail_spu,reset_tail_pcm,VH_AUDIO_BLOCK_FRAMES);
        assert(!memcmp(pcm,oracle_scene_pcm,sizeof pcm));
        if(memcmp(pcm,reset_tail_pcm,sizeof pcm)!=0)
            ++wet_tail_effect_blocks;
        assert(!memcmp(&spu.reverb,&oracle_scene_spu.reverb,
                       sizeof spu.reverb));
        for(unsigned i=0u;i<VH_AUDIO_BLOCK_FRAMES*2u;i++)
            if(pcm[i]!=0) { ++audible_blocks; break; }
    }
    assert(audible_blocks>0u && wet_tail_effect_blocks>0u &&
           seq.note_ons==1u && seq.cycles_completed==1u &&
           spu.frames_rendered==48u*VH_AUDIO_BLOCK_FRAMES);
}

/* The music producer can switch scenes only after the caller has
 * accounted for output pages already prepared from the previous bank.
 * A copied PCM FIFO page must not change when the live SEQ detaches
 * old VAB sample pointers. Its consumer drains it exactly once. */
static void test_pending_pcm_fifo_unchanged_by_scene_switch(void) {
    setup();
    for(unsigned i=0u;i<64u;i++)
        next_scene_sample[i]=(int16_t)(-12000+(int)i*19);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    assert(vh_native_seq_init(
        &seq,controls_song,sizeof controls_song,&spu,
        resolve_scene_reverb,&log_state,1u)==0);
    assert(vh_native_seq_pump(&seq,&ring)==VH_AUDIO_BLOCK_FRAMES);
    assert(vh_audio_stream_queued(&ring)==VH_AUDIO_BLOCK_FRAMES &&
           seq.blocks_advanced==1u && spu.frames_rendered==512u);
    assert(spu.voice[0].pcm==sample && spu.voice[0].active);
    const VhAudioStream pending_pcm=ring;
    const VhNativeSeq pending_seq=seq;
    before_scene_spu=spu;
    assert(vh_native_seq_switch_scene(
        &seq,invalid_data,sizeof invalid_data,&spu,
        resolve_next_scene,&log_state,1u)==-1);
    assert(!memcmp(&seq,&pending_seq,sizeof seq));
    assert(!memcmp(&spu,&before_scene_spu,sizeof spu));
    assert(!memcmp(&ring,&pending_pcm,sizeof ring));

    /* The new bank takes over the producer, not bytes already owned
     * by the FIFO consumer. Keep wet history but release old voices. */
    assert(vh_native_seq_switch_scene(
        &seq,controls_song,sizeof controls_song,&spu,
        resolve_next_scene,&log_state,1u)==0);
    assert(!memcmp(&ring,&pending_pcm,sizeof ring));
    assert(!memcmp(&spu.reverb,&before_scene_spu.reverb,
                   sizeof spu.reverb));
    for(unsigned i=0u;i<VH_NATIVE_MUSIC_VOICES;i++)
        assert(!spu.voice[i].pcm && !spu.voice[i].active);
    assert(vh_audio_stream_read(&ring,pcm,VH_AUDIO_BLOCK_FRAMES)
           ==VH_AUDIO_BLOCK_FRAMES);
    assert(!memcmp(pcm,pending_pcm.pcm,sizeof pcm));
    assert(vh_audio_stream_queued(&ring)==0u &&
           ring.underrun_frames==0u && ring.overrun_frames==0u);
    assert(vh_native_seq_pump(&seq,&ring)==VH_AUDIO_BLOCK_FRAMES);
    assert(seq.note_ons==1u &&
           spu.voice[0].pcm==next_scene_sample &&
           vh_audio_stream_queued(&ring)==VH_AUDIO_BLOCK_FRAMES);
    assert(ring.underrun_frames==0u && ring.overrun_frames==0u);
}

static void test_preflight_instrument_coverage(void) {
    setup();
    VhSeqAudit info={0};
    assert(vh_native_seq_audit(controls_song,sizeof controls_song,
                               resolve,&log_state,&info)==0);
    assert(info.note_events==1u && info.resolved_notes==1u);
    assert(info.missing_notes==0u && !info.has_missing);
    assert(info.program_changes==1u && info.tempo_changes==0u);
    assert(log_state.calls==1 && log_state.program==7u);
    assert(log_state.volume==80u && log_state.pan==0u);
    assert(spu.frames_rendered==0 && !spu.voice[0].active);

    memset(&log_state,0,sizeof log_state);
    assert(vh_native_seq_audit(running_song,sizeof running_song,
                  resolve_with_missing,&log_state,&info)==0);
    assert(info.note_events==2u && info.resolved_notes==1u);
    assert(info.missing_notes==1u && info.has_missing);
    assert(info.first_missing_program==0u);
    assert(info.first_missing_channel==0u);
    assert(info.first_missing_note==61u);
    assert(info.tempo_changes==1u);

    VhSeqAudit before=info;
    assert(vh_native_seq_audit(invalid_data,sizeof invalid_data,
                               resolve,&log_state,&info)==-1);
    assert(!memcmp(&info,&before,sizeof info));
    assert(vh_native_seq_audit(NULL,sizeof controls_song,
                               resolve,&log_state,&info)==-1);
    assert(vh_native_seq_audit(controls_song,sizeof controls_song,
                               NULL,&log_state,&info)==-1);
}

int main(void) {
    test_validation_and_source_immutability();
    test_512_block_controls_and_ring_pressure();
    test_running_tempo_and_repeat_seam();
    test_sustained_voices_across_tempo_pan_and_backpressure();
    test_two_cycle_tempo_control_and_held_voice_seam();
    test_infinite_clean_eot_soak_with_fifo_backpressure();
    test_voice_stealing_stale_note_off();
    test_512_pcm_event_to_spu_fifo();
    test_preflight_instrument_coverage();
    test_scene_switch_preserves_audit_and_wet_tail();
    test_repeated_scene_switch_preserves_wet_tail();
    test_full_twenty_voice_scene_switch_detaches_bank();
    test_pending_pcm_fifo_unchanged_by_scene_switch();
    puts("native pQES SEQ -> 20-voice SPU -> PCM ring: PASS");
    return 0;
}
