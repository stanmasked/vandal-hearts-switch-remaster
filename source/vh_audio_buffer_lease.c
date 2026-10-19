#include "vh_audio_buffer_lease.h"

#include <limits.h>
#include <stddef.h>

int vh_audio_buffer_lease_begin(VhAudioBufferLease *lease,
                                const void *descriptor) {
    if (!lease || !descriptor) return -1;
    if (lease->in_flight) {
        if (lease->busy_begin_rejections<UINT_MAX)
            ++lease->busy_begin_rejections;
        return -1;
    }
    lease->in_flight=descriptor;
    if (lease->pages_leased<UINT64_MAX) ++lease->pages_leased;
    return 0;
}

int vh_audio_buffer_lease_release(VhAudioBufferLease *lease,
                                  const void *released) {
    if (!lease || !lease->in_flight) return -1;
    if (!released || released!=lease->in_flight) {
        if (lease->mismatched_releases<UINT_MAX)
            ++lease->mismatched_releases;
        return -1;
    }
    lease->in_flight=NULL;
    if (lease->pages_released<UINT64_MAX) ++lease->pages_released;
    return 0;
}

void vh_audio_buffer_lease_session_closed(VhAudioBufferLease *lease) {
    if (!lease) return;
    if (lease->in_flight && lease->abandoned_sessions<UINT_MAX)
        ++lease->abandoned_sessions;
    lease->in_flight=NULL;
}
