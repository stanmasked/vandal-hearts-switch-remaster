/* Synthetic tests for 20-slot dry native SPU block-to-ring pipeline. */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_native_spu.h"
#include "vh_spu_adpcm.h"

static VhNativeSpu synth;
static VhAudioStream ring;
static int16_t out[512 * 2u];
static int16_t samples[100];

static void test_adpcm_into_native_mixer(void) {
    uint8_t vag[32] = {0};
    vag[0] = 0x02; vag[1] = 0x04;
    vag[16] = 0x02; vag[17] = 0x03;
    for (unsigned i = 2; i < 16; ++i) vag[i] = 0x22;
    for (unsigned i = 18; i < 32; ++i) vag[i] = 0xee;
    int16_t pcm[56];
    VhSpuAdpcmInfo meta;
    assert(vh_spu_adpcm_decode(vag, sizeof(vag), pcm, 56, &meta) == 0);
    assert(meta.loop_start_frame == 0 && meta.loop_end_frame == 56);
    assert(pcm[0] == 2048 && pcm[27] == 2048);
    assert(pcm[28] == -2048 && pcm[55] == -2048);

    vh_native_spu_reset(&synth);
    vh_audio_stream_reset(&ring);
    assert(vh_native_spu_allocate_slot(&synth) == 0);
    assert(vh_native_spu_note_on(&synth, 0, pcm, 56,
                                 meta.loop_start_frame, meta.loop_end_frame,
                                 4096, 15, 0, 1.0f, 0.5f) == 0);
    assert(vh_native_spu_pump(&synth, &ring, 128) == 128);
    assert(synth.frames_rendered == 128);
    assert(vh_audio_stream_queued(&ring) == 128);
    assert(vh_audio_stream_read(&ring, out, 128) == 128);
    assert(out[0] == 896 && out[1] == 448);
    assert(out[2] == 1792 && out[3] == 896);
    assert(out[4] == 2048 && out[5] == 1024);
    assert(out[56 * 2] == 2048); /* loop begins again */
    assert(out[28 * 2] == -2048);
    assert(out[84 * 2] == -2048);
    assert(vh_native_spu_voice_active(&synth, 0));
}

static void test_envelope_release_and_free_slot(void) {
    for (unsigned i = 0; i < 100; ++i) samples[i] = 10000;
    vh_native_spu_reset(&synth);
    assert(vh_native_spu_note_on(&synth, 0, samples, 100,
                                 0, 100, 0x1000, 15, 0, 1, 0) == 0);
    vh_native_spu_render(&synth, out, 5);
    assert(out[0] == 4375 && out[1] == 0);
    assert(out[2] == 8750 && out[3] == 0);
    assert(out[4] == 10000);
    vh_native_spu_note_off(&synth, 0);
    vh_native_spu_render(&synth, out, 2);
    assert(out[0] == 4999 && out[1] == 0);
    assert(out[2] == 0);
    assert(!vh_native_spu_voice_active(&synth, 0));
    assert(vh_native_spu_allocate_slot(&synth) == 0);
}

static void test_pitch_one_shot_and_polyphony(void) {
    int16_t source[] = {1000, 2000, 3000, 4000};
    vh_native_spu_reset(&synth);
    assert(vh_native_spu_note_on(&synth, 0, source, 4,
                                 -1, -1, 0x800, 15, 0, 1, 0) == 0);
    assert(vh_native_spu_note_on(&synth, 1, source, 4,
                                 -1, -1, 0x1000, 15, 0, 0, 1) == 0);
    vh_native_spu_render(&synth, out, 8);
    assert(out[0] == 437 && out[1] == 437);
    assert(out[2] == 875 && out[3] == 1750);
    assert(out[4] == 2000 && out[5] == 3000);
    assert(out[6] == 2000 && out[7] == 4000);
    assert(out[8 + 1] == 0); /* one-shot right voice already ended */
    assert(!vh_native_spu_voice_active(&synth, 1));
    assert(!vh_native_spu_voice_active(&synth, 0));
}

static void test_gaussian_integer_voice_and_loop_history(void) {
    const int16_t pcm[] = {4000, 8000, 12000, 16000,
                           20000, 24000, 28000};
    const int16_t expected[] = {
        0, 518, 3991, 7974, 11959, 15944, 18144, 13719, 15944
    };
    vh_native_spu_reset(&synth);
    assert(synth.interpolation == VH_SPU_NEAREST);
    assert(vh_native_spu_set_interpolation(&synth, VH_SPU_GAUSSIAN) == 0);
    assert(vh_native_spu_set_interpolation(&synth, 2u) == -1);
    assert(synth.interpolation == VH_SPU_GAUSSIAN);
    assert(vh_native_spu_note_on(&synth, 0, pcm, 7,
                                 2, 5, 0x1000, 15, 0, 1, 0) == 0);
    vh_native_spu_render(&synth, out, 9);
    for (unsigned i = 0; i < 9; ++i) {
        assert(out[2u * i] == expected[i]);
        assert(out[2u * i + 1u] == 0);
    }
    assert(synth.voice[0].looped);
    assert(vh_native_spu_voice_active(&synth, 0));
    assert(vh_native_spu_set_interpolation(&synth, VH_SPU_NEAREST) == 0);
    assert(vh_native_spu_set_interpolation(NULL, VH_SPU_GAUSSIAN) == -1);
}

static void test_20_voice_round_robin(void) {
    vh_native_spu_reset(&synth);
    for (unsigned i = 0; i < VH_NATIVE_MUSIC_VOICES; ++i) {
        assert(vh_native_spu_allocate_slot(&synth) == (int)i);
        assert(vh_native_spu_note_on(&synth, i, samples, 100,
                                     0, 100, 4096, 15, 0, 0.5f, 0.5f) == 0);
    }
    assert(vh_native_spu_allocate_slot(&synth) == 0);
    assert(vh_native_spu_allocate_slot(&synth) == 1);
    assert(vh_native_spu_allocate_slot(&synth) == 2);
    vh_native_spu_note_off(&synth, 3);
    vh_native_spu_render(&synth, out, 2);
    assert(vh_native_spu_allocate_slot(&synth) == 3);
}

static void test_rejected_params_and_ring_backpressure(void) {
    vh_native_spu_reset(&synth);
    vh_audio_stream_reset(&ring);
    assert(vh_native_spu_note_on(&synth, 20, samples, 100,
                                 0, 100, 4096, 15, 0, 1, 1) == -1);
    assert(vh_native_spu_note_on(&synth, 0, samples, 100,
                                 50, 101, 4096, 15, 0, 1, 1) == -1);
    assert(vh_native_spu_note_on(&synth, 0, samples, 100,
                                 0, 100, 4096, 15, 0, NAN, 1) == -1);
    assert(vh_native_spu_note_on(&synth, 0, samples, 100,
                                 -1, -1, 4096, 15, 0, 1, 1) == 0);
    assert(vh_native_spu_pump(&synth, &ring, 513) == 0);
    assert(synth.frames_rendered == 0);
    int16_t silence[VH_AUDIO_RING_FRAMES * 2u] = {0};
    assert(vh_audio_stream_write(&ring, silence, VH_AUDIO_RING_FRAMES) ==
           VH_AUDIO_RING_FRAMES);
    assert(vh_native_spu_pump(&synth, &ring, 512) == 0);
    assert(synth.frames_rendered == 0); /* cannot lose DSP time on full FIFO */
    assert(vh_audio_stream_read(&ring, out, 512) == 512);
    assert(vh_native_spu_pump(&synth, &ring, 512) == 512);
    assert(synth.frames_rendered == 512);
}

int main(void) {
    test_adpcm_into_native_mixer();
    test_envelope_release_and_free_slot();
    test_pitch_one_shot_and_polyphony();
    test_gaussian_integer_voice_and_loop_history();
    test_20_voice_round_robin();
    test_rejected_params_and_ring_backpressure();
    puts("native SPU decoder -> 20 voices -> PCM ring: PASS (synthetic)");
    return 0;
}
