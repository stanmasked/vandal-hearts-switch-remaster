#include "vh_audio_output_edges.h"

#include <stdint.h>
#include <limits.h>

int vh_audio_stop_tail_build(int16_t *destination, size_t capacity_frames,
                             int16_t previous_left, int16_t previous_right) {
    if (!destination || capacity_frames<VH_AUDIO_STOP_TAIL_FRAMES)
        return -1;
    for (unsigned i=0;i<VH_AUDIO_STOP_TAIL_FRAMES;i++) {
        const int32_t weight=(int32_t)(VH_AUDIO_STOP_TAIL_FRAMES-1u-i);
        destination[i*2u]=(int16_t)(
            ((int32_t)previous_left *weight)/
            (int32_t)(VH_AUDIO_STOP_TAIL_FRAMES-1u));
        destination[i*2u+1u]=(int16_t)(
            ((int32_t)previous_right *weight)/
            (int32_t)(VH_AUDIO_STOP_TAIL_FRAMES-1u));
    }
    return 0;
}

void vh_audio_resume_latency_record(VhAudioResumeLatency *s,
                                     uint64_t elapsed_ns) {
    if (!s) return;
    if (!s->count || elapsed_ns<s->min_ns)
        s->min_ns=elapsed_ns;
    if (elapsed_ns>s->max_ns) s->max_ns=elapsed_ns;
    s->last_ns=elapsed_ns;
    if (s->count<UINT64_MAX) ++s->count;
    s->sum_ns=UINT64_MAX-s->sum_ns<elapsed_ns
        ? UINT64_MAX : s->sum_ns+elapsed_ns;
    if (elapsed_ns>UINT64_C(50000000) && s->over_50ms<UINT64_MAX)
        ++s->over_50ms;
    if (elapsed_ns>UINT64_C(100000000) && s->over_100ms<UINT64_MAX)
        ++s->over_100ms;
}
