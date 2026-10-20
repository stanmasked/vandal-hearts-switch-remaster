/* Ownership of one aligned audout PCM page, including wrong/reordered
 * releases, partial PlayBuffer failures, stop versus full-session close.
 * libnx audoutPlayBuffer waits for SOME released buffer, so a foreign
 * release must not make this page writable again.
 */
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_audio_buffer_lease.h"
#include "vh_audio_output_recovery.h"

typedef struct {
    VhAudioBufferLease lease;
    int opened, playing;
    unsigned inject_foreign, inject_submit_failure;
    unsigned submits, stops, closes, opens, starts, accepted;
    unsigned wrong_token, actual_token;
    const int16_t *first_pcm;
    size_t first_frames;
    uint64_t first_digest;
} FakeDevice;

static uint64_t digest(const int16_t *pcm,size_t frames) {
    uint64_t h=UINT64_C(1469598103934665603);
    for(size_t i=0;i<frames*2u;i++) {
        h^=(uint16_t)pcm[i];
        h*=UINT64_C(1099511628211);
    }
    return h;
}
static int submit(void *ctx,const int16_t *pcm,size_t frames) {
    FakeDevice *d=ctx;
    assert(d->opened && d->playing && frames);
    assert(!vh_audio_buffer_lease_begin(&d->lease,&d->actual_token));
    ++d->submits;
    if(!d->first_pcm) {
        d->first_pcm=pcm; d->first_frames=frames;
        d->first_digest=digest(pcm,frames);
    } else {
        assert(d->first_pcm==pcm && d->first_frames==frames);
        assert(d->first_digest==digest(pcm,frames));
    }
    if(d->inject_submit_failure) {
        --d->inject_submit_failure;
        /* Device might have accepted the page before reporting error.
         * Until the session is closed the descriptor remains leased. */
        return -1;
    }
    if(d->inject_foreign) {
        --d->inject_foreign;
        assert(vh_audio_buffer_lease_release(
            &d->lease,&d->wrong_token)==-1);
        assert(d->lease.in_flight==&d->actual_token);
        return -1;
    }
    if(vh_audio_buffer_lease_release(&d->lease,&d->actual_token))
        return -1;
    ++d->accepted;
    return 0;
}
static int stop(void *ctx) {
    FakeDevice *d=ctx;
    ++d->stops;
    d->playing=0;
    /* A stopped service is NOT proof of released buffers. */
    return 0;
}
static void close_session(void *ctx) {
    FakeDevice *d=ctx;
    ++d->closes;
    d->opened=0;d->playing=0;
    vh_audio_buffer_lease_session_closed(&d->lease);
}
static int open_session(void *ctx) {
    FakeDevice *d=ctx;
    assert(!d->opened && !d->lease.in_flight);
    d->opened=1;++d->opens;return 0;
}
static int start(void *ctx) {
    FakeDevice *d=ctx;
    assert(d->opened && !d->playing);
    d->playing=1;++d->starts;return 0;
}
static VhAudioOutputOps callbacks(FakeDevice *d) {
    VhAudioOutputOps ops={d,submit,stop,close_session,
                          open_session,start};
    return ops;
}
static void test_exact_release_ownership(void) {
    VhAudioBufferLease lease={0};
    int a=0,b=0;
    assert(vh_audio_buffer_lease_begin(NULL,&a)==-1);
    assert(vh_audio_buffer_lease_begin(&lease,NULL)==-1);
    assert(vh_audio_buffer_lease_release(&lease,&a)==-1);
    assert(vh_audio_buffer_lease_begin(&lease,&a)==0);
    assert(vh_audio_buffer_lease_begin(&lease,&b)==-1);
    assert(vh_audio_buffer_lease_release(&lease,NULL)==-1);
    assert(vh_audio_buffer_lease_release(&lease,&b)==-1);
    assert(lease.mismatched_releases==2);
    assert(lease.in_flight==&a && lease.pages_released==0);
    assert(vh_audio_buffer_lease_release(&lease,&a)==0);
    assert(lease.in_flight==NULL && lease.pages_released==1);
    assert(lease.pages_leased==1 && lease.busy_begin_rejections==1);
    assert(vh_audio_buffer_lease_release(&lease,&a)==-1);
    assert(vh_audio_buffer_lease_begin(&lease,&b)==0);
    assert(vh_audio_buffer_lease_release(&lease,&a)==-1);
    assert(vh_audio_buffer_lease_begin(&lease,&a)==-1);
    vh_audio_buffer_lease_session_closed(&lease);
    assert(lease.in_flight==NULL && lease.abandoned_sessions==1);
    assert(lease.pages_released==1);
    assert(vh_audio_buffer_lease_begin(&lease,&a)==0);
    assert(vh_audio_buffer_lease_release(&lease,&a)==0);
    assert(lease.pages_released==2);
    assert(lease.pages_leased==3 && lease.busy_begin_rejections==2);
    vh_audio_buffer_lease_session_closed(&lease);
    assert(lease.abandoned_sessions==1);
    vh_audio_buffer_lease_session_closed(NULL);
}
static void test_stale_releases_and_restarts(void) {
    int16_t pcm[32];
    for(unsigned i=0;i<32;i++) pcm[i]=(int16_t)(i*707-11000);
    FakeDevice dev={.opened=1,.playing=1};
    VhAudioOutputOps ops=callbacks(&dev);
    VhAudioOutputRecovery stats={0};
    dev.inject_foreign=1;
    assert(vh_audio_output_submit_recover(&ops,&stats,pcm,16)==0);
    assert(dev.submits==2 && dev.accepted==1);
    assert(dev.closes==1 && dev.opens==1 && dev.starts==1);
    assert(dev.lease.mismatched_releases==1);
    assert(dev.lease.abandoned_sessions==1);
    assert(dev.lease.in_flight==NULL && dev.lease.pages_released==1);
    assert(stats.pages_submitted==1 && stats.recoveries==1);
    assert(stats.frames_submitted==16);
    dev.inject_submit_failure=1;
    assert(vh_audio_output_submit_recover(&ops,&stats,pcm,16)==0);
    assert(dev.submits==4 && dev.accepted==2);
    assert(dev.lease.abandoned_sessions==2);
    assert(stats.pages_submitted==2 && stats.recoveries==2);
    /* Multiple mismatches must exhaust the bounded retry limit,
     * not clear a descriptor and submit a second page to same queue. */
    dev.inject_foreign=3;
    assert(vh_audio_output_submit_recover(&ops,&stats,pcm,16)==-1);
    assert(dev.submits==7 && dev.accepted==2);
    assert(dev.lease.in_flight==&dev.actual_token);
    assert(dev.lease.mismatched_releases==4);
    assert(dev.lease.abandoned_sessions==4);
    assert(stats.pages_submitted==2 && stats.frames_submitted==32);
    assert(vh_audio_buffer_lease_begin(
        &dev.lease,&dev.wrong_token)==-1);
    /* Stop alone does NOT return ownership of this PCM page. */
    assert(!stop(&dev));
    assert(dev.lease.in_flight==&dev.actual_token);
    close_session(&dev);
    assert(dev.lease.in_flight==NULL);
    assert(dev.lease.abandoned_sessions==5);
    assert(!open_session(&dev) && !start(&dev));
    assert(!vh_audio_output_submit_recover(&ops,&stats,pcm,16));
    assert(dev.accepted==3);
    assert(dev.lease.pages_released==3);
}

static void test_stage346_counter_saturation(void) {
    int a=0,b=0;
    VhAudioBufferLease lease={0};
    assert(vh_audio_buffer_lease_begin(&lease,NULL)==-1);
    assert(!lease.pages_leased && !lease.busy_begin_rejections);
    lease.pages_leased=UINT64_MAX-1u;
    lease.busy_begin_rejections=UINT_MAX-1u;
    assert(!vh_audio_buffer_lease_begin(&lease,&a));
    assert(lease.pages_leased==UINT64_MAX);
    assert(vh_audio_buffer_lease_begin(&lease,&b)==-1);
    assert(vh_audio_buffer_lease_begin(&lease,&b)==-1);
    assert(lease.busy_begin_rejections==UINT_MAX);
    assert(vh_audio_buffer_lease_release(&lease,&b)==-1);
    assert(lease.in_flight==&a);
    assert(!vh_audio_buffer_lease_release(&lease,&a));
    assert(!vh_audio_buffer_lease_begin(&lease,&b));
    assert(lease.pages_leased==UINT64_MAX);
    assert(!vh_audio_buffer_lease_release(&lease,&b));
}
int main(void) {
    test_stage346_counter_saturation();
    test_exact_release_ownership();
    test_stale_releases_and_restarts();
    puts("strict audout PCM lease: matching releases, stale queue, "
         "bounded retry and session close PASS");
    return 0;
}
