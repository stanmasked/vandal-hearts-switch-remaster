#ifndef VH_AUDIO_OUTPUT_EDGES_H
#define VH_AUDIO_OUTPUT_EDGES_H

#include <stddef.h>
#include <stdint.h>

/* Optional normal-exit tail only. NEVER submit on HOME/focus loss:
 * applet suspension may invalidate audout while blocking its worker.
 * 96 frames at 48kHz is a two-millisecond stereo fade to digital 0.
 */
#define VH_AUDIO_STOP_TAIL_FRAMES 96u

/* Generate exactly 96 interleaved stereo frames, independent of
 * SEQ/SPU/resampler time. Last PCM sample of prior confirmed page
 * is frame zero; last frame is exactly zero. Returns -1 for invalid
 * args/capacity and leaves destination unchanged on failure.
 */
int vh_audio_stop_tail_build(int16_t *destination, size_t capacity_frames,
                             int16_t previous_left, int16_t previous_right);

/* Instrument time from audout resume attempt to FIRST CONFIRMED
 * COMPLETED PCM page. Not a speaker-onset time or latency guarantee.
 * Counters saturate instead of wrapping during long running sessions.
 */
typedef struct {
    uint64_t count, last_ns, min_ns, max_ns, sum_ns;
    uint64_t over_50ms, over_100ms;
} VhAudioResumeLatency;

void vh_audio_resume_latency_record(VhAudioResumeLatency *stats,
                                     uint64_t elapsed_ns);

#endif
