/* FIFO pause/resume policy regression: drain existing audio before
 * continuing production; no stale replay and no synthetic audio assets.
 * This tests host PCM queue logic, not libnx audout stop/start behavior.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_stream.h"

static VhAudioStream queue;
static int16_t in[512u*2u], out[512u*2u];
int main(void) {
    vh_audio_stream_reset(&queue);
    for (unsigned block=0; block<24u; ++block) {
        for (unsigned i=0;i<512u;i++) {
            int16_t sample=(int16_t)(block*512u+i);
            in[2u*i]=sample;
            in[2u*i+1u]=(int16_t)-sample;
        }
        /* Each frame is consumed exactly once, including after pause.
         * Pausing means do not produce or consume any queued frames.
         */
        assert(vh_audio_stream_write(&queue,in,512u)==512u);
        if(block==8u || block==16u) {
            /* Queued frames must remain untouched during the pause. */
            size_t saved=vh_audio_stream_queued(&queue);
            size_t read_pos=queue.read_index;
            size_t write_pos=queue.write_index;
            assert(saved==512u);
            assert(vh_audio_stream_queued(&queue)==saved);
            assert(queue.read_index==read_pos && queue.write_index==write_pos);
        }
        memset(out,0,sizeof out);
        assert(vh_audio_stream_read(&queue,out,512u)==512u);
        assert(memcmp(out,in,sizeof in)==0);
        assert(vh_audio_stream_queued(&queue)==0);
    }
    assert(queue.overrun_frames==0u && queue.underrun_frames==0u);
    puts("host PCM FIFO pause boundary (no stale replay): PASS");
    return 0;
}
