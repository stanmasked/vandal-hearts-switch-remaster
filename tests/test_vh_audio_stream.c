/* Synthetic host regression: stereo order, wrap, silence, overflow, FIFO. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_stream.h"

static VhAudioStream ring;
static int16_t source[VH_AUDIO_RING_FRAMES * 2];
static int16_t dest[(VH_AUDIO_RING_FRAMES + 32) * 2];
static int16_t expected[VH_AUDIO_RING_FRAMES * 2];

static void basic(void) {
    vh_audio_stream_reset(&ring);
    for (size_t i = 0; i < 20; ++i) dest[i] = 555;
    assert(vh_audio_stream_read(&ring, dest, 10) == 0);
    for (size_t i = 0; i < 20; ++i) assert(dest[i] == 0);
    assert(ring.underrun_frames == 10);
    int16_t pair[] = {1, -1, 2, -2, 3, -3};
    assert(vh_audio_stream_write(&ring, pair, 3) == 3);
    assert(vh_audio_stream_queued(&ring) == 3);
    assert(vh_audio_stream_read(&ring, dest, 5) == 3);
    assert(!memcmp(pair, dest, sizeof(pair)));
    for (size_t i = 6; i < 10; ++i) assert(dest[i] == 0);
    assert(ring.underrun_frames == 12);
    assert(vh_audio_stream_queued(&ring) == 0);
}

static void full_and_wrap(void) {
    vh_audio_stream_reset(&ring);
    for (size_t i = 0; i < VH_AUDIO_RING_FRAMES; ++i) {
        source[2 * i] = (int16_t)i;
        source[2 * i + 1] = -(int16_t)i;
    }
    assert(vh_audio_stream_write(&ring, source, VH_AUDIO_RING_FRAMES) == VH_AUDIO_RING_FRAMES);
    assert(vh_audio_stream_write(&ring, source, 9) == 0);
    assert(ring.overrun_frames == 9);
    assert(vh_audio_stream_read(&ring, dest, VH_AUDIO_RING_FRAMES - 8) == VH_AUDIO_RING_FRAMES - 8);
    assert(!memcmp(source, dest, (VH_AUDIO_RING_FRAMES - 8) * 2 * sizeof(int16_t)));
    assert(vh_audio_stream_write(&ring, source, 6) == 6);
    assert(vh_audio_stream_read(&ring, dest, 14) == 14);
    assert(!memcmp(dest, &source[(VH_AUDIO_RING_FRAMES - 8) * 2], 8 * 2 * sizeof(int16_t)));
    assert(!memcmp(&dest[8 * 2], source, 6 * 2 * sizeof(int16_t)));
    assert(vh_audio_stream_queued(&ring) == 0);
}

static void malformed_calls(void) {
    vh_audio_stream_reset(&ring);
    assert(vh_audio_stream_write(NULL, source, 10) == 0);
    assert(vh_audio_stream_write(&ring, NULL, 10) == 0);
    assert(vh_audio_stream_write(&ring, source, 0) == 0);
    assert(vh_audio_stream_read(&ring, NULL, 10) == 0);
    assert(vh_audio_stream_queued(NULL) == 0);
    for (size_t i = 0; i < 8; ++i) dest[i] = 99;
    assert(vh_audio_stream_read(NULL, dest, 4) == 0);
    for (size_t i = 0; i < 8; ++i) assert(dest[i] == 0);
    vh_audio_stream_reset(&ring);
    assert(ring.overrun_frames == 0 && ring.underrun_frames == 0);
}

static void randomized_fifo(void) {
    vh_audio_stream_reset(&ring);
    size_t length = 0;
    uint32_t seed = 0x7145a1c2u;
    for (size_t step = 0; step < 6000; ++step) {
        seed = seed * 1664525u + 1013904223u;
        size_t n = (seed >> 16) % 41u;
        if (seed & 0x8000u) {
            for (size_t j = 0; j < n; ++j) {
                source[2 * j] = (int16_t)(step % 30000);
                source[2 * j + 1] = -(int16_t)(step % 30000);
            }
            size_t free = VH_AUDIO_RING_FRAMES - length;
            size_t accepted = n < free ? n : free;
            assert(vh_audio_stream_write(&ring, source, n) == accepted);
            memcpy(&expected[length * 2], source, accepted * 2 * sizeof(int16_t));
            length += accepted;
        } else {
            size_t taken = n < length ? n : length;
            assert(vh_audio_stream_read(&ring, dest, n) == taken);
            assert(!memcmp(dest, expected, taken * 2 * sizeof(int16_t)));
            for (size_t i = 2 * taken; i < 2 * n; ++i) assert(dest[i] == 0);
            memmove(expected, &expected[2 * taken], (length - taken) * 2 * sizeof(int16_t));
            length -= taken;
        }
        assert(vh_audio_stream_queued(&ring) == length);
    }
}

int main(void) {
    assert(VH_AUDIO_SAMPLE_RATE == 44100);
    assert(VH_AUDIO_CHANNELS == 2);
    assert(VH_AUDIO_BLOCK_FRAMES == 512);
    basic();
    full_and_wrap();
    malformed_calls();
    randomized_fifo();
    puts("native PCM stereo ring: PASS (synthetic)");
    return 0;
}
