/* Reverb history can survive a bank switch independently of voice PCM.
 * No owned PS1 samples or Switch services; checks deterministic state carry.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_native_spu.h"

static VhNativeSpu before, resumed, control;
static int16_t tone[112], scratch[512*2], resumed_out[512*2], control_out[512*2];
int main(void) {
    for (unsigned i=0;i<112u;i++)
        tone[i]=(int16_t)((int)(i*431u)%20000-10000);
    vh_native_spu_reset(&before);
    assert(vh_native_spu_set_reverb(&before,1,0.5f)==0);
    assert(vh_native_spu_note_on(&before,0u,tone,112u,0,112,4096,15,0,
                                 0.7f,0.4f)==0);
    assert(vh_native_spu_set_voice_reverb(&before,0u,1)==0);
    for (unsigned b=0;b<16u;b++)
        vh_native_spu_render(&before,scratch,512u);
    const VhSpuReverb history=before.reverb;
    /* Detach every bank-owned voice, but preserve the reverb processor. */
    vh_native_spu_reset(&resumed);
    assert(vh_native_spu_set_reverb(&resumed,1,0.5f)==0);
    resumed.reverb=history;
    vh_native_spu_reset(&control);
    assert(vh_native_spu_set_reverb(&control,1,0.5f)==0);
    for (unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
        assert(resumed.voice[slot].pcm==NULL);
        assert(!resumed.voice[slot].active);
    }
    assert(memcmp(&resumed.reverb,&history,sizeof history)==0);
    /* A second continuation must yield byte-identical wet tail. */
    VhNativeSpu duplicate=resumed;
    uint64_t difference=0;
    for(unsigned b=0;b<8u;b++) {
        vh_native_spu_render(&resumed,resumed_out,512u);
        vh_native_spu_render(&duplicate,scratch,512u);
        vh_native_spu_render(&control,control_out,512u);
        assert(memcmp(resumed_out,scratch,sizeof resumed_out)==0);
        for(size_t i=0;i<512u*2u;i++)
            difference+=(resumed_out[i]!=control_out[i]);
    }
    assert(resumed.frames_rendered==8u*512u);
    assert(difference>0u);
    puts("reverb history independent of old-bank PCM: PASS");
    return 0;
}
