/* Portable suspend/resume policy regression for the tactical music
 * owner thread. Models libnx audout gating without Switch services.
 * Only fully synthetic sequence and PCM data are involved.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_game_music_mailbox.h"
#include "vh_music_scene.h"
#include "vh_audio_resample.h"

#define SEQ_HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0
static const uint8_t field_seq[] = {
    SEQ_HDR,0,0xc0,7,0,0x90,60,110,
    0x81,0x70,0x80,60,0,0x81,0x70,0xff,0x2f
};
static const uint8_t selected_seq[] = {
    SEQ_HDR,0,0xc0,7,0,0x90,67,110,
    0x81,0x70,0x80,67,0,0x81,0x70,0xff,0x2f
};
static int16_t sample[128], pcm[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
static VhGameMusicMailbox inbox;
static VhNativeSpu spu;
static VhMusicScene music;
static VhAudioResample converter;
static uint64_t output_frames;
static unsigned accepted_scene;

static int resolve(void *ctx, unsigned program, unsigned note,
                   unsigned velocity, unsigned volume, unsigned pan,
                   VhSeqTone *tone) {
    (void)ctx; (void)velocity; (void)volume; (void)pan;
    if (!tone || program != 7 || (note != 60 && note != 67))
        return -1;
    memset(tone,0,sizeof *tone);
    tone->pcm=sample;
    tone->frames=128;
    tone->loop_start=0; tone->loop_end=128;
    tone->pitch_step=note==60?4096u:6144u;
    tone->adsr1=15;
    tone->gain_left=0.42f;
    tone->gain_right=0.35f;
    tone->reverb_send=1;
    return 0;
}

static const VhMusicCue field_cue = {
    VH_GAME_MUSIC_FIELD,field_seq,sizeof field_seq,0,resolve,NULL
};
static const VhMusicCue selected_cue = {
    VH_GAME_MUSIC_HERO_SELECTED,selected_seq,
    sizeof selected_seq,0,resolve,NULL
};

/* One independent "audio thread" turn. While focus is lost, it does
 * nothing whatsoever to scene/SPU/clock/resampler state.
 */
static void audio_turn(void) {
    if (!vh_game_music_mailbox_running(&inbox) ||
        !vh_game_music_mailbox_focused(&inbox))
        return;
    const unsigned desired=vh_game_music_mailbox_read(&inbox);
    if (desired!=accepted_scene) {
        const VhMusicCue *cue=desired==VH_GAME_MUSIC_FIELD
            ? &field_cue
            : desired==VH_GAME_MUSIC_HERO_SELECTED ? &selected_cue : NULL;
        const int rc=vh_music_scene_request(
            &music,cue,accepted_scene ? 8u : 0u);
        assert(rc==0 || rc==-2);
        if (rc==0) accepted_scene=desired;
    }
    assert(vh_music_scene_render(&music,pcm)==0);
    const size_t count=vh_audio_resample_process(
        &converter,pcm,VH_AUDIO_BLOCK_FRAMES,
        output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
    assert(count>=555u && count<=559u);
    output_frames+=count;
    assert(converter.input_frames == music.blocks_rendered*512u);
}

static void test_pause_and_resume_with_last_scene(void) {
    for (unsigned i=0;i<128u;i++)
        sample[i]=(int16_t)((int)i*140-8500);
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    vh_music_scene_init(&music,&spu);
    vh_audio_resample_reset(&converter);
    vh_game_music_mailbox_init(&inbox,VH_GAME_MUSIC_FIELD);
    for(unsigned i=0;i<16;i++) audio_turn();
    assert(music.active.id==VH_GAME_MUSIC_FIELD && music.switches==1);
    assert(music.seq.note_ons>0u);

    const uint64_t clock_before = converter.input_frames;
    const uint64_t out_before = output_frames;
    const uint64_t spu_before = spu.frames_rendered;
    const uint64_t blocks_before=music.blocks_rendered;
    const unsigned seq_before=music.seq.blocks_advanced;
    const int reverb_before=spu.reverb.cursor;
    vh_game_music_mailbox_set_focus(&inbox,0);
    for(unsigned i=0;i<3000;i++) {
        vh_game_music_mailbox_post(
            &inbox,(i&1u)
                ? VH_GAME_MUSIC_HERO_SELECTED : VH_GAME_MUSIC_FIELD);
        audio_turn();
    }
    vh_game_music_mailbox_post(
        &inbox,VH_GAME_MUSIC_HERO_SELECTED);
    assert(converter.input_frames==clock_before);
    assert(output_frames==out_before);
    assert(spu.frames_rendered==spu_before);
    assert(music.blocks_rendered==blocks_before);
    assert(music.seq.blocks_advanced==seq_before);
    assert(spu.reverb.cursor==reverb_before);
    assert(music.active.id==VH_GAME_MUSIC_FIELD);
    assert(vh_game_music_mailbox_read(&inbox)==
           VH_GAME_MUSIC_HERO_SELECTED);

    assert(vh_game_music_mailbox_resume_serial(&inbox)==0u);
    vh_game_music_mailbox_on_resume(&inbox,1);
    assert(vh_game_music_mailbox_resume_serial(&inbox)==1u);
    for(unsigned i=0;i<20;i++) audio_turn();
    assert(music.active.id==VH_GAME_MUSIC_HERO_SELECTED);
    assert(music.switches==2);
    assert(music.stage==VH_MUSIC_PLAYING);
    assert(music.blocks_rendered==blocks_before+20u);
    assert(converter.input_frames==clock_before+20u*512u);
    assert(output_frames>out_before);
    assert(spu.interpolation==VH_SPU_GAUSSIAN);
    assert(spu.reverb_enabled);

    /* A second focus loss does not restart the selected cue. */
    vh_game_music_mailbox_set_focus(&inbox,0);
    const uint64_t later=music.blocks_rendered;
    for(unsigned i=0;i<128u;i++) audio_turn();
    assert(music.blocks_rendered==later);
    vh_game_music_mailbox_on_resume(&inbox,1);
    assert(vh_game_music_mailbox_resume_serial(&inbox)==2u);
    audio_turn();
    assert(music.blocks_rendered==later+1);
    assert(music.switches==2);

    vh_game_music_mailbox_stop(&inbox);
    audio_turn();
    assert(music.blocks_rendered==later+1);
}

int main(void) {
    test_pause_and_resume_with_last_scene();
    puts("focus loss/resume: SEQ SPU reverb 44k/48k clocks preserved PASS");
    return 0;
}
