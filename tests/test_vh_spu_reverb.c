/* Deterministic STUDIO_C reverb network regression (synthetic PCM only). */
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_spu_reverb.h"
#include "vh_native_spu.h"

static VhSpuReverb a, b;
static VhNativeSpu synth;
static int16_t pcm[256];
static int16_t output[512*2];

static void test_studio_c_disabled_and_tail(void) {
    vh_spu_reverb_reset(&a);
    int wl = -1, wr = -1;
    assert(a.phase == 0 && a.cursor == 0);
    assert(sizeof(a.work)/sizeof(a.work[0]) == VH_REV_SAMPLES);
    vh_spu_reverb_process(NULL, 2000, 2000, 0.5f, &wl, &wr);
    assert(wl==0 && wr==0);
    vh_spu_reverb_process(&a, 2000, 2000, NAN, &wl, &wr);
    assert(wl==0 && wr==0 && a.cursor==0);

    uint64_t tail_energy = 0;
    uint64_t active_energy = 0;
    for (int i=0;i<48000;i++) {
        /* 4000 nonzero input frames, then exactly zero. A reverb tail
         * must continue after the input has stopped.
         */
        const int left = i<4000 ? 14000 : 0;
        const int right = i<4000 ? -9000 : 0;
        vh_spu_reverb_process(&a,left,right,0.75f,&wl,&wr);
        if (i<4000) active_energy += (uint64_t)(abs(wl)+abs(wr));
        if (i>=4000) tail_energy += (uint64_t)(abs(wl)+abs(wr));
        assert(wl>=INT16_MIN && wl<=INT16_MAX);
        assert(wr>=INT16_MIN && wr<=INT16_MAX);
    }
    assert(active_energy>0);
    assert(tail_energy>0);
    vh_spu_reverb_reset(&a);
    assert(a.phase==0 && a.cursor==0);
    for (unsigned i=0;i<VH_REV_SAMPLES;i++) assert(a.work[i]==0);
}

static void test_deterministic_state_vs_independent_context(void) {
    vh_spu_reverb_reset(&a);
    vh_spu_reverb_reset(&b);
    for (int i=0;i<16000;i++) {
        int l=(i%71)*120-4000;
        int r=(i%53)*210-5000;
        int al,ar,bl,br;
        vh_spu_reverb_process(&a,l,r,1.f,&al,&ar);
        vh_spu_reverb_process(&b,l,r,1.f,&bl,&br);
        assert(al==bl && ar==br);
    }
    assert(!memcmp(&a,&b,sizeof a));
}

static void test_dry_compatibility_and_mode_bit(void) {
    for(unsigned i=0;i<256;i++) pcm[i]=i%2 ? 15000 : -9000;
    vh_native_spu_reset(&synth);
    assert(!synth.reverb_enabled);
    assert(vh_native_spu_set_reverb(&synth,1,1.5f)==-1);
    assert(vh_native_spu_set_reverb(&synth,1,NAN)==-1);
    assert(vh_native_spu_set_voice_reverb(&synth,20,1)==-1);
    assert(vh_native_spu_set_reverb(&synth,1,0.75f)==0);
    assert(vh_native_spu_note_on(&synth,0,pcm,256,0,256,
                                  4096,15,0,0.7f,0.7f)==0);
    assert(vh_native_spu_set_voice_reverb(&synth,0,1)==0);
    assert(synth.voice[0].reverb_send);
    vh_native_spu_render(&synth,output,512);
    assert(synth.frames_rendered==512);
    assert(synth.reverb.cursor==256);
    vh_native_spu_note_off(&synth,0);
    vh_native_spu_render(&synth,output,512);
    assert(synth.reverb.cursor==512);
    assert(vh_native_spu_set_reverb(&synth,0,0.f)==0);
    vh_native_spu_reset(&synth);
    assert(!synth.reverb_enabled && synth.reverb.cursor==0);
}

int main(void) {
    test_studio_c_disabled_and_tail();
    test_deterministic_state_vs_independent_context();
    test_dry_compatibility_and_mode_bit();
    puts("native STUDIO_C reverb network, send and tail: PASS");
    return 0;
}
