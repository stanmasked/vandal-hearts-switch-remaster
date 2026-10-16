/* Long-running native music pipeline smoke: synthetic SEQ->SPU+STUDIO_C
 * -> 44100/48000 resampler, no original game data or console services.
 * Verifies no accumulated phase drift, frozen tail or voice ownership leak.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_native_seq.h"
#include "vh_audio_resample.h"

#define SOAK_BLOCKS 2048u
static VhNativeSeq seq;
static VhNativeSpu spu;
static VhAudioResample resample;
static int16_t sample[112];
static int16_t source[VH_AUDIO_BLOCK_FRAMES * 2u];
static int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES * 2u];
static const uint8_t song[] = {
    'p','Q','E','S',0,0,0,0,0x01,0xe0,0x07,0xa1,0x20,0,0,
    0,0xc0,7,0,0xb0,10,64,
    0,0x90,60,100,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f,
};
static unsigned resolved;

static int lookup(void *ctx, unsigned program, unsigned note,
                  unsigned velocity, unsigned volume, unsigned pan,
                  VhSeqTone *tone) {
    (void)ctx;
    if (program != 7 || note != 60 || !velocity ||
        volume > 127 || pan > 127) return -1;
    memset(tone,0,sizeof *tone);
    tone->pcm = sample;
    tone->frames = 112;
    tone->loop_start = 0;
    tone->loop_end = 112;
    tone->pitch_step = 4096;
    tone->adsr1 = 15;
    tone->adsr2 = 0;
    tone->gain_left = 0.72f;
    tone->gain_right = 0.4f;
    tone->reverb_send = 1;
    ++resolved;
    return 0;
}

int main(void) {
    for (unsigned i=0;i<112;i++)
        sample[i] = (int16_t)((int)(i*431)%24000-12000);
    vh_native_spu_reset(&spu);
    vh_audio_resample_reset(&resample);
    assert(vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,lookup,NULL,0)==0);

    uint64_t output_frames=0;
    uint64_t checksum=UINT64_C(1469598103934665603);
    uint64_t nonzero=0;
    for(unsigned block=0;block<SOAK_BLOCKS;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,source,VH_AUDIO_BLOCK_FRAMES);
        const size_t n = vh_audio_resample_process(
            &resample,source,VH_AUDIO_BLOCK_FRAMES,
            output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(n>=555 && n<=559);
        output_frames+=n;
        for(size_t i=0;i<2u*n;i++) {
            checksum ^= (uint16_t)output[i];
            checksum *= UINT64_C(1099511628211);
            if(output[i]) ++nonzero;
        }
        assert(spu.frames_rendered == (uint64_t)(block+1)*512u);
        assert(resample.input_frames == spu.frames_rendered);
        assert(seq.blocks_advanced == block+1);
        assert(seq.playing && !seq.last_error);
        assert(spu.reverb.cursor == (int)((spu.frames_rendered/2u) % VH_REV_SAMPLES));
    }
    const uint64_t in_frames=(uint64_t)SOAK_BLOCKS*512u;
    const uint64_t expected=(in_frames-1u)*160u/147u+1u;
    assert(output_frames>=expected-2u && output_frames<=expected+2u);
    assert(nonzero>100000);
    assert(seq.cycles_completed>=10);
    assert(resolved==seq.note_ons);
    assert(seq.note_ons > 20 && seq.note_ons < 100);
    assert(seq.note_offs > 20);
    assert(checksum != UINT64_C(1469598103934665603));
    printf("SEQ+STUDIO_C+48k soak: PASS %u blocks, %llu PCM frames, %u loops, checksum=%016llx\n",
           SOAK_BLOCKS,(unsigned long long)output_frames,seq.cycles_completed,
           (unsigned long long)checksum);
    return 0;
}
