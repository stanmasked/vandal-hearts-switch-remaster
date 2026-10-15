#include "vh_audio_stream.h"

#include <string.h>

void vh_audio_stream_reset(VhAudioStream *stream) {
    if (!stream) return;
    memset(stream, 0, sizeof(*stream));
}

size_t vh_audio_stream_queued(const VhAudioStream *stream) {
    return stream ? stream->queued_frames : 0;
}

size_t vh_audio_stream_write(VhAudioStream *stream,
                             const int16_t *stereo_pcm, size_t frames) {
    if (!stream || !stereo_pcm || !frames) return 0;
    const size_t available = VH_AUDIO_RING_FRAMES - stream->queued_frames;
    const size_t written = frames < available ? frames : available;
    size_t first = VH_AUDIO_RING_FRAMES - stream->write_index;
    if (first > written) first = written;
    memcpy(&stream->pcm[stream->write_index * VH_AUDIO_CHANNELS], stereo_pcm,
           first * VH_AUDIO_CHANNELS * sizeof(int16_t));
    if (written > first) {
        memcpy(stream->pcm, &stereo_pcm[first * VH_AUDIO_CHANNELS],
               (written - first) * VH_AUDIO_CHANNELS * sizeof(int16_t));
    }
    stream->write_index = (stream->write_index + written) % VH_AUDIO_RING_FRAMES;
    stream->queued_frames += written;
    stream->overrun_frames += (uint64_t)(frames - written);
    return written;
}

size_t vh_audio_stream_read(VhAudioStream *stream,
                            int16_t *stereo_out, size_t frames) {
    if (!stereo_out || !frames) return 0;
    if (!stream) {
        memset(stereo_out, 0, frames * VH_AUDIO_CHANNELS * sizeof(int16_t));
        return 0;
    }
    const size_t received =
        frames < stream->queued_frames ? frames : stream->queued_frames;
    size_t first = VH_AUDIO_RING_FRAMES - stream->read_index;
    if (first > received) first = received;
    memcpy(stereo_out, &stream->pcm[stream->read_index * VH_AUDIO_CHANNELS],
           first * VH_AUDIO_CHANNELS * sizeof(int16_t));
    if (received > first) {
        memcpy(&stereo_out[first * VH_AUDIO_CHANNELS], stream->pcm,
               (received - first) * VH_AUDIO_CHANNELS * sizeof(int16_t));
    }
    if (received < frames) {
        memset(&stereo_out[received * VH_AUDIO_CHANNELS], 0,
               (frames - received) * VH_AUDIO_CHANNELS * sizeof(int16_t));
    }
    stream->read_index = (stream->read_index + received) % VH_AUDIO_RING_FRAMES;
    stream->queued_frames -= received;
    stream->underrun_frames += (uint64_t)(frames - received);
    return received;
}
