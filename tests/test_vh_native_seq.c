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

static int resolve_with_missing(void *ctx, unsigned program,
                                unsigned note, unsigned velocity,
                                unsigned volume, unsigned pan,
                                VhSeqTone *out) {
    if (note==61u) return -1;
    return resolve(ctx,program,note,velocity,volume,pan,out);
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
    test_voice_stealing_stale_note_off();
    test_512_pcm_event_to_spu_fifo();
    test_preflight_instrument_coverage();
    puts("native pQES SEQ -> 20-voice SPU -> PCM ring: PASS");
    return 0;
}
