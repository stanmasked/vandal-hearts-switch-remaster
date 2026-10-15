#ifndef VH_AUDIO_STREAM_H
#define VH_AUDIO_STREAM_H

#include <stddef.h>
#include <stdint.h>

/* 44.1 kHz, stereo, interleaved signed PCM16 transport.
 * Single producer + single consumer; caller must synchronize access.
 * For SDL2: SDL_LockAudioDevice guards writes from the main thread,
 * and the audio callback reads without allocating or locking.
 */
#define VH_AUDIO_SAMPLE_RATE 44100
#define VH_AUDIO_CHANNELS 2
#define VH_AUDIO_BLOCK_FRAMES 512u
#define VH_AUDIO_RING_FRAMES 4096u

typedef struct {
    int16_t pcm[VH_AUDIO_RING_FRAMES * VH_AUDIO_CHANNELS];
    size_t read_index;
    size_t write_index;
    size_t queued_frames;
    uint64_t overrun_frames;
    uint64_t underrun_frames;
} VhAudioStream;

void vh_audio_stream_reset(VhAudioStream *stream);
size_t vh_audio_stream_queued(const VhAudioStream *stream);
size_t vh_audio_stream_write(VhAudioStream *stream,
                             const int16_t *stereo_pcm, size_t frames);
/* Zero-fill any underrun; return actual source frames before padding. */
size_t vh_audio_stream_read(VhAudioStream *stream,
                            int16_t *stereo_out, size_t frames);

#endif
