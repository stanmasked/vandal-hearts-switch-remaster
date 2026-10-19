#include "vh_audout_presubmit_witness.h"

#include <limits.h>
#include <string.h>

/* Canonical PCM16 little-endian digest: independent of host endianness.
 * This is a diagnostic fingerprint, not a cryptographic authenticator.
 */
static void fingerprint(const int16_t *pcm,size_t frames,
                        uint64_t *fnv,uint32_t *crc) {
    uint64_t h=UINT64_C(14695981039346656037);
    uint32_t c=UINT32_C(0xffffffff);
    for(size_t i=0;i<frames*2u;i++) {
        const uint16_t sample=(uint16_t)pcm[i];
        for(unsigned b=0u;b<2u;b++) {
            const uint8_t octet=(uint8_t)(sample>>(b*8u));
            h=(h^octet)*UINT64_C(1099511628211);
            c^=octet;
            for(unsigned k=0u;k<8u;k++)
                c=(c>>1u)^((c&1u)?UINT32_C(0xedb88320):0u);
        }
    }
    *fnv=h;
    *crc=c^UINT32_C(0xffffffff);
}
static int valid(const int16_t *pcm,size_t frames) {
    return pcm && frames>0u &&
        frames<=VH_AUDOUT_PRESUBMIT_MAX_FRAMES;
}

void vh_audout_presubmit_reset(VhAudoutPresubmitWitness *w) {
    if(w) memset(w,0,sizeof *w);
}

int vh_audout_presubmit_arm(VhAudoutPresubmitWitness *w,
                            const int16_t *pcm,size_t frames) {
    if(!w || !valid(pcm,frames) || w->pending ||
       w->count>VH_AUDOUT_PRESUBMIT_CAP) return -1;
    if(w->count==VH_AUDOUT_PRESUBMIT_CAP) return 1;
    VhAudoutPresubmitPage *page=&w->page[w->count];
    if(page->frames || page->attempts || page->successful_returns)
        return -1;
    fingerprint(pcm,frames,&page->fnv1a64,&page->crc32);
    page->frames=(uint32_t)frames;
    w->pending=1u;
    w->checked=0u;
    return 0;
}

int vh_audout_presubmit_before_call(VhAudoutPresubmitWitness *w,
                                     const int16_t *pcm,size_t frames) {
    if(!w || !valid(pcm,frames) || w->count>VH_AUDOUT_PRESUBMIT_CAP)
        return -1;
    if(!w->pending)
        return w->count==VH_AUDOUT_PRESUBMIT_CAP ? 1 : -1;
    const VhAudoutPresubmitPage *page=&w->page[w->count];
    uint64_t fnv;
    uint32_t crc;
    fingerprint(pcm,frames,&fnv,&crc);
    if(frames!=page->frames || fnv!=page->fnv1a64 ||
       crc!=page->crc32) {
        if(w->mismatches<UINT_MAX) ++w->mismatches;
        w->checked=0u;
        return -1;
    }
    w->checked=1u;
    return 0;
}

int vh_audout_presubmit_return(VhAudoutPresubmitWitness *w,int returned) {
    if(!w || (returned!=0 && returned!=1) ||
       w->count>VH_AUDOUT_PRESUBMIT_CAP) return -1;
    if(!w->pending)
        return w->count==VH_AUDOUT_PRESUBMIT_CAP ? 1 : -1;
    if(!w->checked) return -1;
    VhAudoutPresubmitPage *page=&w->page[w->count];
    if(page->attempts==UINT32_MAX) return -1;
    ++page->attempts;
    w->checked=0u;
    if(returned) {
        page->successful_returns=1u;
        w->pending=0u;
        ++w->count;
    }
    return 0;
}
