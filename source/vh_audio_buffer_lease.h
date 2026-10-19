#ifndef VH_AUDIO_BUFFER_LEASE_H
#define VH_AUDIO_BUFFER_LEASE_H

#include <stdint.h>

/* One-buffer audout ownership discipline. PlayBuffer waits for SOME
 * released buffer, not necessarily the newly submitted one.
 * Never allow backing PCM to be overwritten until the exact
 * submitted AudioOutBuffer descriptor is returned. Functions
 * are audio-owner-only, not thread synchronization primitives.
 */
typedef struct {
    const void *in_flight;
    uint64_t pages_released;
    unsigned mismatched_releases;
    unsigned abandoned_sessions;
    /* Stage346: software-only lease transitions, not DAC queue metrics. */
    uint64_t pages_leased;
    unsigned busy_begin_rejections;
} VhAudioBufferLease;

/* 0 = descriptor is now owned by device, -1 = busy or invalid. */
int vh_audio_buffer_lease_begin(VhAudioBufferLease *lease,
                                const void *descriptor);
/* 0 iff the exact descriptor is released; a mismatch keeps the
 * lease active until the entire output session is closed.
 */
int vh_audio_buffer_lease_release(VhAudioBufferLease *lease,
                                  const void *released);
/* Call only AFTER the previous audio session is closed, not merely
 * after audoutStopAudioOut (which can leave buffers queued).
 */
void vh_audio_buffer_lease_session_closed(VhAudioBufferLease *lease);

#endif
