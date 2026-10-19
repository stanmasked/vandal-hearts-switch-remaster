/* Stage345: long-running host-only audout PCM ownership and continuity model.
 * Source production logic is unchanged; simulate transport ownership,
 * wrong descriptor releases, partial failures and bounded restarts.
 * Not a hardware Switch DAC/queue observation or audio fidelity proof.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_audio_buffer_lease.h"
#include "vh_audio_output_recovery.h"
#include "vh_audio_resample.h"

#define PAGES 512u
#define MAX_FRAMES VH_AUDIO_RESAMPLE_MAX_FRAMES
#define FNV_INIT UINT64_C(1469598103934665603)
#define FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    VhAudioBufferLease lease;
    unsigned real_token, foreign_token;
    unsigned opened, playing, attempts, fail_left;
    unsigned calls, stops, closes, opens, starts, accepted_pages;
    size_t expected_frames;
    const int16_t *expected_pointer;
    uint64_t expected_hash, accepted_rolling;
    uint64_t accepted_frames;
} Model;

static uint64_t hash_page(const int16_t *p, size_t n) {
    uint64_t h=FNV_INIT;
    for(size_t i=0;i<2u*n;i++) {
        h^=(uint16_t)p[i];
        h*=FNV_PRIME;
    }
    return h;
}
static uint64_t hash_append(uint64_t h,const int16_t *p,size_t n) {
    for(size_t i=0;i<2u*n;i++) {
        h^=(uint16_t)p[i];
        h*=FNV_PRIME;
    }
    return h;
}
static int model_submit(void *opaque,const int16_t *pcm,size_t frames) {
    Model *m=opaque;
    assert(m->opened && m->playing);
    assert(pcm==m->expected_pointer && frames==m->expected_frames);
    assert(hash_page(pcm,frames)==m->expected_hash);
    /* Never submit a new buffer while the previous exact descriptor
     * is owned by the service; an incorrect release may not free it. */
    assert(!vh_audio_buffer_lease_begin(&m->lease,&m->real_token));
    ++m->calls;
    ++m->attempts;
    if(m->fail_left) {
        --m->fail_left;
        if(m->attempts%2u==1u) {
            assert(vh_audio_buffer_lease_release(&m->lease,&m->foreign_token)==-1);
            assert(m->lease.in_flight==&m->real_token);
            assert(vh_audio_buffer_lease_begin(&m->lease,&m->foreign_token)==-1);
        }
        /* Failure may occur after the page was queued; the page
         * remains immutable and owned through stop, until close. */
        assert(m->lease.in_flight==&m->real_token);
        return -1;
    }
    assert(vh_audio_buffer_lease_release(&m->lease,&m->real_token)==0);
    assert(!m->lease.in_flight);
    m->accepted_rolling=hash_append(m->accepted_rolling,pcm,frames);
    m->accepted_frames+=frames;
    ++m->accepted_pages;
    return 0;
}
static int model_stop(void *opaque) {
    Model *m=opaque;
    assert(m->opened && m->playing);
    ++m->stops;
    m->playing=0;
    /* Stop alone does not grant writable ownership. */
    assert(m->lease.in_flight==&m->real_token);
    return 0;
}
static void model_close(void *opaque) {
    Model *m=opaque;
    assert(m->opened && !m->playing);
    ++m->closes;
    m->opened=0;
    vh_audio_buffer_lease_session_closed(&m->lease);
    assert(!m->lease.in_flight);
}
static int model_open(void *opaque) {
    Model *m=opaque;
    assert(!m->opened && !m->lease.in_flight);
    ++m->opens;
    m->opened=1;
    return 0;
}
static int model_start(void *opaque) {
    Model *m=opaque;
    assert(m->opened && !m->playing && !m->lease.in_flight);
    ++m->starts;
    m->playing=1;
    return 0;
}
static VhAudioOutputOps model_ops(Model *m) {
    return (VhAudioOutputOps){m,model_submit,model_stop,model_close,
                              model_open,model_start};
}
static void make_page(int16_t *pcm,size_t frames,unsigned serial) {
    for(size_t i=0;i<frames;i++) {
        uint32_t seed=serial*UINT32_C(2654435761)+(uint32_t)i*UINT32_C(2246822519);
        pcm[2u*i]=(int16_t)(uint16_t)(seed>>12);
        pcm[2u*i+1u]=(int16_t)(uint16_t)((seed>>3)^UINT32_C(0x5a5a));
    }
}
static void select_page(Model *m,int16_t *pcm,size_t frames,
                        unsigned serial,unsigned failed_attempts) {
    assert(!m->lease.in_flight);
    make_page(pcm,frames,serial);
    m->expected_pointer=pcm;
    m->expected_frames=frames;
    m->expected_hash=hash_page(pcm,frames);
    m->attempts=0;
    m->fail_left=failed_attempts;
}
static void continuous_pages(void) {
    static int16_t pcm[MAX_FRAMES*2u];
    Model m={.opened=1,.playing=1,.accepted_rolling=FNV_INIT};
    VhAudioOutputRecovery totals={0};
    VhAudioOutputOps ops=model_ops(&m);
    uint64_t expected=FNV_INIT;
    uint64_t expected_frames=0;
    unsigned expected_failures=0,expected_restarts=0,expected_mismatches=0;
    for(unsigned page=0;page<PAGES;page++) {
        size_t frames=1u+(size_t)((page*101u)%MAX_FRAMES);
        unsigned faults=page%3u; /* 0, 1 or 2 recoverable failures */
        select_page(&m,pcm,frames,page+17u,faults);
        assert(vh_audio_output_submit_recover(&ops,&totals,pcm,frames)==0);
        assert(m.attempts==faults+1u && m.fail_left==0u);
        assert(!m.lease.in_flight);
        assert(hash_page(pcm,frames)==m.expected_hash);
        expected=hash_append(expected,pcm,frames);
        expected_frames+=frames;
        expected_failures+=faults;
        expected_restarts+=faults;
        expected_mismatches+=faults>0u;
        assert(totals.pages_submitted==page+1u);
        assert(totals.frames_submitted==expected_frames);
        assert(totals.submit_failures==expected_failures);
        assert(totals.restart_attempts==expected_restarts);
        assert(totals.recoveries<=page+1u);
        assert(m.lease.pages_released==page+1u);
        assert(m.lease.pages_leased==m.calls);
        assert(m.lease.busy_begin_rejections==expected_mismatches);
        assert(m.lease.mismatched_releases==expected_mismatches);
        assert(m.accepted_rolling==expected);
    }
    assert(totals.pages_submitted==PAGES);
    assert(totals.recoveries==PAGES-PAGES/3u-1u); /* remainder of 512 / 3 = 2 */
    assert(m.accepted_frames==expected_frames);
    assert(m.accepted_pages==PAGES && m.calls==PAGES+expected_failures);
    assert(m.stops==expected_failures && m.closes==expected_failures);
    assert(m.opens==expected_failures && m.starts==expected_failures);
    assert(m.lease.abandoned_sessions==expected_failures);
    assert(m.lease.pages_released==PAGES);
    /* Exhaust the fixed retry limit: leave page leased until the
     * service is explicitly closed, then permit next safe reuse. */
    select_page(&m,pcm,MAX_FRAMES,10000u,VH_AUDIO_OUTPUT_RESTART_LIMIT+1u);
    const unsigned before_mismatches=m.lease.mismatched_releases;
    const uint64_t before_hash=m.accepted_rolling;
    assert(vh_audio_output_submit_recover(&ops,&totals,pcm,MAX_FRAMES)==-1);
    assert(m.lease.in_flight==&m.real_token);
    assert(hash_page(pcm,MAX_FRAMES)==m.expected_hash);
    assert(m.lease.mismatched_releases==before_mismatches+2u);
    assert(m.accepted_rolling==before_hash);
    assert(totals.pages_submitted==PAGES && totals.frames_submitted==expected_frames);
    assert(vh_audio_buffer_lease_begin(&m.lease,&m.foreign_token)==-1);
    assert(!model_stop(&m));
    assert(m.lease.in_flight==&m.real_token);
    model_close(&m);
    assert(!model_open(&m) && !model_start(&m));
    select_page(&m,pcm,MAX_FRAMES,10001u,0u);
    assert(vh_audio_output_submit_recover(&ops,&totals,pcm,MAX_FRAMES)==0);
    assert(totals.pages_submitted==PAGES+1u);
    assert(totals.frames_submitted==expected_frames+MAX_FRAMES);
    assert(m.accepted_pages==PAGES+1u);
    assert(m.lease.pages_leased==m.calls);
    assert(m.lease.busy_begin_rejections==expected_mismatches+3u);
    assert(m.lease.pages_released==PAGES+1u);
    assert(m.accepted_rolling==hash_append(before_hash,pcm,MAX_FRAMES));
    assert(!m.lease.in_flight);
}
int main(void) {
    continuous_pages();
    puts("Stage345 host audout 512 distinct PCM pages: FIFO page hashes,"
         " exact leases, stale release rejection, retry-safe immutable data PASS");
    return 0;
}
