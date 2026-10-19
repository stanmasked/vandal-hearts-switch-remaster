#include "vh_audout_presubmit_optical.h"
#include <string.h>

/* VHPRExxx layout:
 *  0..7 magic VHPRE001; 8 count (must be eight); 9 pending;
 *  10..11 reserved; 12..15 mismatches; 16..207 eight 24-byte records;
 *  208..908 reserved zero; 909..912 packet CRC32; 913..923 zero.
 * Page: frames(u32), attempts(u32), successful_returns(u32),
 *       canonical PCM16LE FNV-1a64(u64), CRC32(u32).
 */
static const uint8_t MAGIC[8]={'V','H','P','R','E','0','0','1'};
static void le32(uint8_t *p,uint32_t v) {
    for(unsigned i=0;i<4u;i++) {p[i]=(uint8_t)v;v>>=8u;}
}
static void le64(uint8_t *p,uint64_t v) {
    for(unsigned i=0;i<8u;i++) {p[i]=(uint8_t)v;v>>=8u;}
}
static uint32_t crc32(const uint8_t *p,size_t n) {
    uint32_t crc=UINT32_C(0xffffffff);
    for(size_t i=0;i<n;i++) {
        crc^=p[i];
        for(unsigned j=0;j<8u;j++)
            crc=(crc>>1u)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    return crc^UINT32_C(0xffffffff);
}
int vh_audout_presubmit_optical_encode(const VhAudoutPresubmitWitness *w,
    uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES]) {
    if(!w || !packet || w->pending || w->checked ||
       w->count!=VH_AUDOUT_PRESUBMIT_CAP || w->mismatches)
        return -1;
    memset(packet,0,VH_SCENE_OPTICAL_PACKET_BYTES);
    memcpy(packet,MAGIC,8u);
    packet[8]=(uint8_t)w->count;
    le32(packet+12,w->mismatches);
    for(unsigned i=0;i<w->count;i++) {
        const VhAudoutPresubmitPage *p=&w->page[i];
        if(!p->frames || p->frames>VH_AUDOUT_PRESUBMIT_MAX_FRAMES ||
           !p->attempts || p->successful_returns!=1u ||
           !p->fnv1a64 || !p->crc32) return -1;
        uint8_t *dst=packet+16u+i*24u;
        le32(dst,p->frames);
        le32(dst+4,p->attempts);
        le32(dst+8,p->successful_returns);
        le64(dst+12,p->fnv1a64);
        le32(dst+20,p->crc32);
    }
    le32(packet+909,crc32(packet,909u));
    return 0;
}
