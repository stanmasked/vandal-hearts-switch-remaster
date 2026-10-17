/* Fault-injected output restart: never re-render SEQ, SPU or resampler
 * while retrying an immutable 48-kHz PCM page. Host only, no libnx.
 */
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_output_recovery.h"
#include "vh_audio_resample.h"
#include "vh_audio_report_pages.h"
#include "vh_native_seq.h"

typedef struct {
    unsigned opened, playing, failures_left, submissions, accepted;
    unsigned opens, closes, stops, starts, attempts_this_page;
    int fail_stop, fail_open, fail_start;
    unsigned fail_starts_left, fail_opens_left, fail_stops_left;
    unsigned mismatched_returns_left, null_returns_left;
    /* Strict mock ownership: a foreign/NULL backend return leaves
     * our descriptor in-flight. Only a SUCCESSFUL stop flushes it.
     * No later submit is allowed until that ownership is cleared. */
    unsigned pending_unreleased, flushed_unreleased;
    int owned_descriptor, foreign_descriptor;
    const int16_t *page_pointer;
    size_t page_frames;
    uint64_t page_hash, checksum;
    VhAudioSubmitTiming timing;
} Mock;

static uint64_t hash_page(const int16_t *pcm, size_t frames) {
    uint64_t h=UINT64_C(1469598103934665603);
    for (size_t i=0;i<frames*2u;i++) {
        h^=(uint16_t)pcm[i];
        h*=UINT64_C(1099511628211);
    }
    return h;
}
static int submit(void *ctx,const int16_t *pcm,size_t frames) {
    Mock *m=ctx;
    assert(m->opened && m->playing && pcm && frames);
    assert(m->pending_unreleased==0u);
    const uint64_t hash=hash_page(pcm,frames);
    if (!m->attempts_this_page) {
        m->page_pointer=pcm;
        m->page_frames=frames;
        m->page_hash=hash;
    } else {
        assert(m->page_pointer==pcm);
        assert(m->page_frames==frames && m->page_hash==hash);
    }
    ++m->attempts_this_page;
    ++m->submissions;
    /* Fake backend latency, not elapsed wall-clock CI time. One
     * record per raw attempt, including retries and failures.
     */
    const uint64_t waited=(m->submissions%5u==0u)
        ? 250000u : 110000u;
    if (m->failures_left) {
        --m->failures_left;
        assert(vh_audio_output_record_submit_timing(
            &m->timing,waited,19200000u,frames,0)==0);
        return -1;
    }
    /* Simulate a successful libnx return with a wrong (or missing)
     * descriptor. Never permit page reuse until the matching buffer
     * is released, even though the underlying API reported success.
     */
    const void *returned=&m->owned_descriptor;
    if (m->mismatched_returns_left) {
        --m->mismatched_returns_left;
        returned=&m->foreign_descriptor;
    } else if (m->null_returns_left) {
        --m->null_returns_left;
        returned=NULL;
    }
    const int returned_ours=
        vh_audio_output_page_returned(&m->owned_descriptor,returned);
    assert(vh_audio_output_record_submit_timing(
        &m->timing,waited,19200000u,frames,returned_ours)==0);
    if (!returned_ours) {
        m->pending_unreleased=1u;
        return -1;
    }
    ++m->accepted;
    m->checksum=(m->checksum ^ hash)*UINT64_C(1099511628211);
    return 0;
}
static int stop(void *ctx) {
    Mock *m=ctx;
    ++m->stops;
    if (m->fail_stops_left) {
        --m->fail_stops_left;
        return -1;
    }
    if (m->fail_stop) return -1;
    /* A successful stop drains/discards any unreturned descriptor.
     * An unsuccessful stop must NOT grant ownership to the caller. */
    if (m->pending_unreleased) {
        ++m->flushed_unreleased;
        m->pending_unreleased=0u;
    }
    m->playing=0;
    return 0;
}
static void close_device(void *ctx) {
    Mock *m=ctx;
    assert(!m->playing && !m->pending_unreleased);
    ++m->closes;
    m->opened=0;
}
static int open_device(void *ctx) {
    Mock *m=ctx;
    ++m->opens;
    if (m->fail_opens_left) {
        --m->fail_opens_left;
        return -1;
    }
    if (m->fail_open) return -1;
    m->opened=1;
    return 0;
}
static int start(void *ctx) {
    Mock *m=ctx;
    ++m->starts;
    if (m->fail_starts_left) {
        --m->fail_starts_left;
        return -1;
    }
    if (m->fail_start) return -1;
    assert(m->opened && !m->playing);
    m->playing=1;
    return 0;
}
static VhAudioOutputOps callbacks(Mock *m) {
    const VhAudioOutputOps ops={
        m,submit,stop,close_device,open_device,start
    };
    return ops;
}
static void begin_page(Mock *m,unsigned failures) {
    m->failures_left=failures;
    m->attempts_this_page=0;
    m->page_pointer=NULL;
    m->page_frames=0;
    m->page_hash=0;
    assert(!m->pending_unreleased);
}
static const uint8_t song[]={
    'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0,
    0,0xc0,7,0,0x90,60,110,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static int16_t sample[128], alternate_sample[128];
static int16_t src[512u*2u], dst[640u*2u];
static VhSpuReverb history_before_switch;
static VhNativeSpu spu;
static VhNativeSeq seq;
static VhAudioResample resampler;
static int resolve(void *ctx,unsigned program,unsigned note,
                   unsigned velocity,unsigned volume,unsigned pan,
                   VhSeqTone *out) {
    (void)velocity;(void)volume;(void)pan;
    if (!out || program!=7u || note!=60u) return -1;
    memset(out,0,sizeof *out);
    out->pcm=ctx ? (const int16_t *)ctx : sample;
    out->frames=128u;
    out->loop_start=0;
    out->loop_end=128;
    out->pitch_step=4096u;
    out->adsr1=15;
    out->gain_left=.7f;
    out->gain_right=.4f;
    out->reverb_send=1;
    return 0;
}

/* Mirrors the native producer's serialized gate: do not reinitialize
 * borrowed VAB/SEQ voice memory until audout has returned the page, or
 * until a successful backend stop has explicitly drained the lease. */
static int switch_when_page_free(VhAudioPageLease *lease,
                                 const int16_t *new_pcm) {
    if (!vh_audio_page_lease_ready(lease)) return -1;
    return vh_native_seq_switch_scene(&seq,song,sizeof song,&spu,
                                      resolve,(void *)new_pcm,0u);
}

static void test_audout_inflight_page_lease_scene_lifetime(void) {
    VhAudioPageLease lease={0};
    int descriptor=0,foreign=0;
    assert(vh_audio_page_lease_ready(&lease));
    assert(!vh_audio_page_lease_ready(NULL));
    assert(vh_audio_page_lease_begin(NULL,&descriptor)==-1);
    assert(vh_audio_page_lease_begin(&lease,NULL)==-1);
    assert(vh_audio_page_lease_return(&lease,&descriptor)==-1);
    assert(vh_audio_page_lease_return(NULL,&descriptor)==-1);
    assert(vh_audio_page_lease_stopped(NULL,0)==-1);

    for(unsigned i=0u;i<128u;i++) {
        sample[i]=(int16_t)((int)i*67-4400);
        alternate_sample[i]=(int16_t)((int)i*93-6000);
    }
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,sample,0u)==0);
    const int16_t *current=sample;
    unsigned released=0u,stopped=0u;
    for(unsigned iteration=0u;iteration<96u;iteration++) {
        assert(vh_audio_page_lease_ready(&lease));
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
                         &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t page_hash=hash_page(dst,frames);
        const VhNativeSeq before=seq;
        const uint64_t spu_frames=spu.frames_rendered;
        const uint64_t clock=resampler.input_frames;
        const int16_t *next=(iteration&1u) ? sample : alternate_sample;
        assert(vh_audio_page_lease_begin(&lease,&descriptor)==0);
        assert(!vh_audio_page_lease_ready(&lease));
        assert(lease.in_flight==&descriptor);
        assert(vh_audio_page_lease_begin(&lease,&descriptor)==-1);
        assert(vh_audio_page_lease_begin(&lease,&foreign)==-1);
        assert(vh_audio_page_lease_return(&lease,NULL)==-1);
        assert(vh_audio_page_lease_return(&lease,&foreign)==-1);
        assert(vh_audio_page_lease_stopped(&lease,-1)==-1);
        assert(lease.in_flight==&descriptor);
        /* Both "bad descriptor" and "bad stop" paths must leave the
         * current voice bank, music clock and 48-kHz page untouched. */
        assert(switch_when_page_free(&lease,next)==-1);
        assert(!memcmp(&seq,&before,sizeof seq));
        assert(spu.frames_rendered==spu_frames);
        assert(resampler.input_frames==clock);
        assert(seq.context==current);
        assert(hash_page(dst,frames)==page_hash);
        if(iteration%3u==0u) {
            /* A failed backend stop is NOT permission to free the old
             * buffer. The successful stop below is the only way out. */
            Mock backend={.opened=1u,.playing=1u,.fail_stops_left=1u};
            assert(stop(&backend)==-1);
            assert(backend.playing);
            assert(!vh_audio_page_lease_ready(&lease));
            assert(switch_when_page_free(&lease,next)==-1);
            assert(stop(&backend)==0);
            assert(!backend.playing);
            assert(vh_audio_page_lease_stopped(&lease,0)==0);
            stopped++;
        } else {
            assert(vh_audio_page_lease_return(&lease,&descriptor)==0);
            assert(vh_audio_page_lease_return(&lease,&descriptor)==-1);
            released++;
        }
        assert(vh_audio_page_lease_ready(&lease));
        assert(hash_page(dst,frames)==page_hash);
        assert(switch_when_page_free(&lease,next)==0);
        current=next;
        assert(seq.context==current && seq.blocks_advanced==0u);
        assert(spu.frames_rendered==0u);
        assert(resampler.input_frames==clock);
        for(unsigned slot=0u;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
            assert(!spu.voice[slot].active);
            assert(spu.voice[slot].pcm==NULL);
        }
    }
    assert(released==64u && stopped==32u);
    assert(vh_audio_page_lease_stopped(&lease,0)==0);
    assert(vh_audio_page_lease_ready(&lease));
}


/* A production-shaped audout callback mock. The backend may return
 * the WRONG AudioOutBuffer pointer; in this case the page remains
 * in-flight even if the service itself returned success. The exact
 * same output samples must survive a failed stop and eventual replay.
 * There is no libnx service or physical-device claim in this test. */
typedef struct {
    VhAudioPageLease lease;
    int descriptor, foreign_descriptor;
    const int16_t *pcm;
    size_t frames;
    uint64_t pcm_hash;
    unsigned opened, playing;
    unsigned wrong_returns_left, failed_stops_left;
    unsigned failed_opens_left, failed_starts_left;
    unsigned calls, stops, closes, opens, starts, returned;
    VhAudioTransportTimingHealth transport_health;
    VhAudioTimingFaultInjection timing_injection;
    unsigned timing_fault_mode;
} LeasedDevice;

static int leased_submit(void *opaque,const int16_t *pcm,size_t frames) {
    LeasedDevice *d=opaque;
    if(!d->opened || !d->playing ||
       vh_audio_page_lease_begin(&d->lease,&d->descriptor))
        return -1;
    assert(pcm==d->pcm && frames==d->frames);
    assert(hash_page(pcm,frames)==d->pcm_hash);
    ++d->calls;
    if(d->wrong_returns_left) {
        --d->wrong_returns_left;
        assert(!vh_audio_output_page_returned(&d->descriptor,
                                             &d->foreign_descriptor));
        assert(vh_audio_page_lease_return(
                   &d->lease,&d->foreign_descriptor)==-1);
        assert(!vh_audio_page_lease_ready(&d->lease));
        return -1;
    }
    assert(vh_audio_output_page_returned(&d->descriptor,&d->descriptor));
    assert(vh_audio_page_lease_return(&d->lease,&d->descriptor)==0);
    assert(vh_audio_page_lease_ready(&d->lease));
    ++d->returned;
    return 0;
}
static int leased_stop(void *opaque) {
    LeasedDevice *d=opaque;
    ++d->stops;
    if(!d->playing)
        return vh_audio_page_lease_ready(&d->lease) ? 0 : -1;
    if(d->failed_stops_left) {
        --d->failed_stops_left;
        assert(vh_audio_page_lease_stopped(&d->lease,-1)==-1);
        assert(d->lease.in_flight==&d->descriptor);
        return -1;
    }
    assert(vh_audio_page_lease_stopped(&d->lease,0)==0);
    d->playing=0u;
    return 0;
}
static void leased_close(void *opaque) {
    LeasedDevice *d=opaque;
    if(!d->opened) return;
    assert(!d->playing && vh_audio_page_lease_ready(&d->lease));
    ++d->closes;
    d->opened=0u;
}
static int leased_open(void *opaque) {
    LeasedDevice *d=opaque;
    if(d->opened || !vh_audio_page_lease_ready(&d->lease)) return -1;
    ++d->opens;
    if(d->failed_opens_left) {
        --d->failed_opens_left;
        return -1;
    }
    d->opened=1u;
    return 0;
}
static int leased_start(void *opaque) {
    LeasedDevice *d=opaque;
    if(!d->opened || d->playing ||
       !vh_audio_page_lease_ready(&d->lease)) return -1;
    ++d->starts;
    if(d->failed_starts_left) {
        --d->failed_starts_left;
        return -1;
    }
    d->playing=1u;
    return 0;
}
/* The backend has ALREADY returned the correct descriptor. Timing
 * telemetry can still fail (zero tick frequency or overflow). Such
 * diagnostic failure must never trigger transport stop/reopen/replay. */
static int leased_submit_with_timing_fault(
    void *opaque, const int16_t *pcm, size_t frames) {
    LeasedDevice *dev=opaque;
    const int sent=leased_submit(opaque,pcm,frames);
    /* Three independent reasons to reject optional timing: a
     * missing clock, saturated call count, or saturated tick sum. */
    VhAudioSubmitTiming invalid={0};
    const unsigned mode=dev->timing_fault_mode%3u;
    const uint64_t hz=mode ? UINT64_C(19200000) : 0u;
    if(mode==1u) invalid.calls=UINT64_MAX;
    if(mode==2u) invalid.total_ticks=UINT64_MAX;
    const VhAudioSubmitTiming before=invalid;
    const int recorded=vh_audio_output_record_submit_timing(
                           &invalid,200u,hz,frames,sent==0);
    assert(recorded==-1 &&
           !memcmp(&invalid,&before,sizeof invalid));
    return vh_audio_output_transport_outcome(sent==0,recorded,
                                              &dev->transport_health);
}

/* ZL-style fault injection must be consumed only by a valid returned
 * descriptor. An erroneous one first triggers normal stop/reopen
 * recovery; it cannot spoof the timing-only failure. */
static int leased_submit_with_one_shot_bad_clock(
    void *opaque, const int16_t *pcm, size_t frames) {
    LeasedDevice *dev=opaque;
    const int returned=leased_submit(opaque,pcm,frames)==0;
    const uint64_t freq=vh_audio_timing_fault_frequency(
                &dev->timing_injection,returned,UINT64_C(19200000));
    VhAudioSubmitTiming telemetry={0};
    const int recorded=vh_audio_output_record_submit_timing(
                      &telemetry,200u,freq,frames,returned);
    assert((freq==0u)==(recorded==-1));
    return vh_audio_output_transport_outcome(
                returned,recorded,&dev->transport_health);
}

/* ZL is merely an on-console request: the final report must bind
 * INJECTED to a genuinely returned page and rejected timing record.
 * An absent ZL request must not conceal unrelated real timing errors.
 */
static void test_timing_injection_final_evidence(void) {
    VhAudioTimingFaultInjection injection={0};
    VhAudioTransportTimingHealth health={0};
    VhAudioOutputRecovery recovery={.pages_submitted=1u};
    assert(vh_audio_output_verify_timing_injection(
               NULL,&health,&recovery)==-1);
    assert(vh_audio_output_verify_timing_injection(
               &injection,NULL,&recovery)==-1);
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,NULL)==-1);
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==0);
    assert(vh_audio_timing_fault_arm(&injection)==0);
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==1);
    assert(vh_audio_timing_fault_frequency(
               &injection,0,UINT64_C(19200000))==UINT64_C(19200000));
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==1);
    assert(vh_audio_timing_fault_frequency(
               &injection,1,UINT64_C(19200000))==0u);
    /* Malformed records cannot claim a verified injection. */
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==-1);
    assert(vh_audio_output_transport_outcome(1,-1,&health)==0);
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==2);
    health.delivered_without_timing=0u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==-1);
    health.delivered_without_timing=2u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==-1);
    health.delivered_without_timing=1u;
    health.timing_fault=0u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==-1);
    health.timing_fault=1u;
    injection.armed=1u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==-1);
    injection.armed=0u;
    injection.injected=2u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==-1);
    /* Real diagnostic faults can happen without any ZL injection. */
    injection.injected=0u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==0);
    injection.armed=1u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==1);
    injection.armed=0u;
    health.delivered_without_timing=0u;
    assert(vh_audio_output_verify_timing_injection(
               &injection,&health,&recovery)==0);
}

static void test_one_shot_timing_injection_after_returned_pcm(void) {
    VhAudioTimingFaultInjection probe={0};
    assert(vh_audio_timing_fault_arm(NULL)==-1);
    assert(vh_audio_timing_fault_arm(&probe)==0);
    assert(probe.armed && !probe.injected);
    assert(vh_audio_timing_fault_arm(&probe)==-1);
    assert(vh_audio_timing_fault_frequency(
                  &probe,0,UINT64_C(19200000))==UINT64_C(19200000));
    assert(probe.armed && !probe.injected);
    assert(vh_audio_timing_fault_frequency(
                  &probe,1,UINT64_C(19200000))==0u);
    assert(!probe.armed && probe.injected);
    assert(vh_audio_timing_fault_frequency(
                  &probe,1,UINT64_C(19200000))==UINT64_C(19200000));
    assert(vh_audio_timing_fault_arm(&probe)==-1);
    assert(vh_audio_timing_fault_frequency(
                  NULL,1,UINT64_C(19200000))==UINT64_C(19200000));

    for(unsigned i=0u;i<128u;i++)
        sample[i]=(int16_t)((int)i*53-4000);
    vh_native_spu_reset(&spu);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,sample,0u)==0);
    unsigned recovered=0u,direct=0u;
    for(unsigned i=0u;i<48u;i++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
                              &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t page_hash=hash_page(dst,frames);
        const VhNativeSeq before_seq=seq;
        const VhNativeSpu before_spu=spu;
        const VhAudioResample before_resampler=resampler;
        LeasedDevice dev={
            .opened=1u,.playing=1u,.pcm=dst,.frames=frames,
            .pcm_hash=page_hash,.wrong_returns_left=(unsigned)(i&1u)
        };
        assert(vh_audio_timing_fault_arm(&dev.timing_injection)==0);
        VhAudioOutputRecovery stats={0};
        const VhAudioOutputOps ops={
            &dev,leased_submit_with_one_shot_bad_clock,
            leased_stop,leased_close,leased_open,leased_start
        };
        assert(vh_audio_output_submit_recover(&ops,&stats,dst,frames)==0);
        assert(!dev.timing_injection.armed && dev.timing_injection.injected);
        assert(dev.transport_health.timing_fault==1u &&
               dev.transport_health.delivered_without_timing==1u);
        assert(vh_audio_output_verify_transport_health(
                         &dev.transport_health,&stats)==1);
        assert(stats.pages_submitted==1u &&
               stats.frames_submitted==frames && dev.returned==1u);
        if(i&1u) {
            ++recovered;
            assert(dev.calls==2u && dev.stops==1u &&
                   dev.opens==1u && dev.closes==1u &&
                   stats.submit_failures==1u && stats.recoveries==1u);
        } else {
            ++direct;
            assert(dev.calls==1u && !dev.stops &&
                   !stats.submit_failures && !stats.recoveries);
        }
        assert(vh_audio_page_lease_ready(&dev.lease));
        assert(hash_page(dst,frames)==page_hash);
        assert(!memcmp(&seq,&before_seq,sizeof seq));
        assert(!memcmp(&spu,&before_spu,sizeof spu));
        assert(!memcmp(&resampler,&before_resampler,sizeof resampler));
        assert(vh_audio_output_stop_close(&ops)==0);
    }
    assert(direct==24u && recovered==24u);
}

static void test_timing_fault_never_replays_delivered_pcm(void) {
    unsigned direct=0u,backend_retry=0u;
    for(unsigned i=0u;i<128u;i++)
        sample[i]=(int16_t)((int)i*67-4500);
    vh_native_spu_reset(&spu);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,sample,0u)==0);
    for(unsigned iteration=0u;iteration<48u;iteration++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
                              &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const VhNativeSeq saved_seq=seq;
        const VhNativeSpu saved_spu=spu;
        const VhAudioResample saved_rate=resampler;
        const uint64_t page_hash=hash_page(dst,frames);
        LeasedDevice dev={
            .opened=1u,.playing=1u,.pcm=dst,.frames=frames,
            .pcm_hash=page_hash,
            .wrong_returns_left=(unsigned)(iteration&1u),
            .timing_fault_mode=iteration%3u
        };
        VhAudioOutputRecovery counters={0};
        const VhAudioOutputOps callbacks={
            &dev,leased_submit_with_timing_fault,
            leased_stop,leased_close,leased_open,leased_start
        };
        assert(vh_audio_output_submit_recover(
                            &callbacks,&counters,dst,frames)==0);
        assert(dev.transport_health.timing_fault==1u);
        assert(dev.transport_health.delivered_without_timing==1u);
        assert(vh_audio_output_verify_transport_health(
                   &dev.transport_health,&counters)==1);
        assert(counters.pages_submitted==1u &&
               counters.frames_submitted==frames);
        assert(dev.returned==1u &&
               vh_audio_page_lease_ready(&dev.lease));
        if(iteration&1u) {
            backend_retry++;
            /* A real wrong-descriptor failure still needs exactly
             * one stop/reopen and retry, not extra timing-fault retries. */
            assert(dev.calls==2u && dev.stops==1u &&
                   dev.closes==1u && dev.opens==1u && dev.starts==1u);
            assert(counters.submit_failures==1u &&
                   counters.restart_attempts==1u && counters.recoveries==1u);
        } else {
            direct++;
            /* The accepted PCM remains exactly once, no recovery. */
            assert(dev.calls==1u && dev.stops==0u &&
                   dev.closes==0u && dev.opens==0u && dev.starts==0u);
            assert(counters.submit_failures==0u &&
                   counters.restart_attempts==0u && counters.recoveries==0u);
        }
        assert(hash_page(dst,frames)==page_hash);
        assert(!memcmp(&seq,&saved_seq,sizeof seq));
        assert(!memcmp(&spu,&saved_spu,sizeof spu));
        assert(!memcmp(&resampler,&saved_rate,sizeof resampler));
        assert(vh_audio_output_stop_close(&callbacks)==0);
        assert(vh_audio_page_lease_ready(&dev.lease));
    }
    assert(direct==24u && backend_retry==24u);

    /* The outcome is driven ONLY by descriptor transport. An invalid
     * observation counts a returned page once; a foreign descriptor
     * never contributes to the returned-without-timing accumulator. */
    VhAudioTransportTimingHealth health={0};
    assert(vh_audio_output_transport_outcome(0,-1,&health)==-1);
    assert(health.timing_fault==1u && !health.delivered_without_timing);
    assert(vh_audio_output_transport_outcome(1,-1,&health)==0);
    assert(vh_audio_output_transport_outcome(1,-1,&health)==0);
    assert(health.timing_fault==1u &&
           health.delivered_without_timing==2u);
    assert(vh_audio_output_transport_outcome(0,-1,&health)==-1 &&
           health.delivered_without_timing==2u);
    assert(vh_audio_output_transport_outcome(1,0,&health)==0 &&
           health.delivered_without_timing==2u);
    health=(VhAudioTransportTimingHealth){0};
    assert(vh_audio_output_transport_outcome(1,0,&health)==0 &&
           health.timing_fault==0u &&
           health.delivered_without_timing==0u);
    health.delivered_without_timing=UINT64_MAX;
    assert(vh_audio_output_transport_outcome(1,-1,&health)==0);
    assert(health.timing_fault==1u &&
           health.delivered_without_timing==UINT64_MAX);
    assert(vh_audio_output_transport_outcome(0,-1,NULL)==-1);
    assert(vh_audio_output_transport_outcome(1,-1,NULL)==0);

    VhAudioOutputRecovery sample_stats={.pages_submitted=1u};
    health=(VhAudioTransportTimingHealth){0};
    assert(vh_audio_output_verify_transport_health(&health,&sample_stats)==0);
    health.delivered_without_timing=1u;
    assert(vh_audio_output_verify_transport_health(&health,&sample_stats)==-1);
    health.timing_fault=1u;
    assert(vh_audio_output_verify_transport_health(&health,&sample_stats)==1);
    health.delivered_without_timing=2u;
    assert(vh_audio_output_verify_transport_health(&health,&sample_stats)==-1);
    health.delivered_without_timing=1u;
    health.timing_fault=2u;
    assert(vh_audio_output_verify_transport_health(&health,&sample_stats)==-1);
    assert(vh_audio_output_verify_transport_health(NULL,&sample_stats)==-1);
    assert(vh_audio_output_verify_transport_health(&health,NULL)==-1);

}

static void test_failed_stop_page_lease_with_real_recovery(void) {
    for(unsigned i=0u;i<128u;i++) {
        sample[i]=(int16_t)((int)i*67-4400);
        alternate_sample[i]=(int16_t)((int)i*93-6000);
    }
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,sample,0u)==0);
    unsigned recovered=0u,manual_stops=0u;
    for(unsigned iteration=0u;iteration<36u;iteration++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
                              &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t original_hash=hash_page(dst,frames);
        const VhNativeSeq old_seq=seq;
        const uint64_t spu_frames=spu.frames_rendered;
        const VhAudioResample old_resampler=resampler;
        LeasedDevice d={
            .pcm=dst,.frames=frames,.pcm_hash=original_hash,
            .opened=1u,.playing=1u,
            .wrong_returns_left=1u,
            .failed_stops_left=(iteration%3u==0u ? 1u : 0u)
        };
        VhAudioOutputRecovery recovery={0};
        const VhAudioOutputOps ops={
            &d,leased_submit,leased_stop,leased_close,
            leased_open,leased_start
        };
        const int first=vh_audio_output_submit_recover(
                                       &ops,&recovery,dst,frames);
        if(iteration%3u==0u) {
            /* Failed stop: the original descriptor is still owned.
             * No reopen, rerender, bank replacement or second submit. */
            assert(first==-1);
            assert(recovery.submit_failures==1u);
            assert(recovery.restart_attempts==0u);
            assert(recovery.pages_submitted==0u);
            assert(d.calls==1u && d.stops==1u && d.closes==0u);
            assert(d.opened && d.playing && !d.returned);
            assert(d.lease.in_flight==&d.descriptor);
            assert(leased_submit(&d,dst,frames)==-1);
            assert(d.calls==1u);
            assert(switch_when_page_free(&d.lease,alternate_sample)==-1);
            assert(vh_audio_output_stop_close(&ops)==0);
            assert(d.stops==2u && d.closes==1u);
            assert(vh_audio_page_lease_ready(&d.lease));
            assert(ops.open(ops.context)==0);
            assert(ops.start(ops.context)==0);
            assert(vh_audio_output_submit_recover(
                        &ops,&recovery,dst,frames)==0);
            assert(recovery.submit_failures==1u);
            assert(recovery.pages_submitted==1u);
            assert(recovery.restart_attempts==0u);
            ++manual_stops;
        } else {
            /* Same fully rendered page is resent after a successful
             * backend stop, close, reopen and restart. */
            assert(first==0);
            assert(recovery.submit_failures==1u);
            assert(recovery.restart_attempts==1u);
            assert(recovery.recoveries==1u);
            assert(recovery.pages_submitted==1u);
            assert(d.calls==2u && d.stops==1u &&
                   d.closes==1u && d.opens==1u && d.starts==1u);
            ++recovered;
        }
        assert(d.returned==1u && d.calls==2u);
        assert(vh_audio_page_lease_ready(&d.lease));
        assert(hash_page(dst,frames)==original_hash);
        assert(memcmp(&seq,&old_seq,sizeof seq)==0);
        assert(spu.frames_rendered==spu_frames);
        assert(memcmp(&resampler,&old_resampler,sizeof resampler)==0);
        assert(vh_audio_output_stop_close(&ops)==0);
        assert(!d.opened && !d.playing);
        const int16_t *next=iteration%2u ? sample : alternate_sample;
        assert(switch_when_page_free(&d.lease,next)==0);
        assert(seq.context==next && seq.blocks_advanced==0u);
        assert(spu.frames_rendered==0u);
        assert(resampler.input_frames==old_resampler.input_frames);
    }
    assert(recovered==24u && manual_stops==12u);
}


/* Host-only exit/reopen fault injection. A wrong audout descriptor
 * leaves the PCM page held through THREE failed stops: the recovery
 * helper, final teardown and HOME/resume. No operation may overwrite
 * or replay the page until stop drains the descriptor. After reopening
 * it must be submitted exactly once, without another SEQ/SPU tick. */
static void test_shutdown_resume_inflight_descriptor_lifetime(void) {
    for(unsigned k=0u;k<128u;k++) {
        sample[k]=(int16_t)((int)k*71-5000);
        alternate_sample[k]=(int16_t)((int)k*89-7000);
    }
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,sample,0u)==0);
    unsigned resume_path=0u,close_path=0u;
    for(unsigned iteration=0u;iteration<48u;iteration++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
                       &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t pcm_hash=hash_page(dst,frames);
        const VhNativeSeq before_seq=seq;
        const VhNativeSpu before_spu=spu;
        const VhAudioResample before_rate=resampler;
        LeasedDevice dev={
            .pcm=dst,.frames=frames,.pcm_hash=pcm_hash,
            .opened=1u,.playing=1u,
            .wrong_returns_left=1u,.failed_stops_left=3u
        };
        VhAudioOutputRecovery stats={0};
        const VhAudioOutputOps callbacks={
            &dev,leased_submit,leased_stop,leased_close,
            leased_open,leased_start
        };
        /* Backend claims success but releases a FOREIGN descriptor.
         * Recovery's first audoutStopAudioOut also fails. */
        assert(vh_audio_output_submit_recover(
                         &callbacks,&stats,dst,frames)==-1);
        assert(dev.calls==1u && dev.stops==1u && !dev.closes);
        assert(dev.lease.in_flight==&dev.descriptor);
        assert(stats.submit_failures==1u);
        assert(stats.pages_submitted==0u &&
               stats.restart_attempts==0u);
        const int16_t *next=(iteration&1u) ? sample : alternate_sample;

        /* Exit teardown must not call close or unlock after a second
         * failed audout stop. Forced HOME/resume must also fail safely. */
        assert(vh_audio_output_stop_close(&callbacks)==-1);
        assert(dev.stops==2u && !dev.closes && dev.playing);
        assert(vh_audio_output_resume_recover(
                         &callbacks,&stats,1)==-1);
        assert(dev.stops==3u && !dev.closes && dev.playing);
        assert(stats.resume_restarts==0u &&
               stats.resume_recoveries==0u);
        assert(dev.lease.in_flight==&dev.descriptor);
        assert(leased_submit(&dev,dst,frames)==-1);
        assert(dev.calls==1u);
        assert(switch_when_page_free(&dev.lease,next)==-1);
        assert(memcmp(&seq,&before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&before_spu,sizeof spu)==0);
        assert(memcmp(&resampler,&before_rate,sizeof resampler)==0);
        assert(hash_page(dst,frames)==pcm_hash);

        if(iteration&1u) {
            /* A clean teardown finally drains the outstanding page.
             * A new session then safely resumes without a write. */
            assert(vh_audio_output_stop_close(&callbacks)==0);
            assert(dev.stops==4u && dev.closes==1u);
            assert(vh_audio_page_lease_ready(&dev.lease));
            assert(leased_open(&dev)==0 && leased_start(&dev)==0);
            ++close_path;
        } else {
            /* The recovery API must not silently submit old PCM:
             * it only opens and starts a new audout session. */
            assert(vh_audio_output_resume_recover(
                         &callbacks,&stats,1)==0);
            assert(dev.stops==4u && dev.closes==1u);
            assert(stats.resume_restarts==1u &&
                   stats.resume_recoveries==1u);
            assert(stats.pages_submitted==0u);
            assert(vh_audio_page_lease_ready(&dev.lease));
            ++resume_path;
        }
        assert(dev.calls==1u && dev.returned==0u);
        assert(hash_page(dst,frames)==pcm_hash);
        assert(memcmp(&seq,&before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&before_spu,sizeof spu)==0);
        assert(memcmp(&resampler,&before_rate,sizeof resampler)==0);
        /* One retry of the PRE-RENDERED page, same pointer and samples.
         * The music clock is exactly where it was at the first attempt. */
        assert(vh_audio_output_submit_recover(
                         &callbacks,&stats,dst,frames)==0);
        assert(dev.calls==2u && dev.returned==1u);
        assert(stats.pages_submitted==1u &&
               stats.frames_submitted==frames);
        assert(stats.submit_failures==1u &&
               stats.restart_attempts==0u);
        assert(vh_audio_page_lease_ready(&dev.lease));
        assert(hash_page(dst,frames)==pcm_hash);
        assert(memcmp(&seq,&before_seq,sizeof seq)==0);
        assert(memcmp(&spu,&before_spu,sizeof spu)==0);
        assert(memcmp(&resampler,&before_rate,sizeof resampler)==0);
        assert(vh_audio_output_stop_close(&callbacks)==0);
        assert(!dev.opened && !dev.playing);
        assert(switch_when_page_free(&dev.lease,next)==0);
        assert(seq.context==next && seq.blocks_advanced==0u);
        assert(spu.frames_rendered==0u);
        assert(resampler.input_frames==before_rate.input_frames);
    }
    assert(resume_path==24u && close_path==24u);
}


/* Returned PCM and an empty lease are a precondition for HOME pause:
 * repeated same-session and forced-reopen resumes must never re-submit
 * the page or advance SEQ/SPU/44.1->48k resampling. Faults in open()
 * and start() require bounded fallback, without any producer activity.
 */
static void test_repeated_home_resume_with_returned_pcm(void) {
    for(unsigned i=0u;i<128u;i++) {
        sample[i]=(int16_t)((int)i*73-5200);
        alternate_sample[i]=(int16_t)((int)i*97-6000);
    }
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,
                              resolve,sample,0u)==0);
    unsigned ordinary=0u,fast_retry=0u,open_retry=0u,start_retry=0u;
    for(unsigned iteration=0u;iteration<96u;iteration++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
                          &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t fingerprint=hash_page(dst,frames);
        const VhNativeSeq saved_seq=seq;
        const VhNativeSpu saved_spu=spu;
        const VhAudioResample saved_resampler=resampler;
        LeasedDevice dev={
            .opened=1u,.playing=1u,.pcm=dst,
            .frames=frames,.pcm_hash=fingerprint
        };
        VhAudioOutputRecovery stats={0};
        const VhAudioOutputOps ops={
            &dev,leased_submit,leased_stop,leased_close,
            leased_open,leased_start
        };
        assert(vh_audio_output_submit_recover(
                  &ops,&stats,dst,frames)==0);
        assert(stats.pages_submitted==1u && stats.frames_submitted==frames);
        assert(dev.calls==1u && dev.returned==1u);
        assert(vh_audio_page_lease_ready(&dev.lease));
        assert(leased_stop(&dev)==0 && !dev.playing);

        const unsigned mode=iteration%4u;
        if(mode==1u) dev.failed_starts_left=1u;
        if(mode==2u) dev.failed_opens_left=1u;
        if(mode==3u) dev.failed_starts_left=1u;
        const int forced=(mode>=2u);
        assert(vh_audio_output_resume_recover(&ops,&stats,forced)==0);
        assert(dev.opened && dev.playing);
        assert(vh_audio_page_lease_ready(&dev.lease));
        assert(dev.calls==1u && dev.returned==1u);
        assert(stats.pages_submitted==1u && stats.frames_submitted==frames);
        assert(stats.submit_failures==0u && stats.restart_attempts==0u);
        if(mode==0u) {
            ordinary++;
            assert(stats.resume_restarts==0u &&
                   stats.resume_failures==0u &&
                   stats.resume_recoveries==0u);
        } else if(mode==1u) {
            fast_retry++;
            assert(stats.resume_restarts==1u &&
                   stats.resume_failures==1u &&
                   stats.resume_recoveries==1u);
        } else {
            if(mode==2u) open_retry++; else start_retry++;
            assert(stats.resume_restarts==2u &&
                   stats.resume_failures==1u &&
                   stats.resume_recoveries==1u);
        }
        const VhAudioOutputRecovery settled=stats;
        const unsigned submitted=dev.calls,returned=dev.returned;
        /* Rapid HOME-focus oscillations after the one returned page
         * use only stop()/start(): no extra pages and no retry counts. */
        for(unsigned n=0u;n<4u;n++) {
            assert(leased_stop(&dev)==0);
            assert(vh_audio_output_resume_recover(&ops,&stats,0)==0);
            assert(dev.opened && dev.playing);
            assert(!memcmp(&stats,&settled,sizeof settled));
            assert(dev.calls==submitted && dev.returned==returned);
            assert(vh_audio_page_lease_ready(&dev.lease));
            assert(hash_page(dst,frames)==fingerprint);
            assert(!memcmp(&seq,&saved_seq,sizeof seq));
            assert(!memcmp(&spu,&saved_spu,sizeof spu));
            assert(!memcmp(&resampler,&saved_resampler,
                           sizeof resampler));
        }
        assert(vh_audio_output_stop_close(&ops)==0);
        assert(!dev.opened && !dev.playing);
        assert(vh_audio_page_lease_ready(&dev.lease));
        const int16_t *next=(iteration&1u) ? sample : alternate_sample;
        assert(switch_when_page_free(&dev.lease,next)==0);
        assert(seq.context==next && seq.blocks_advanced==0u);
        assert(spu.frames_rendered==0u);
        assert(resampler.input_frames==saved_resampler.input_frames);
    }
    assert(ordinary==24u && fast_retry==24u &&
           open_retry==24u && start_retry==24u);
}


/* End-to-end host mock: synthesize an actual 44.1k SEQ/SPU page,
 * resample to 48k, observe HOME, then submit with a real page lease.
 * Wrong returned descriptors and failed stops leave HOME pending;
 * retrying the very SAME PCM bytes, without advancing any clocks,
 * is the only path to a first-returned-page observation. */
static void test_home_observer_vs_audout_lease_faults(void) {
    for(unsigned i=0u;i<128u;i++) {
        sample[i]=(int16_t)((int)i*67-5200);
        alternate_sample[i]=(int16_t)((int)i*97-6500);
    }
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,
                              &spu,resolve,sample,0u)==0);
    VhAudioAppletEvents observed={0};
    const VhAudioManualResume no_manual={0};
    const uint64_t hz=UINT64_C(19200000);
    unsigned automatic_recoveries=0u,failed_stops=0u,clean_pages=0u;
    for(unsigned epoch=0u;epoch<48u;epoch++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
                             &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const VhNativeSeq saved_seq=seq;
        const VhNativeSpu saved_spu=spu;
        const VhAudioResample saved_rate=resampler;
        const uint64_t fingerprint=hash_page(dst,frames);
        const uint64_t budget=(uint64_t)frames*hz/48000u;
        const uint64_t start=UINT64_C(1000000)+(uint64_t)epoch*
                             UINT64_C(3000000);
        assert(vh_audio_applet_record_at(&observed,
                         VH_AUDIO_APPLET_BACKGROUND,start-500u)==0);
        assert(vh_audio_applet_record_at(&observed,
                         VH_AUDIO_APPLET_FOREGROUND,start)==0);
        assert(observed.pending_return && vh_audio_applet_verify(&observed)==0);
        LeasedDevice dev={
            .opened=1u,.playing=1u,.pcm=dst,
            .frames=frames,.pcm_hash=fingerprint,
            .wrong_returns_left=(epoch%3u !=0u),
            .failed_stops_left=(epoch%3u ==2u)
        };
        VhAudioOutputRecovery stats={0};
        const VhAudioOutputOps ops={
            &dev,leased_submit,leased_stop,leased_close,
            leased_open,leased_start
        };
        const int submitted=vh_audio_output_submit_recover(
                                      &ops,&stats,dst,frames);
        if(epoch%3u==0u) {
            ++clean_pages;
            assert(submitted==0 && stats.submit_failures==0u);
        } else if(epoch%3u==1u) {
            ++automatic_recoveries;
            assert(submitted==0 && stats.submit_failures==1u &&
                   stats.recoveries==1u);
        } else {
            ++failed_stops;
            assert(submitted==-1 && stats.submit_failures==1u &&
                   !stats.pages_submitted && !dev.returned);
            assert(dev.lease.in_flight==&dev.descriptor);
            /* Device reported no page. It would be incorrect to call
             * vh_audio_applet_page_returned here. */
            assert(vh_audio_applet_submit_failed(&observed)==0);
            assert(observed.pending_return && !observed.in_background);
            assert(vh_audio_report_focus_evidence(&observed,&no_manual,
                1,0,0,0,0)==VH_AUDIO_REPORT_INCOMPLETE);
            assert(leased_submit(&dev,dst,frames)==-1);
            assert(switch_when_page_free(&dev.lease,alternate_sample)==-1);
            assert(vh_audio_output_stop_close(&ops)==0);
            assert(vh_audio_page_lease_ready(&dev.lease));
            assert(leased_open(&dev)==0 && leased_start(&dev)==0);
            assert(vh_audio_output_submit_recover(&ops,&stats,dst,frames)==0);
            assert(dev.calls==2u && dev.returned==1u);
        }
        assert(dev.returned==1u && stats.pages_submitted==1u);
        assert(stats.frames_submitted==frames);
        assert(vh_audio_page_lease_ready(&dev.lease));
        assert(hash_page(dst,frames)==fingerprint);
        assert(memcmp(&seq,&saved_seq,sizeof seq)==0);
        assert(memcmp(&spu,&saved_spu,sizeof spu)==0);
        assert(memcmp(&resampler,&saved_rate,sizeof resampler)==0);
        /* Each group of six covers inclusive 1x, 2x, 4x and >4x
         * elapsed times with the same native page budget. */
        const unsigned multiple=epoch%6u+1u;
        assert(vh_audio_applet_page_returned_budget_at(
                         &observed,start+budget*multiple,budget)==1);
        assert(observed.first_pages_after_return==epoch+1u &&
               observed.returned_pages==epoch+1u &&
               !observed.pending_return && vh_audio_applet_verify(&observed)==0);
        assert(vh_audio_report_focus_evidence(&observed,&no_manual,
                    1,0,0,0,0)==VH_AUDIO_REPORT_FULL);
        assert(vh_audio_output_stop_close(&ops)==0);
        const int16_t *next=epoch%2u ? sample : alternate_sample;
        assert(switch_when_page_free(&dev.lease,next)==0);
        assert(seq.context==next && seq.blocks_advanced==0u);
        assert(spu.frames_rendered==0u);
        assert(resampler.input_frames==saved_rate.input_frames);
    }
    assert(clean_pages==16u && automatic_recoveries==16u &&
           failed_stops==16u);
    assert(observed.failed_logical_submissions==16u &&
           observed.failures_while_pending==16u);
    assert(observed.timed_first_pages==48u &&
           observed.budgeted_first_pages==48u);
    assert(observed.page_budget_bands[0]==8u &&
           observed.page_budget_bands[1]==8u &&
           observed.page_budget_bands[2]==16u &&
           observed.page_budget_bands[3]==16u);
    assert(vh_audio_applet_verify(&observed)==0);
}

int main(void) {
    test_timing_injection_final_evidence();
    test_one_shot_timing_injection_after_returned_pcm();
    test_timing_fault_never_replays_delivered_pcm();
    test_home_observer_vs_audout_lease_faults();
    test_audout_inflight_page_lease_scene_lifetime();
    test_failed_stop_page_lease_with_real_recovery();
    test_shutdown_resume_inflight_descriptor_lifetime();
    test_repeated_home_resume_with_returned_pcm();
    Mock device={.opened=1,.playing=1,
                 .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps ops=callbacks(&device);
    VhAudioOutputRecovery stats={0};
    /* Deterministic synthetic timer: distinguishes expected blocking
     * page waits from failed backend calls, without sleeping in CI.
     * The page budget at 19.2 MHz / 48 kHz for 576 frames is 230400.
     */
    VhAudioSubmitTiming timing={0};
    const uint64_t freq=UINT64_C(19200000);
    assert(vh_audio_output_record_submit_timing(
               &timing,100000u,freq,576u,1)==0);
    assert(vh_audio_output_record_submit_timing(
               &timing,240000u,freq,576u,0)==0);
    assert(vh_audio_output_record_submit_timing(
               &timing,230400u,freq,576u,1)==0);
    assert(timing.calls==3u);
    assert(timing.total_ticks==570400u);
    assert(timing.max_ticks==240000u);
    assert(timing.waits_longer_than_page==1u);
    assert(timing.failed_submissions==1u);
    assert(vh_audio_output_ticks_to_us(240000u,freq)==12500u);
    assert(vh_audio_output_ticks_to_us(freq,freq)==1000000u);
    assert(vh_audio_output_ticks_to_us(UINT64_MAX,1u)==UINT64_MAX);
    assert(vh_audio_output_ticks_to_us(100u,0u)==0u);
    const VhAudioSubmitTiming stable=timing;
    assert(vh_audio_output_record_submit_timing(
               NULL,10u,freq,576u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,0u,576u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,0u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,VH_AUDIO_RESAMPLE_MAX_FRAMES+1u,1)==-1);
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,UINT64_MAX,576u,1)==-1);
    assert(!memcmp(&timing,&stable,sizeof timing));
    timing.calls=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,576u,1)==-1);
    timing=stable;
    timing.total_ticks=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,1u,freq,576u,1)==-1);
    timing=stable;
    timing.failed_submissions=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,10u,freq,576u,0)==-1);
    timing=stable;
    timing.waits_longer_than_page=UINT64_MAX;
    assert(vh_audio_output_record_submit_timing(
               &timing,240000u,freq,576u,1)==-1);

    /* Per-logical-page wait grouping; retries count as ONE accepted
     * page and their raw blocking ticks are accumulated together.
     */
    VhAudioSceneWaits grouping={0};
    const VhAudioSubmitTiming first_before={0};
    const VhAudioSubmitTiming first_after={
        .calls=2u, .total_ticks=340000u,
        .waits_longer_than_page=1u, .failed_submissions=1u
    };
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,1)==0);
    assert(grouping.first_after_switch.pages==1u);
    assert(grouping.first_after_switch.total_ticks==340000u);
    assert(grouping.first_after_switch.peak_page_ticks==340000u);
    assert(grouping.first_after_switch.slow_pages==1u);
    assert(grouping.first_after_switch.retried_pages==1u);
    assert(grouping.first_after_switch.failed_pages==0u);
    const VhAudioSubmitTiming second_after={
        .calls=3u, .total_ticks=460000u,
        .waits_longer_than_page=1u, .failed_submissions=1u
    };
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_after,&second_after,freq,576u,0,1)==0);
    assert(grouping.ordinary.pages==1u);
    assert(grouping.ordinary.total_ticks==120000u);
    assert(grouping.ordinary.slow_pages==0u);
    assert(grouping.ordinary.retried_pages==0u);
    const VhAudioSubmitTiming failed_after={
        .calls=4u, .total_ticks=510000u,
        .waits_longer_than_page=1u, .failed_submissions=2u
    };
    assert(vh_audio_output_record_scene_page(
        &grouping,&second_after,&failed_after,freq,576u,1,0)==0);
    assert(grouping.first_after_switch.pages==2u);
    assert(grouping.first_after_switch.failed_pages==1u);
    assert(grouping.first_after_switch.total_ticks==390000u);
    assert(grouping.first_after_switch.wait_le_page==1u);
    assert(grouping.first_after_switch.wait_le_2pages==1u);
    assert(grouping.first_after_switch.wait_le_4pages==0u);
    assert(grouping.first_after_switch.wait_gt_4pages==0u);
    assert(grouping.ordinary.wait_le_page==1u);
    const VhAudioSceneWaits fixed_grouping=grouping;
    assert(vh_audio_output_record_scene_page(
        NULL,&first_before,&first_after,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,NULL,&first_after,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,NULL,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_after,&first_before,freq,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,0u,576u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,0u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,
        VH_AUDIO_RESAMPLE_MAX_FRAMES+1u,1,1)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,0)==-1);
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,UINT64_MAX,576u,1,1)==-1);
    VhAudioSubmitTiming too_many=first_after;
    too_many.calls=VH_AUDIO_OUTPUT_RESTART_LIMIT+2u;
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&too_many,freq,576u,1,1)==-1);
    assert(!memcmp(&grouping,&fixed_grouping,sizeof grouping));
    grouping.first_after_switch.pages=UINT64_MAX;
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,1)==-1);
    grouping=fixed_grouping;
    grouping.first_after_switch.total_ticks=UINT64_MAX;
    assert(vh_audio_output_record_scene_page(
        &grouping,&first_before,&first_after,freq,576u,1,1)==-1);
    grouping=fixed_grouping;

    /* Four disjoint latency bands, normalized by *actual* stereo
     * page length (576 / 48000 seconds), not nominal source blocks.
     * No allocations or samples are stored by the histogram.
     */
    VhAudioSceneWaits latency_bands={0};
    VhAudioSubmitTiming previous={0};
    static const uint64_t band_ticks[]={100000u,300000u,
                                       700000u,1200000u};
    for (unsigned i=0;i<4u;i++) {
        VhAudioSubmitTiming next=previous;
        next.calls++;
        next.total_ticks+=band_ticks[i];
        if (band_ticks[i]>next.max_ticks)
            next.max_ticks=band_ticks[i];
        if (band_ticks[i]>230400u)
            next.waits_longer_than_page++;
        assert(vh_audio_output_record_scene_page(
            &latency_bands,&previous,&next,freq,576u,0,1)==0);
        previous=next;
    }
    const VhAudioPageWaitBucket *hist=&latency_bands.ordinary;
    assert(hist->pages==4u && hist->wait_le_page==1u);
    assert(hist->wait_le_2pages==1u);
    assert(hist->wait_le_4pages==1u);
    assert(hist->wait_gt_4pages==1u);
    VhAudioOutputRecovery hist_recovery={.pages_submitted=4u};
    assert(vh_audio_output_verify_run(
        &latency_bands,&hist_recovery,&previous,
        4u,0u,4u,0u,1)==1);
    VhAudioSceneWaits corrupt_bands=latency_bands;
    corrupt_bands.ordinary.wait_le_2pages++;
    assert(vh_audio_output_verify_run(
        &corrupt_bands,&hist_recovery,&previous,
        4u,0u,4u,0u,1)==-1);
    corrupt_bands=latency_bands;
    corrupt_bands.ordinary.wait_gt_4pages--;
    assert(vh_audio_output_verify_run(
        &corrupt_bands,&hist_recovery,&previous,
        4u,0u,4u,0u,1)==-1);

    assert(vh_audio_output_submit_recover(NULL,&stats,dst,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,NULL,dst,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,NULL,10u)==-1);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,0u)==-1);
    assert(vh_audio_output_submit_recover(
               &ops,&stats,dst,VH_AUDIO_RESAMPLE_MAX_FRAMES+1u)==-1);
    assert(device.submissions==0u && stats.pages_submitted==0u);
    /* Identity contract used by both native libnx probes: a service
     * success with NULL or a foreign descriptor is NOT page release. */
    int owned_page=1, foreign_page=2;
    assert(vh_audio_output_page_returned(&owned_page,&owned_page));
    assert(!vh_audio_output_page_returned(&owned_page,&foreign_page));
    assert(!vh_audio_output_page_returned(&owned_page,NULL));
    assert(!vh_audio_output_page_returned(NULL,NULL));
    for (unsigned form=0;form<2u;form++) {
        Mock wrong={.opened=1,.playing=1};
        VhAudioOutputOps wrong_ops=callbacks(&wrong);
        VhAudioOutputRecovery wrong_stats={0};
        for (unsigned i=0;i<64u;i++) dst[i]=(int16_t)i;
        const uint64_t original_hash=hash_page(dst,32u);
        begin_page(&wrong,0u);
        if (form==0u) wrong.mismatched_returns_left=1u;
        else wrong.null_returns_left=1u;
        assert(vh_audio_output_submit_recover(
                   &wrong_ops,&wrong_stats,dst,32u)==0);
        assert(wrong_stats.pages_submitted==1u);
        assert(wrong_stats.frames_submitted==32u);
        assert(wrong_stats.submit_failures==1u);
        assert(wrong_stats.restart_attempts==1u);
        assert(wrong_stats.recoveries==1u);
        assert(wrong.submissions==2u && wrong.accepted==1u);
        assert(wrong.opens==1u && wrong.closes==1u &&
               wrong.stops==1u && wrong.starts==1u);
        assert(wrong.pending_unreleased==0u &&
               wrong.flushed_unreleased==1u);
        assert(hash_page(dst,32u)==original_hash);
        assert(wrong.page_pointer==dst && wrong.page_frames==32u);
        assert(wrong.page_hash==original_hash);
    }
    /* Repeated foreign released pointers never grant ownership of the
     * caller's page. Exhausting two restarts must stop the session and
     * return failure, leaving the entire prepared page untouched.
     */
    Mock never_returned={.opened=1,.playing=1};
    VhAudioOutputOps no_return_ops=callbacks(&never_returned);
    VhAudioOutputRecovery no_return_stats={0};
    begin_page(&never_returned,0u);
    never_returned.mismatched_returns_left=
        VH_AUDIO_OUTPUT_RESTART_LIMIT+1u;
    const uint64_t guarded_hash=hash_page(dst,32u);
    assert(vh_audio_output_submit_recover(&no_return_ops,&no_return_stats,
                                          dst,32u)==-1);
    assert(no_return_stats.pages_submitted==0u);
    assert(no_return_stats.frames_submitted==0u);
    assert(no_return_stats.submit_failures==
           VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    assert(no_return_stats.restart_attempts==
           VH_AUDIO_OUTPUT_RESTART_LIMIT);
    assert(never_returned.accepted==0u);
    assert(never_returned.pending_unreleased==1u &&
           never_returned.flushed_unreleased==
           VH_AUDIO_OUTPUT_RESTART_LIMIT);
    assert(never_returned.submissions==VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    assert(never_returned.timing.calls==never_returned.submissions);
    assert(never_returned.timing.failed_submissions==
           never_returned.submissions);
    assert(hash_page(dst,32u)==guarded_hash);
    for(unsigned i=0;i<128u;i++)
        sample[i]=(int16_t)((int)i*113-7000);
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,resolve,NULL,0)==0);
    /* Independent expected 48-kHz stream fingerprint: backend restarts
     * must not duplicate, drop or reorder any accepted PCM page.
     */
    uint64_t expected_checksum=UINT64_C(1469598103934665603);
    uint64_t expected_frames=0;
    unsigned expected_failures=0,expected_recovered_pages=0;
    for (unsigned block=0;block<64u;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
            &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        expected_checksum=(expected_checksum ^ hash_page(dst,frames)) *
                          UINT64_C(1099511628211);
        expected_frames+=frames;
        const uint64_t old_spu=spu.frames_rendered;
        const uint64_t old_in=resampler.input_frames;
        const uint64_t old_tick=resampler.next_output_tick;
        const uint64_t old_notes=seq.note_ons;
        const unsigned failures=(block%17u==5u)?2u:
                                (block%11u==3u)?1u:0u;
        expected_failures+=failures;
        if(failures) ++expected_recovered_pages;
        begin_page(&device,failures);
        assert(vh_audio_output_submit_recover(
            &ops,&stats,dst,frames)==0);
        assert(device.attempts_this_page==failures+1u);
        assert(stats.pages_submitted==block+1u);
        assert(spu.frames_rendered==old_spu);
        assert(resampler.input_frames==old_in);
        assert(resampler.next_output_tick==old_tick);
        assert(seq.note_ons==old_notes);
        assert(old_in==(uint64_t)(block+1u)*512u);
    }
    assert(device.accepted==64u);
    assert(device.checksum==expected_checksum);
    assert(stats.frames_submitted==expected_frames);
    assert(stats.frames_submitted==resampler.next_output_tick/44100u);
    assert(stats.pages_submitted==64u);
    assert(stats.recoveries==expected_recovered_pages);
    assert(stats.submit_failures==expected_failures);
    assert(stats.restart_attempts==expected_failures);
    assert(device.submissions==64u+expected_failures);
    assert(expected_recovered_pages>0u && expected_failures>0u);

    /* Three failed submissions exceed the two permitted restarts.
     * An external caller can later submit the same prepared page again,
     * but no SEQ/SPU/resampling is performed by the recovery helper.
     */
    const uint64_t old_clock=spu.frames_rendered;
    const uint64_t old_input=resampler.input_frames;
    const uint64_t old_pages=stats.pages_submitted;
    const uint64_t page_hash=hash_page(dst,557u);
    begin_page(&device,3u);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==-1);
    assert(device.attempts_this_page==3u);
    assert(stats.pages_submitted==old_pages);
    assert(hash_page(dst,557u)==page_hash);
    assert(spu.frames_rendered==old_clock);
    assert(resampler.input_frames==old_input);
    begin_page(&device,0u);
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==0);
    assert(stats.pages_submitted==old_pages+1u);

    /* Restart failure must never mark the rejected page as accepted. */
    begin_page(&device,1u);
    device.fail_stop=1;
    const uint64_t accepted=stats.pages_submitted;
    assert(vh_audio_output_submit_recover(&ops,&stats,dst,557u)==-1);
    assert(stats.pages_submitted==accepted);
    assert(spu.frames_rendered==old_clock);
    /* An unsuccessful stop/open/start cannot claim page delivery. */
    for(unsigned stage=0;stage<3u;stage++) {
        Mock broken={.opened=1,.playing=1};
        VhAudioOutputOps bad=callbacks(&broken);
        VhAudioOutputRecovery counts={0};
        begin_page(&broken,1u);
        broken.fail_stop=stage==0u;
        broken.fail_open=stage==1u;
        broken.fail_start=stage==2u;
        assert(vh_audio_output_submit_recover(
            &bad,&counts,dst,557u)==-1);
        assert(counts.pages_submitted==0u);
        assert(counts.frames_submitted==0u);
        assert(broken.submissions==1u);
        assert(spu.frames_rendered==old_clock);
        assert(resampler.input_frames==old_input);
    }
    /* HOME/sleep resume must not generate a new PCM page. */
    Mock paused={.opened=1,.playing=0};
    VhAudioOutputOps pause_ops=callbacks(&paused);
    VhAudioOutputRecovery pause_stats={0};
    const uint64_t old_notes=seq.note_ons;
    assert(vh_audio_output_resume_recover(&pause_ops,&pause_stats,1)==0);
    assert(paused.opened && paused.playing);
    assert(paused.opens==1u && paused.starts==1u);
    assert(pause_stats.pages_submitted==0u);
    assert(pause_stats.resume_recoveries==1u);
    assert(spu.frames_rendered==old_clock);
    assert(resampler.input_frames==old_input);
    assert(seq.note_ons==old_notes);
    /* Session-only fast focus path: exactly one start, no reopen
     * or PCM submission, including with an already nonzero page
     * count (user pauses after a successfully returned page). */
    Mock fast_resume={.opened=1,.playing=0};
    VhAudioOutputOps fast_ops=callbacks(&fast_resume);
    VhAudioOutputRecovery fast_stats={
        .pages_submitted=11u,.frames_submitted=6138u
    };
    assert(vh_audio_output_resume_recover(
        &fast_ops,&fast_stats,0)==0);
    assert(fast_resume.playing && fast_resume.starts==1u &&
           fast_resume.opens==0u && fast_resume.stops==0u &&
           fast_resume.submissions==0u);
    assert(fast_stats.pages_submitted==11u &&
           fast_stats.frames_submitted==6138u &&
           fast_stats.resume_restarts==0u &&
           fast_stats.resume_recoveries==0u &&
           fast_stats.resume_failures==0u);

    /* A transient fast-start failure must fall back to one bounded
     * reopen and still NEVER submit a PCM page. */
    Mock fallback={.opened=1,.playing=0,.fail_starts_left=1u};
    VhAudioOutputOps fallback_ops=callbacks(&fallback);
    VhAudioOutputRecovery fallback_stats={
        .pages_submitted=7u,.frames_submitted=3900u
    };
    assert(vh_audio_output_resume_recover(
        &fallback_ops,&fallback_stats,0)==0);
    assert(fallback.starts==2u && fallback.opens==1u &&
           fallback.stops==1u && fallback.closes==1u);
    assert(fallback_stats.resume_failures==1u &&
           fallback_stats.resume_restarts==1u &&
           fallback_stats.resume_recoveries==1u);
    assert(fallback_stats.pages_submitted==7u &&
           fallback_stats.frames_submitted==3900u &&
           fallback.submissions==0u);

    /* HOME/sleep forced reopen: initial open may fail, the second
     * restart can succeed, and neither touches the audio clock. */
    Mock transient_open={.opened=1,.playing=0,.fail_opens_left=1u};
    VhAudioOutputOps transient_ops=callbacks(&transient_open);
    VhAudioOutputRecovery transient_stats={0};
    assert(vh_audio_output_resume_recover(
        &transient_ops,&transient_stats,1)==0);
    assert(transient_open.opens==2u && transient_open.starts==1u &&
           transient_open.stops==2u && transient_open.closes==2u);
    assert(transient_stats.resume_failures==1u &&
           transient_stats.resume_restarts==2u &&
           transient_stats.resume_recoveries==1u &&
           transient_stats.pages_submitted==0u);

    for(unsigned scenario=0u;scenario<3u;scenario++) {
        Mock dead={.opened=1,.playing=0};
        VhAudioOutputOps dead_ops=callbacks(&dead);
        VhAudioOutputRecovery dead_stats={
            .pages_submitted=3u,.frames_submitted=1671u
        };
        dead.fail_stop=(scenario==0u);
        dead.fail_open=(scenario==1u);
        dead.fail_start=(scenario==2u);
        assert(vh_audio_output_resume_recover(
            &dead_ops,&dead_stats,1)==-1);
        assert(dead.submissions==0u);
        assert(dead_stats.pages_submitted==3u &&
               dead_stats.frames_submitted==1671u &&
               dead_stats.resume_recoveries==0u);
        if (scenario==0u) {
            assert(dead_stats.resume_restarts==0u &&
                   dead_stats.resume_failures==0u);
        } else {
            assert(dead_stats.resume_restarts==
                   VH_AUDIO_OUTPUT_RESTART_LIMIT);
            assert(dead_stats.resume_failures==
                   VH_AUDIO_OUTPUT_RESTART_LIMIT);
        }
    }

    /* Pre-callback accounting failure means no backend action
     * and no mutable stats (including pages) may change. */
    for(unsigned scenario=0u;scenario<4u;scenario++) {
        Mock guard={.opened=1,.playing=0};
        VhAudioOutputOps guard_ops=callbacks(&guard);
        VhAudioOutputRecovery guard_stats={
            .pages_submitted=13u,.frames_submitted=7241u
        };
        unsigned forced=1u;
        if (scenario==0u) guard_stats.resume_restarts=UINT_MAX;
        if (scenario==1u) guard_stats.resume_failures=UINT_MAX;
        if (scenario==2u) guard_stats.resume_recoveries=UINT_MAX;
        if (scenario==3u) {
            guard_stats.resume_recoveries=1u;
            forced=0u; /* contradictory pre-existing counters */
        }
        const VhAudioOutputRecovery saved=guard_stats;
        assert(vh_audio_output_resume_recover(
            &guard_ops,&guard_stats,(int)forced)==-1);
        assert(!memcmp(&guard_stats,&saved,sizeof saved));
        assert(guard.opens==0u && guard.starts==0u &&
               guard.stops==0u && guard.closes==0u &&
               guard.submissions==0u);
    }
    /* Saturated fast-resume failure counter also fails before start. */
    Mock fast_guard={.opened=1,.playing=0};
    VhAudioOutputOps fast_guard_ops=callbacks(&fast_guard);
    VhAudioOutputRecovery fast_guard_stats={
        .resume_failures=UINT_MAX
    };
    assert(vh_audio_output_resume_recover(
        &fast_guard_ops,&fast_guard_stats,0)==-1);
    assert(fast_guard.starts==0u);
    assert(fast_guard_stats.resume_failures==UINT_MAX);

    /* Interleave eight genuine returned logical pages with three
     * simulated HOME/focus/failed-resume intervals. The strict
     * backend history and cumulative PCM checksum must remain
     * unchanged during ALL resumes, then advance exactly once on
     * the next actually submitted page (with a failed/retried call
     * on one page to prove retry does not duplicate delivery).
     */
    Mock handoff={.opened=1,.playing=1,
                  .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps handoff_ops=callbacks(&handoff);
    VhAudioOutputRecovery handoff_stats={0};
    VhAudioSceneWaits handoff_waits={0};
    uint64_t wanted_hash=UINT64_C(1469598103934665603);
    const uint64_t hold_spu=spu.frames_rendered;
    const uint64_t hold_resampler=resampler.input_frames;
    const uint64_t hold_seq=seq.note_ons;
    for (unsigned k=0u;k<8u;k++) {
        int16_t handoff_pcm[16];
        for (unsigned z=0u;z<16u;z++)
            handoff_pcm[z]=(int16_t)((int)k*701+(int)z*37-3000);
        const VhAudioSubmitTiming page_before=handoff.timing;
        begin_page(&handoff,k==4u ? 1u : 0u);
        assert(vh_audio_output_submit_recover(
            &handoff_ops,&handoff_stats,handoff_pcm,8u)==0);
        assert(vh_audio_output_record_scene_page(
            &handoff_waits,&page_before,&handoff.timing,
            freq,8u,0,1)==0);
        wanted_hash=(wanted_hash ^ hash_page(handoff_pcm,8u))*
                    UINT64_C(1099511628211);
        assert(handoff.checksum==wanted_hash);
        assert(handoff.accepted==k+1u);
        assert(handoff_stats.pages_submitted==k+1u);
        assert(handoff_stats.frames_submitted==8u*(k+1u));
        if (k==1u || k==3u || k==5u) {
            /* Current descriptor was already returned; no restart
             * may resubmit it during an ordinary resume. */
            assert(handoff_ops.stop(handoff_ops.context)==0);
            const VhAudioSubmitTiming before_resume=handoff.timing;
            const VhAudioSceneWaits waits_before=handoff_waits;
            const unsigned calls_before=handoff.submissions;
            const unsigned accepted_before=handoff.accepted;
            const uint64_t checksum_before=handoff.checksum;
            const uint64_t pages_before=handoff_stats.pages_submitted;
            const uint64_t frames_before=handoff_stats.frames_submitted;
            if (k==1u) {
                assert(vh_audio_output_resume_recover(
                    &handoff_ops,&handoff_stats,0)==0);
            } else if (k==3u) {
                handoff.fail_opens_left=1u;
                assert(vh_audio_output_resume_recover(
                    &handoff_ops,&handoff_stats,1)==0);
            } else {
                handoff.fail_stop=1;
                assert(vh_audio_output_resume_recover(
                    &handoff_ops,&handoff_stats,1)==-1);
                handoff.fail_stop=0;
                assert(vh_audio_output_resume_recover(
                    &handoff_ops,&handoff_stats,1)==0);
            }
            assert(handoff.opened && handoff.playing);
            assert(handoff.submissions==calls_before);
            assert(handoff.accepted==accepted_before);
            assert(handoff.checksum==checksum_before);
            assert(handoff_stats.pages_submitted==pages_before);
            assert(handoff_stats.frames_submitted==frames_before);
            assert(!memcmp(&handoff.timing,&before_resume,
                           sizeof before_resume));
            assert(!memcmp(&handoff_waits,&waits_before,
                           sizeof waits_before));
            assert(spu.frames_rendered==hold_spu);
            assert(resampler.input_frames==hold_resampler);
            assert(seq.note_ons==hold_seq);
        }
    }
    assert(handoff.submissions==9u && handoff.accepted==8u);
    assert(handoff_stats.submit_failures==1u);
    assert(handoff_stats.restart_attempts==1u &&
           handoff_stats.recoveries==1u);
    assert(handoff_stats.resume_restarts==3u &&
           handoff_stats.resume_recoveries==2u &&
           handoff_stats.resume_failures==1u);
    assert(vh_audio_output_verify_run(
        &handoff_waits,&handoff_stats,&handoff.timing,
        8u,0u,8u,0u,1)==1);

    /* A saturated retry counter must fail BEFORE making a raw
     * audout call, preserving all stats and PCM buffer data. */
    for(unsigned k=0u;k<5u;k++) {
        Mock guarded={.opened=1,.playing=1};
        VhAudioOutputOps guarded_ops=callbacks(&guarded);
        VhAudioOutputRecovery guarded_stats={
            .pages_submitted=2u,.frames_submitted=16u
        };
        if (k==0u) guarded_stats.submit_failures=UINT_MAX;
        if (k==1u) {
            guarded_stats.submit_failures=UINT_MAX;
            guarded_stats.restart_attempts=UINT_MAX;
        }
        if (k==2u) {
            guarded_stats.submit_failures=UINT_MAX;
            guarded_stats.restart_attempts=UINT_MAX;
            guarded_stats.recoveries=UINT_MAX;
        }
        if (k==3u) {
            guarded_stats.restart_attempts=1u;
            guarded_stats.submit_failures=0u;
        }
        if (k==4u) {
            guarded_stats.recoveries=1u;
            guarded_stats.restart_attempts=0u;
        }
        int16_t unchanged_pcm[16]={1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
        const uint64_t before_hash=hash_page(unchanged_pcm,8u);
        const VhAudioOutputRecovery before=guarded_stats;
        assert(vh_audio_output_submit_recover(
            &guarded_ops,&guarded_stats,unchanged_pcm,8u)==-1);
        assert(guarded.submissions==0u && guarded.starts==0u &&
               guarded.opens==0u && guarded.stops==0u);
        assert(!memcmp(&guarded_stats,&before,sizeof before));
        assert(hash_page(unchanged_pcm,8u)==before_hash);
    }
    /* Boundary value: the first failed call is counted, but a
     * saturated failure counter MUST block the retry callback. */
    Mock at_limit={.opened=1,.playing=1};
    VhAudioOutputOps at_limit_ops=callbacks(&at_limit);
    VhAudioOutputRecovery at_limit_stats={
        .submit_failures=UINT_MAX-1u,
        .restart_attempts=1u,.recoveries=1u
    };
    begin_page(&at_limit,1u);
    assert(vh_audio_output_submit_recover(
        &at_limit_ops,&at_limit_stats,dst,8u)==-1);
    assert(at_limit_stats.submit_failures==UINT_MAX);
    assert(at_limit_stats.restart_attempts==1u);
    assert(at_limit.submissions==1u && at_limit.stops==0u);

    /* Two successive backend 'success' results release the WRONG
     * descriptor (foreign, then NULL). Model the submitted buffer
     * as still owned after both. Only a successful stop drains it.
     * Immediately pause and resume after eventual valid delivery;
     * no resume may retransmit that already delivered PCM page.
     */
    Mock ownership={.opened=1,.playing=1,
                    .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps ownership_ops=callbacks(&ownership);
    VhAudioOutputRecovery ownership_stats={0};
    VhAudioSceneWaits ownership_waits={0};
    int16_t owned_pcm[16];
    for(unsigned z=0u;z<16u;z++)
        owned_pcm[z]=(int16_t)(2000+(int)z*117);
    const uint64_t owned_hash=hash_page(owned_pcm,8u);
    const uint64_t stable_spu=spu.frames_rendered;
    const uint64_t stable_resample=resampler.input_frames;
    const uint64_t stable_seq=seq.note_ons;
    begin_page(&ownership,0u);
    ownership.mismatched_returns_left=1u;
    ownership.null_returns_left=1u;
    const VhAudioSubmitTiming ownership_before={0};
    assert(vh_audio_output_submit_recover(
        &ownership_ops,&ownership_stats,owned_pcm,8u)==0);
    assert(vh_audio_output_record_scene_page(
        &ownership_waits,&ownership_before,&ownership.timing,
        freq,8u,0,1)==0);
    assert(ownership.submissions==3u && ownership.accepted==1u);
    assert(ownership.flushed_unreleased==2u &&
           ownership.pending_unreleased==0u);
    assert(ownership_stats.pages_submitted==1u &&
           ownership_stats.submit_failures==2u &&
           ownership_stats.restart_attempts==2u &&
           ownership_stats.recoveries==1u);
    assert(ownership.page_pointer==owned_pcm &&
           ownership.page_hash==owned_hash);
    assert(hash_page(owned_pcm,8u)==owned_hash);

    /* Pause immediately after the successful recovered submission
     * and again straight after the first session resume. The page
     * fingerprint, service calls and music clocks stay unchanged. */
    const unsigned calls_before_pause=ownership.submissions;
    const unsigned accepted_before_pause=ownership.accepted;
    const uint64_t hash_before_pause=ownership.checksum;
    const VhAudioSubmitTiming timing_before_pause=ownership.timing;
    const VhAudioSceneWaits waits_before_pause=ownership_waits;
    assert(ownership_ops.stop(ownership_ops.context)==0);
    ownership.fail_opens_left=1u;
    assert(vh_audio_output_resume_recover(
        &ownership_ops,&ownership_stats,1)==0);
    assert(ownership_ops.stop(ownership_ops.context)==0);
    assert(vh_audio_output_resume_recover(
        &ownership_ops,&ownership_stats,0)==0);
    assert(ownership.submissions==calls_before_pause);
    assert(ownership.accepted==accepted_before_pause);
    assert(ownership.checksum==hash_before_pause);
    assert(ownership.pending_unreleased==0u &&
           ownership.flushed_unreleased==2u);
    assert(!memcmp(&ownership.timing,&timing_before_pause,
                   sizeof timing_before_pause));
    assert(!memcmp(&ownership_waits,&waits_before_pause,
                   sizeof waits_before_pause));
    assert(ownership_stats.pages_submitted==1u &&
           ownership_stats.frames_submitted==8u);
    assert(spu.frames_rendered==stable_spu);
    assert(resampler.input_frames==stable_resample);
    assert(seq.note_ons==stable_seq);

    /* Next explicitly produced page is different: it is delivered
     * exactly once; previously delivered page cannot be replayed by
     * focus/HOME restart. */
    int16_t next_owned_pcm[16];
    for(unsigned z=0u;z<16u;z++)
        next_owned_pcm[z]=(int16_t)(-3000+(int)z*103);
    const uint64_t second_hash=hash_page(next_owned_pcm,8u);
    const VhAudioSubmitTiming second_before=ownership.timing;
    begin_page(&ownership,0u);
    assert(vh_audio_output_submit_recover(
        &ownership_ops,&ownership_stats,next_owned_pcm,8u)==0);
    assert(vh_audio_output_record_scene_page(
        &ownership_waits,&second_before,&ownership.timing,
        freq,8u,0,1)==0);
    assert(ownership.submissions==4u && ownership.accepted==2u);
    assert(ownership.checksum==
           ((UINT64_C(1469598103934665603)^owned_hash)*
             UINT64_C(1099511628211)^second_hash)*
             UINT64_C(1099511628211));
    assert(ownership_stats.pages_submitted==2u &&
           ownership_stats.frames_submitted==16u);
    assert(vh_audio_output_verify_run(
        &ownership_waits,&ownership_stats,&ownership.timing,
        2u,0u,2u,0u,1)==1);
    assert(spu.frames_rendered==stable_spu);
    assert(resampler.input_frames==stable_resample);
    assert(seq.note_ons==stable_seq);

    /* If the initial stop fails while the descriptor is not yet
     * returned, it remains IN-FLIGHT and must not be closed or
     * resubmitted. Recovery is possible only after an explicit
     * successful drain, and never implicitly delivers a page. */
    Mock stalled={.opened=1,.playing=1,.fail_stop=1};
    VhAudioOutputOps stalled_ops=callbacks(&stalled);
    VhAudioOutputRecovery stalled_stats={0};
    VhAudioSceneWaits stalled_waits={0};
    begin_page(&stalled,0u);
    stalled.mismatched_returns_left=1u;
    const VhAudioSubmitTiming stalled_before={0};
    assert(vh_audio_output_submit_recover(
        &stalled_ops,&stalled_stats,owned_pcm,8u)==-1);
    assert(stalled.pending_unreleased==1u &&
           stalled.flushed_unreleased==0u);
    assert(stalled.submissions==1u && stalled.accepted==0u);
    assert(stalled.stops==1u && stalled.closes==0u &&
           stalled.opens==0u && stalled.starts==0u);
    assert(vh_audio_output_record_scene_page(
        &stalled_waits,&stalled_before,&stalled.timing,
        freq,8u,0,0)==0);
    assert(stalled_stats.pages_submitted==0u &&
           stalled_stats.submit_failures==1u);
    /* A second failed STOP must not grant ownership either. */
    assert(vh_audio_output_resume_recover(
        &stalled_ops,&stalled_stats,1)==-1);
    assert(stalled.pending_unreleased==1u &&
           stalled.closes==0u && stalled.submissions==1u);
    stalled.fail_stop=0;
    assert(stalled_ops.stop(stalled_ops.context)==0);
    assert(stalled.pending_unreleased==0u &&
           stalled.flushed_unreleased==1u);
    assert(vh_audio_output_resume_recover(
        &stalled_ops,&stalled_stats,1)==0);
    assert(stalled.submissions==1u && stalled.accepted==0u);
    assert(vh_audio_output_verify_run(
        &stalled_waits,&stalled_stats,&stalled.timing,
        0u,0u,1u,0u,0)==0);
    assert(hash_page(owned_pcm,8u)==owned_hash);

    /* Three failed stop attempts in a row: first inside failed page
     * recovery, two more in forced HOME/session recovery. A backend
     * "success" with foreign descriptor is STILL outstanding. Every
     * attempted reopen must be blocked until stop succeeds. */
    Mock held={.opened=1,.playing=1,
               .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps held_ops=callbacks(&held);
    VhAudioOutputRecovery held_stats={0};
    VhAudioSceneWaits held_waits={0};
    int16_t held_first[16], held_rejected[16], held_next[16];
    for(unsigned i=0u;i<16u;i++) {
        held_first[i]=(int16_t)(1150+(int)i*101);
        held_rejected[i]=(int16_t)(-2500+(int)i*79);
        held_next[i]=(int16_t)(3200-(int)i*63);
    }
    const uint64_t held_first_hash=hash_page(held_first,8u);
    const uint64_t held_next_hash=hash_page(held_next,8u);
    const uint64_t held_clock=spu.frames_rendered;
    const uint64_t held_input=resampler.input_frames;
    const uint64_t held_notes=seq.note_ons;
    begin_page(&held,0u);
    const VhAudioSubmitTiming held_first_before=held.timing;
    assert(vh_audio_output_submit_recover(
        &held_ops,&held_stats,held_first,8u)==0);
    assert(vh_audio_output_record_scene_page(
        &held_waits,&held_first_before,&held.timing,freq,8u,0,1)==0);
    assert(held.accepted==1u && held.submissions==1u);
    const uint64_t held_checksum=held.checksum;
    assert(held_checksum==
           (UINT64_C(1469598103934665603)^held_first_hash)*
            UINT64_C(1099511628211));

    /* A foreign descriptor is not release. The next three stop
     * callbacks ALL fail (one page retry + two forced resumes). */
    begin_page(&held,0u);
    held.mismatched_returns_left=1u;
    held.fail_stops_left=3u;
    const uint64_t rejected_hash=hash_page(held_rejected,8u);
    const VhAudioSubmitTiming held_reject_before=held.timing;
    assert(vh_audio_output_submit_recover(
        &held_ops,&held_stats,held_rejected,8u)==-1);
    assert(vh_audio_output_record_scene_page(
        &held_waits,&held_reject_before,&held.timing,
        freq,8u,0,0)==0);
    assert(held.pending_unreleased==1u);
    assert(held.fail_stops_left==2u);
    assert(held.accepted==1u && held.submissions==2u);
    assert(held.stops==1u && held.closes==0u);
    assert(held_stats.pages_submitted==1u &&
           held_stats.frames_submitted==8u &&
           held_stats.submit_failures==1u &&
           held_stats.restart_attempts==0u);
    const VhAudioOutputRecovery held_pre_resume=held_stats;
    const VhAudioSubmitTiming held_raw_before=held.timing;
    const VhAudioSceneWaits held_page_before=held_waits;

    for(unsigned attempt=0u;attempt<2u;attempt++) {
        assert(vh_audio_output_resume_recover(
            &held_ops,&held_stats,1)==-1);
        assert(held.pending_unreleased==1u);
        assert(held.fail_stops_left==1u-attempt);
        assert(held.stops==2u+attempt);
        assert(held.closes==0u && held.opens==0u &&
               held.starts==0u && held.flushed_unreleased==0u);
        assert(held.accepted==1u && held.submissions==2u);
        assert(held.checksum==held_checksum);
        assert(!memcmp(&held_stats,&held_pre_resume,
                       sizeof held_pre_resume));
        assert(!memcmp(&held.timing,&held_raw_before,
                       sizeof held_raw_before));
        assert(!memcmp(&held_waits,&held_page_before,
                       sizeof held_page_before));
        assert(hash_page(held_rejected,8u)==rejected_hash);
        assert(spu.frames_rendered==held_clock &&
               resampler.input_frames==held_input &&
               seq.note_ons==held_notes);
    }

    /* The FOURTH stop now succeeds and is the ONLY event that can
     * release the outstanding buffer. Reopening itself never
     * requeues the previously failed page. */
    assert(vh_audio_output_resume_recover(
        &held_ops,&held_stats,1)==0);
    assert(held.fail_stops_left==0u);
    assert(held.stops==4u && held.closes==1u &&
           held.opens==1u && held.starts==1u);
    assert(held.pending_unreleased==0u &&
           held.flushed_unreleased==1u);
    assert(held.accepted==1u && held.submissions==2u);
    assert(held.checksum==held_checksum);
    assert(held_stats.resume_restarts==1u &&
           held_stats.resume_recoveries==1u &&
           held_stats.resume_failures==0u);
    assert(held_stats.pages_submitted==1u &&
           held_stats.frames_submitted==8u);
    assert(!memcmp(&held.timing,&held_raw_before,
                   sizeof held_raw_before));
    assert(!memcmp(&held_waits,&held_page_before,
                   sizeof held_page_before));

    /* Pause and resume AGAIN before rendering the next page: no
     * stale descriptor is submitted, regardless of focus mode. */
    assert(held_ops.stop(held_ops.context)==0);
    const unsigned held_raw_calls=held.submissions;
    const uint64_t held_accepted_hash=held.checksum;
    assert(vh_audio_output_resume_recover(
        &held_ops,&held_stats,0)==0);
    assert(held.submissions==held_raw_calls &&
           held.accepted==1u &&
           held.checksum==held_accepted_hash);
    assert(held.pending_unreleased==0u &&
           held.flushed_unreleased==1u);

    /* A fresh, distinct PCM page may now be delivered exactly once
     * without replaying the rejected or earlier returned page. */
    begin_page(&held,0u);
    const VhAudioSubmitTiming held_next_before=held.timing;
    assert(vh_audio_output_submit_recover(
        &held_ops,&held_stats,held_next,8u)==0);
    assert(vh_audio_output_record_scene_page(
        &held_waits,&held_next_before,&held.timing,freq,8u,0,1)==0);
    assert(held.accepted==2u && held.submissions==3u);
    assert(held.checksum==
           (held_checksum^held_next_hash)*
            UINT64_C(1099511628211));
    assert(held_stats.pages_submitted==2u &&
           held_stats.frames_submitted==16u);
    assert(held_stats.submit_failures==1u &&
           held_stats.restart_attempts==0u);
    assert(held_waits.ordinary.pages==3u &&
           held_waits.ordinary.failed_pages==1u);
    assert(vh_audio_output_verify_run(
        &held_waits,&held_stats,&held.timing,
        2u,0u,3u,0u,0)==0);
    assert(hash_page(held_rejected,8u)==rejected_hash);
    assert(spu.frames_rendered==held_clock &&
           resampler.input_frames==held_input &&
           seq.note_ons==held_notes);

    /* Final cleanup cannot close until stop has truly released the
     * descriptor. Even an already-recovered service obeys this. */
    Mock teardown={.opened=1,.playing=1,.fail_stops_left=2u};
    VhAudioOutputOps teardown_ops=callbacks(&teardown);
    for(unsigned i=0u;i<2u;i++) {
        assert(vh_audio_output_stop_close(&teardown_ops)==-1);
        assert(teardown.stops==i+1u && teardown.closes==0u);
        assert(teardown.opened && teardown.playing);
    }
    assert(vh_audio_output_stop_close(&teardown_ops)==0);
    assert(teardown.stops==3u && teardown.closes==1u);
    assert(!teardown.opened && !teardown.playing);
    assert(vh_audio_output_stop_close(NULL)==-1);
    const VhAudioOutputOps missing_stop={
        NULL,NULL,NULL,NULL,NULL,NULL
    };
    assert(vh_audio_output_stop_close(&missing_stop)==-1);

    /* Repeatedly failing even AFTER a late stage retry is never
     * allowed to close an outstanding descriptor. If all calls to
     * resume stop continue to fail, no page can be marked returned;
     * the underlying mock remains intentionally unrecovered. */
    Mock persistent={.opened=1,.playing=1,
                     .fail_stops_left=6u};
    VhAudioOutputOps persist_ops=callbacks(&persistent);
    VhAudioOutputRecovery persist_stats={0};
    begin_page(&persistent,0u);
    persistent.mismatched_returns_left=1u;
    assert(vh_audio_output_submit_recover(
        &persist_ops,&persist_stats,held_rejected,8u)==-1);
    assert(persistent.pending_unreleased==1u);
    for(unsigned i=0u;i<5u;i++) {
        assert(vh_audio_output_resume_recover(
            &persist_ops,&persist_stats,1)==-1);
        assert(persistent.pending_unreleased==1u);
        assert(persistent.submissions==1u &&
               persistent.accepted==0u &&
               persistent.closes==0u &&
               persistent.opens==0u &&
               persistent.starts==0u);
        assert(persist_stats.pages_submitted==0u &&
               persist_stats.resume_recoveries==0u &&
               persist_stats.resume_restarts==0u);
    }
    assert(persistent.stops==6u);
    assert(persistent.fail_stops_left==0u);
    assert(persistent.flushed_unreleased==0u);
    /* Combine bank switching and blocking audout page ownership.
     * Unlike the previous single-bank test, this one changes the
     * borrowed voice sample arena between 6 eight-block scenes.
     * No switch or PCM overwrite occurs before the mock reports
     * release of the exact previous page, including after failures.
     */
    for (unsigned i=0;i<128u;i++)
        alternate_sample[i]=(int16_t)(6000-(int)i*127);
    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_reverb(&spu,1,.5f)==0);
    vh_audio_resample_reset(&resampler);
    assert(vh_native_seq_init(&seq,song,sizeof song,&spu,resolve,
                              sample,0)==0);
    Mock switching={.opened=1,.playing=1,
                    .checksum=UINT64_C(1469598103934665603)};
    VhAudioOutputOps switch_ops=callbacks(&switching);
    VhAudioOutputRecovery switch_stats={0};
    VhAudioSceneWaits measured_pages={0};
    uint64_t check_hash=UINT64_C(1469598103934665603);
    uint64_t frame_count=0;
    unsigned switch_count=0, extra_submits=0, recovered_pages=0;
    for (unsigned block=0;block<48u;block++) {
        if (block && block%8u==0u) {
            /* Submissions are synchronous: all previous page memory
             * must already have returned to the caller.
             */
            assert(switching.accepted==block);
            assert(switch_stats.pages_submitted==block);
            assert(switching.page_pointer==dst);
            assert(switching.attempts_this_page>=1u);
            const uint64_t old_input=resampler.input_frames;
            const uint64_t old_tick=resampler.next_output_tick;
            memcpy(&history_before_switch,&spu.reverb,
                   sizeof(history_before_switch));
            const int16_t *new_source=(block/8u)%2u
                ? alternate_sample : sample;
            assert(vh_native_seq_switch_scene(&seq,song,sizeof song,&spu,
                       resolve,(void *)new_source,0)==0);
            assert(!memcmp(&spu.reverb,&history_before_switch,
                           sizeof(history_before_switch)));
            assert(resampler.input_frames==old_input);
            assert(resampler.next_output_tick==old_tick);
            assert(seq.context==new_source);
            assert(spu.frames_rendered==0u);
            for (unsigned slot=0;slot<VH_NATIVE_MUSIC_VOICES;slot++) {
                assert(!spu.voice[slot].active);
                assert(spu.voice[slot].pcm==NULL);
            }
            ++switch_count;
        }
        assert(vh_native_seq_advance_block(&seq)>=0);
        vh_native_spu_render(&spu,src,512u);
        const size_t frames=vh_audio_resample_process(
            &resampler,src,512u,dst,640u);
        assert(frames>=555u && frames<=559u);
        const uint64_t hash=hash_page(dst,frames);
        check_hash=(check_hash^hash)*UINT64_C(1099511628211);
        frame_count+=frames;
        const uint64_t old_input=resampler.input_frames;
        const uint64_t old_tick=resampler.next_output_tick;
        const uint64_t old_voice_time=spu.frames_rendered;
        const uint64_t old_notes=seq.note_ons;
        /* Force recovery on the first page of new scenes 3 and 5,
         * not just ordinary pages between bank changes.
         */
        begin_page(&switching,(block%19u==7u || block==16u) ? 1u : 0u);
        switching.mismatched_returns_left=(block%13u==5u || block==32u);
        switching.null_returns_left=(block%17u==11u);
        const unsigned failures=switching.failures_left+
            switching.mismatched_returns_left+switching.null_returns_left;
        const VhAudioSubmitTiming before_page=switching.timing;
        extra_submits+=failures;
        recovered_pages+=(failures!=0u);
        assert(vh_audio_output_submit_recover(&switch_ops,&switch_stats,
                                              dst,frames)==0);
        const int boundary=block && block%8u==0u;
        assert(vh_audio_output_record_scene_page(
                   &measured_pages,&before_page,&switching.timing,
                   freq,frames,boundary,1)==0);
        assert(switching.accepted==block+1u);
        assert(switch_stats.pages_submitted==block+1u);
        assert(switching.attempts_this_page==failures+1u);
        assert(hash_page(dst,frames)==hash);
        assert(resampler.input_frames==old_input);
        assert(resampler.next_output_tick==old_tick);
        assert(spu.frames_rendered==old_voice_time);
        assert(seq.note_ons==old_notes);
    }
    assert(switch_count==5u);
    assert(switching.accepted==48u);
    assert(switching.submissions==48u+extra_submits);
    assert(switching.timing.calls==switching.submissions);
    assert(switching.timing.failed_submissions==extra_submits);
    assert(switching.timing.waits_longer_than_page>0u);
    assert(switching.timing.max_ticks==250000u);
    assert(measured_pages.first_after_switch.pages==5u);
    assert(measured_pages.ordinary.pages==43u);
    assert(measured_pages.first_after_switch.failed_pages==0u);
    assert(measured_pages.ordinary.failed_pages==0u);
    assert(measured_pages.first_after_switch.retried_pages==2u);
    assert(measured_pages.ordinary.retried_pages==recovered_pages-2u);
    assert(measured_pages.first_after_switch.total_ticks+
           measured_pages.ordinary.total_ticks==switching.timing.total_ticks);
    assert(measured_pages.first_after_switch.retried_pages+
           measured_pages.ordinary.retried_pages==recovered_pages);
    assert(measured_pages.first_after_switch.slow_pages+
           measured_pages.ordinary.slow_pages>0u);
    assert(measured_pages.first_after_switch.peak_page_ticks>0u);
    assert(measured_pages.ordinary.peak_page_ticks>0u);
    assert(switching.checksum==check_hash);
    assert(switch_stats.frames_submitted==frame_count);
    assert(switch_stats.pages_submitted==48u);
    assert(switch_stats.submit_failures==extra_submits);
    assert(switch_stats.restart_attempts==extra_submits);
    assert(switch_stats.recoveries==recovered_pages);
    assert(extra_submits>0u && recovered_pages>0u);
    assert(resampler.input_frames==48u*512u);
    assert(frame_count==((48u*512u-1u)*48000u)/44100u+1u);
    assert(resampler.next_output_tick==frame_count*44100u);
    /* A successful test is only eligible for FULL once all returned
     * PCM pages, synthetic scene changes and service waits reconcile.
     * The same facts are INCOMPLETE when the requested duration is
     * longer, or when a human stops the test early.
     */
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==1);
    VhAudioOutputRecovery invalid_resume=switch_stats;
    invalid_resume.resume_recoveries=1u; /* no restart observed */
    assert(vh_audio_output_verify_run(
        &measured_pages,&invalid_resume,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,64u,8u,1)==0);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,48u,8u,0)==0);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,4u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        48u,5u,48u,0u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&switching.timing,
        47u,5u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        NULL,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,NULL,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,NULL,
        48u,5u,48u,8u,1)==-1);
    VhAudioSceneWaits altered=measured_pages;
    altered.first_after_switch.pages=6u;
    assert(vh_audio_output_verify_run(
        &altered,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    altered=measured_pages;
    altered.ordinary.total_ticks++;
    assert(vh_audio_output_verify_run(
        &altered,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    altered=measured_pages;
    altered.ordinary.failed_pages=altered.ordinary.pages+1u;
    assert(vh_audio_output_verify_run(
        &altered,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    altered=measured_pages;
    altered.first_after_switch.wait_gt_4pages++;
    assert(vh_audio_output_verify_run(
        &altered,&switch_stats,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    VhAudioOutputRecovery altered_recovery=switch_stats;
    assert(switch_stats.recoveries>0u);
    --altered_recovery.recoveries;
    /* A full successful run cannot hide a retried page whose
     * recovery was omitted from the independent backend counters. */
    assert(vh_audio_output_verify_run(
        &measured_pages,&altered_recovery,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    altered_recovery=switch_stats;
    altered_recovery.pages_submitted++;
    assert(vh_audio_output_verify_run(
        &measured_pages,&altered_recovery,&switching.timing,
        48u,5u,48u,8u,1)==-1);
    VhAudioSubmitTiming altered_timing=switching.timing;
    altered_timing.failed_submissions++;
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&altered_timing,
        48u,5u,48u,8u,1)==-1);
    /* A hidden extra audout call used to pass the >=logical_pages
     * guard: even if every page/wait sum is otherwise unchanged,
     * raw calls MUST equal successful pages + failed submissions.
     * This catches orphan calls without guessing audible effects.
     */
    altered_timing=switching.timing;
    ++altered_timing.calls;
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&altered_timing,
        48u,5u,48u,8u,1)==-1);
    altered_timing=switching.timing;
    --altered_timing.calls;
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&altered_timing,
        48u,5u,48u,8u,1)==-1);
    altered_timing=switching.timing;
    altered_timing.calls=UINT64_MAX;
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&altered_timing,
        48u,5u,48u,8u,1)==-1);
    altered_timing=switching.timing;
    altered_timing.waits_longer_than_page=altered_timing.calls+1u;
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&altered_timing,
        48u,5u,48u,8u,1)==-1);
    altered_timing=switching.timing;
    const uint64_t boundary_peak=measured_pages.first_after_switch.peak_page_ticks;
    const uint64_t ordinary_peak=measured_pages.ordinary.peak_page_ticks;
    altered_timing.max_ticks=(boundary_peak>ordinary_peak
                              ? boundary_peak : ordinary_peak)+1u;
    assert(vh_audio_output_verify_run(
        &measured_pages,&switch_stats,&altered_timing,
        48u,5u,48u,8u,1)==-1);
    /* A failed logical page is accounted for without ever claiming
     * that the audio service returned a usable PCM page.
     */
    VhAudioSceneWaits aborted={0};
    aborted.ordinary.pages=1u;
    aborted.ordinary.failed_pages=1u;
    aborted.ordinary.total_ticks=100u;
    aborted.ordinary.peak_page_ticks=100u;
    aborted.ordinary.wait_le_page=1u;
    aborted.ordinary.failed_in_band[0]=1u;
    VhAudioOutputRecovery aborted_recovery={.submit_failures=1u};
    VhAudioSubmitTiming aborted_timing={
        .calls=1u,.total_ticks=100u,.max_ticks=100u,
        .failed_submissions=1u};
    assert(vh_audio_output_verify_run(
        &aborted,&aborted_recovery,&aborted_timing,
        0u,0u,48u,8u,0)==0);
    /* Even a terminal failed page must count every failed call, and
     * the page bucket cannot hide an additional service invocation. */
    aborted_timing.calls=2u;
    assert(vh_audio_output_verify_run(
        &aborted,&aborted_recovery,&aborted_timing,
        0u,0u,48u,8u,0)==-1);
    aborted_timing.calls=1u;
    /* A fully failed sequence can include multiple raw service
     * failures on its one logical page (up to the retry cap). */
    aborted_timing.calls=3u;
    aborted_timing.failed_submissions=3u;
    aborted_recovery.submit_failures=3u;
    aborted_recovery.restart_attempts=2u;
    aborted.ordinary.retried_pages=1u;
    assert(vh_audio_output_verify_run(
        &aborted,&aborted_recovery,&aborted_timing,
        0u,0u,48u,8u,0)==0);
    aborted_timing=(VhAudioSubmitTiming){
        .calls=1u,.total_ticks=100u,.max_ticks=100u,
        .failed_submissions=1u};
    aborted_recovery.submit_failures=1u;
    aborted_recovery.restart_attempts=0u;
    aborted.ordinary.retried_pages=0u;
    /* A user-owned bank is never automatically switched; the same
     * class of observations is valid only with zero boundary pages.
     */
    VhAudioSceneWaits sd_pages={0};
    sd_pages.ordinary.pages=2u;
    sd_pages.ordinary.total_ticks=200u;
    sd_pages.ordinary.peak_page_ticks=100u;
    sd_pages.ordinary.wait_le_page=2u;
    VhAudioOutputRecovery sd_recovery={.pages_submitted=2u};
    VhAudioSubmitTiming sd_timing={
        .calls=2u,.total_ticks=200u,.max_ticks=100u};
    assert(vh_audio_output_verify_run(
        &sd_pages,&sd_recovery,&sd_timing,2u,0u,2u,0u,1)==1);
    assert(vh_audio_output_verify_run(
        &sd_pages,&sd_recovery,&sd_timing,2u,1u,2u,0u,1)==-1);

    printf("audout recovery: %u accepted pages, %u restarts, clock stable PASS\n",
           device.accepted,stats.restart_attempts);
    return 0;
}
