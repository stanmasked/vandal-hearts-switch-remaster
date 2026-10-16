/* Verify queued music survives pause at ring wrap; stale samples do not replay.
 * Generated PCM, host-only. Does not emulate libnx audout service.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_stream.h"

static VhAudioStream ring;
static int16_t source[4096u * 2u], received[4096u * 2u];

static void fill(unsigned start, unsigned count) {
    for (unsigned i=0;i<count;i++) {
        unsigned t=start+i;
        source[i*2u]=(int16_t)(t%30000u);
        source[i*2u+1u]=(int16_t)-(int)(t%30000u);
    }
}
static void check(unsigned start, unsigned count) {
    for (unsigned i=0;i<count;i++) {
        unsigned t=start+i;
        assert(received[i*2u]==(int16_t)(t%30000u));
        assert(received[i*2u+1u]==(int16_t)-(int)(t%30000u));
    }
}
int main(void) {
    vh_audio_stream_reset(&ring);
    fill(0u,3000u);
    assert(vh_audio_stream_write(&ring,source,3000u)==3000u);
    assert(vh_audio_stream_read(&ring,received,2500u)==2500u);
    check(0u,2500u);

    /* Producer wraps while 500 original frames are still queued. */
    fill(3000u,2000u);
    assert(vh_audio_stream_write(&ring,source,2000u)==2000u);
    assert(vh_audio_stream_queued(&ring)==2500u);
    const size_t rd=ring.read_index, wr=ring.write_index;
    const uint64_t over=ring.overrun_frames, under=ring.underrun_frames;

    /* Deliberate pause: no producer/consumer activity, even at wrap. */
    for (unsigned i=0;i<100u;i++) {
        assert(vh_audio_stream_queued(&ring)==2500u);
        assert(ring.read_index==rd && ring.write_index==wr);
        assert(ring.overrun_frames==over && ring.underrun_frames==under);
    }

    assert(vh_audio_stream_read(&ring,received,2500u)==2500u);
    check(2500u,2500u);
    assert(vh_audio_stream_queued(&ring)==0u);
    /* Empty read pads zeros and never replays the previously queued data. */
    memset(received,0x7f,128u*2u*sizeof(int16_t));
    assert(vh_audio_stream_read(&ring,received,128u)==0u);
    for (unsigned i=0;i<128u*2u;i++) assert(received[i]==0);
    assert(ring.underrun_frames==128u && ring.overrun_frames==0u);
    puts("host PCM pause at ring wrap and empty zero-fill: PASS");
    return 0;
}
