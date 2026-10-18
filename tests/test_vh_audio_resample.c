/* Deterministic 44.1-to-48 kHz PCM stereo streaming regression. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

static int16_t input[1024 * 2u];
static int16_t a[1300 * 2u], b[1300 * 2u];
static VhAudioResample left, right;

static void test_dc_and_first_linear_frames(void) {
    vh_audio_resample_reset(&left);
    for (unsigned i=0;i<1024;i++) {
        input[2u*i]=9000;
        input[2u*i+1u]=-13000;
    }
    const size_t n0=vh_audio_resample_process(&left,input,512,a,650);
    const size_t n1=vh_audio_resample_process(&left,input+1024,512,a+2*n0,650);
    assert(n0>=555 && n0<=559);
    assert(n1>=555 && n1<=559);
    for(size_t i=0;i<n0+n1;i++) {
        assert(a[2*i]==9000);
        assert(a[2*i+1]==-13000);
    }
    assert(left.input_frames==1024);
    assert(left.have_previous==1);
}

static void test_chunk_invariance_and_stereo(void) {
    for(unsigned i=0;i<1024;i++) {
        input[2u*i]=(int16_t)((int)i*45-19000);
        input[2u*i+1u]=(int16_t)(15000-(int)i*27);
    }
    vh_audio_resample_reset(&left);
    vh_audio_resample_reset(&right);
    size_t n=0,m=0;
    n+=vh_audio_resample_process(&left,input,512,a,650);
    n+=vh_audio_resample_process(&left,input+2*512,512,a+2*n,650);
    m+=vh_audio_resample_process(&right,input,240,b,650);
    m+=vh_audio_resample_process(&right,input+2*240,272,b+2*m,650);
    m+=vh_audio_resample_process(&right,input+2*512,512,b+2*m,650);
    assert(n==m);
    assert(n>=1110 && n<=1116);
    assert(memcmp(a,b,n*2u*sizeof(int16_t))==0);
    assert(a[0]==input[0] && a[1]==input[1]);
    /* 1st upsampled frame is at source position 147/160. */
    assert(a[2] == (int16_t)(
        ((int64_t)input[0]*(160-147)+(int64_t)input[2]*147)/160));
    assert(a[3] == (int16_t)(
        ((int64_t)input[1]*(160-147)+(int64_t)input[3]*147)/160));
}

static void test_capacity_and_restart(void) {
    vh_audio_resample_reset(&left);
    VhAudioResample snapshot=left;
    assert(vh_audio_resample_process(&left,input,512,a,100)==0);
    assert(memcmp(&left,&snapshot,sizeof left)==0);
    assert(vh_audio_resample_process(NULL,input,512,a,650)==0);
    assert(vh_audio_resample_process(&left,NULL,512,a,650)==0);
    assert(vh_audio_resample_process(&left,input,0,a,650)==0);
    assert(vh_audio_resample_process(&left,input,513,a,650)==0);
    assert(vh_audio_resample_process(&left,input,512,NULL,650)==0);
    assert(memcmp(&left,&snapshot,sizeof left)==0);
    vh_audio_resample_reset(&left);
    assert(left.input_frames==0 && left.next_output_tick==0);
}


/* Ten seconds of independently generated stereo data. Compare exact output
 * across fixed 512-frame input blocks and two different irregular schedules.
 * This exercises frame-to-frame phase continuity across many boundaries and
 * includes deliberately failed-capacity calls that must not consume PCM. */
#define LONG_SOURCE_FRAMES (10u * VH_AUDIO_SAMPLE_RATE)
static int16_t long_input[VH_AUDIO_BLOCK_FRAMES * 2u];
static int16_t long_output[VH_AUDIO_RESAMPLE_MAX_FRAMES * 2u];

typedef struct {
    uint64_t pcm_hash;
    size_t output_frames;
    VhAudioResample state;
} VhLongStreamResult;

static uint64_t hash_pcm(uint64_t hash, const int16_t *pcm, size_t frames) {
    for (size_t i = 0; i < frames * 2u; ++i) {
        const uint16_t sample = (uint16_t)pcm[i];
        hash ^= (uint8_t)sample;
        hash *= UINT64_C(1099511628211);
        hash ^= (uint8_t)(sample >> 8u);
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

static VhLongStreamResult stream_ten_seconds(unsigned schedule) {
    static const size_t uneven[] = {1u, 7u, 31u, 127u, 255u,
                                     511u, 2u, 63u, 512u, 3u};
    VhAudioResample state;
    vh_audio_resample_reset(&state);
    uint64_t hash = UINT64_C(14695981039346656037);
    size_t total_output = 0u;
    unsigned failed_capacity_checks = 0u;
    for (size_t pos = 0u, step = 0u; pos < LONG_SOURCE_FRAMES; ++step) {
        size_t chunk = VH_AUDIO_BLOCK_FRAMES;
        if (schedule == 1u) {
            chunk = uneven[step % (sizeof uneven / sizeof uneven[0])];
        } else if (schedule == 2u) {
            chunk = 1u + (step * 73u) % VH_AUDIO_BLOCK_FRAMES;
        }
        if (chunk > LONG_SOURCE_FRAMES - pos)
            chunk = LONG_SOURCE_FRAMES - pos;
        for (size_t i = 0; i < chunk; ++i) {
            const size_t frame = pos + i;
            const int left_sample = (int)((frame * 73u + 13u) & 65535u) - 32768;
            const int right_sample = (int)((frame * 151u + 491u) & 65535u) - 32768;
            long_input[2u * i] = (int16_t)left_sample;
            long_input[2u * i + 1u] = (int16_t)right_sample;
        }
        if (schedule == 2u && step % 29u == 0u) {
            /* Even a 1-frame input block needs more than one unit of
             * conservative output capacity. A rejected attempt must be
             * completely retryable, without phase or PCM writes. */
            const VhAudioResample snapshot = state;
            long_output[0] = 12345;
            assert(vh_audio_resample_process(
                &state, long_input, chunk, long_output, 1u) == 0u);
            assert(memcmp(&state, &snapshot, sizeof state) == 0);
            assert(long_output[0] == 12345);
            ++failed_capacity_checks;
        }
        const size_t n = vh_audio_resample_process(
            &state, long_input, chunk, long_output,
            VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(n <= VH_AUDIO_RESAMPLE_MAX_FRAMES);
        hash = hash_pcm(hash, long_output, n);
        total_output += n;
        pos += chunk;
    }
    if (schedule == 2u) assert(failed_capacity_checks >= 10u);
    assert(state.input_frames == LONG_SOURCE_FRAMES);
    VhLongStreamResult result = {hash, total_output, state};
    return result;
}

static void test_ten_second_stream_phase_invariance(void) {
    const VhLongStreamResult fixed = stream_ten_seconds(0u);
    const VhLongStreamResult irregular = stream_ten_seconds(1u);
    const VhLongStreamResult retried = stream_ten_seconds(2u);
    /* Without an explicit end-of-stream flush, the last fractional
     * sample needs one more input frame. 10 s at 44.1 kHz therefore
     * produces 479999 complete interpolated frames, not 480000. */
    assert(fixed.output_frames == 479999u);
    assert(irregular.output_frames == fixed.output_frames);
    assert(retried.output_frames == fixed.output_frames);
    assert(irregular.pcm_hash == fixed.pcm_hash);
    assert(retried.pcm_hash == fixed.pcm_hash);
    assert(memcmp(&fixed.state, &irregular.state, sizeof fixed.state) == 0);
    assert(memcmp(&fixed.state, &retried.state, sizeof fixed.state) == 0);
}

int main(void) {
    assert(VH_NATIVE_AUDOUT_RATE==48000u);
    assert(VH_AUDIO_SAMPLE_RATE==44100u);
    test_dc_and_first_linear_frames();
    test_chunk_invariance_and_stereo();
    test_capacity_and_restart();
    test_ten_second_stream_phase_invariance();
    puts("44.1k -> 48k stateful stereo resampler: PASS (10s phase and chunk invariance)");
    return 0;
}
