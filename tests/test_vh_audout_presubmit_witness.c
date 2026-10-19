/* Bounded, generated-only PCM page identity and retry order probes. */
#include "vh_audout_presubmit_witness.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int16_t page[VH_AUDOUT_PRESUBMIT_MAX_FRAMES*2u];
static void fill(unsigned seed) {
    for(unsigned i=0u;i<VH_AUDOUT_PRESUBMIT_MAX_FRAMES*2u;i++)
        page[i]=(int16_t)((i*97u+seed*701u)%65536u);
}
int main(void) {
    VhAudoutPresubmitWitness w;
    vh_audout_presubmit_reset(&w);
    fill(1u);
    assert(vh_audout_presubmit_before_call(&w,page,557u)==-1);
    assert(vh_audout_presubmit_return(&w,1)==-1);
    assert(vh_audout_presubmit_arm(NULL,page,557u)==-1);
    assert(vh_audout_presubmit_arm(&w,NULL,557u)==-1);
    assert(vh_audout_presubmit_arm(&w,page,0u)==-1);
    assert(vh_audout_presubmit_arm(&w,page,641u)==-1);
    assert(vh_audout_presubmit_arm(&w,page,557u)==0);
    assert(w.count==0u && w.pending==1u);
    assert(vh_audout_presubmit_arm(&w,page,557u)==-1);
    assert(vh_audout_presubmit_return(&w,1)==-1); /* no checked call */
    assert(vh_audout_presubmit_before_call(&w,page,558u)==-1);
    page[31]^=1; /* one-bit PCM corruption must be rejected */
    assert(vh_audout_presubmit_before_call(&w,page,557u)==-1);
    assert(w.mismatches==2u && w.count==0u);
    page[31]^=1; /* restore exactly the sealed bytes */
    assert(vh_audout_presubmit_before_call(&w,page,557u)==0);
    assert(vh_audout_presubmit_return(&w,0)==0); /* failed audout try */
    assert(w.page[0].attempts==1u && w.pending==1u);
    assert(vh_audout_presubmit_before_call(&w,page,557u)==0);
    assert(vh_audout_presubmit_return(&w,1)==0); /* exact page released */
    assert(w.count==1u && !w.pending && w.page[0].attempts==2u);
    assert(w.page[0].successful_returns==1u);
    assert(vh_audout_presubmit_before_call(&w,page,557u)==-1);
    assert(vh_audout_presubmit_return(&w,0)==-1);
    const uint64_t first_hash=w.page[0].fnv1a64;
    const uint32_t first_crc=w.page[0].crc32;
    assert(first_hash && first_crc);
    /* Independent PCM16-LE reference (Python struct.pack + zlib.crc32).
     * These constants guard byte ordering and digest implementations,
     * rather than comparing two copies of the SAME buggy algorithm. */
    assert(first_hash==UINT64_C(0x05d42c5563013652));
    assert(first_crc==UINT32_C(0x154b4767));
    for(unsigned i=1u;i<VH_AUDOUT_PRESUBMIT_CAP;i++) {
        const size_t frames=i&1u?558u:557u;
        fill(i+1u);
        assert(vh_audout_presubmit_arm(&w,page,frames)==0);
        assert(vh_audout_presubmit_before_call(&w,page,frames)==0);
        assert(vh_audout_presubmit_return(&w,1)==0);
        assert(w.count==i+1u);
    }
    assert(w.page[0].fnv1a64==first_hash);
    assert(w.page[0].crc32==first_crc);
    assert(vh_audout_presubmit_arm(&w,page,557u)==1);
    assert(vh_audout_presubmit_before_call(&w,page,557u)==1);
    assert(vh_audout_presubmit_return(&w,1)==1);
    assert(w.count==VH_AUDOUT_PRESUBMIT_CAP);
    assert(w.mismatches==2u);
    assert(w.page[1].fnv1a64==UINT64_C(0xf53cd6dfed5657df));
    assert(w.page[1].crc32==UINT32_C(0x667ef4d2));
    vh_audout_presubmit_reset(&w);
    assert(w.count==0u && w.mismatches==0u && !w.pending);
    fill(7u);
    assert(vh_audout_presubmit_arm(&w,page,1u)==0);
    assert(vh_audout_presubmit_before_call(&w,page,1u)==0);
    assert(vh_audout_presubmit_return(&w,1)==0);
    assert(w.page[0].fnv1a64==UINT64_C(0x6dcd8fc02714d452));
    assert(w.page[0].crc32==UINT32_C(0x5b9f7c93));
    puts("PASS: PCM16 stereo pre-submit dual fingerprints and exact-page release");
    puts("PASS: reject changed frames/PCM, accept identical retry without re-render");
    puts("PASS: bounded eight-page observer, no PCM pointers or audout side effects");
    return 0;
}
