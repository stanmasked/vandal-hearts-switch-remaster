#include "vh_map02_pcm_metrics.h"
#include "vh_audio_scene_optical.h"
#include <string.h>
#include <limits.h>

enum { ROW_BYTES=28, ROW_START=12, CRC_OFFSET=909 };
static void put_le(uint8_t *dst,uint64_t value,unsigned size) {
    for(unsigned i=0;i<size;i++) {dst[i]=(uint8_t)value;value >>= 8;}
}
static uint32_t crc32_ieee(const uint8_t *data,size_t count) {
    uint32_t crc=UINT32_C(0xffffffff);
    for(size_t i=0;i<count;i++) {
        crc^=data[i];
        for(unsigned bit=0;bit<8;bit++)
            crc=(crc>>1u)^((crc&1u) ? UINT32_C(0xedb88320) : 0u);
    }
    return crc^UINT32_C(0xffffffff);
}
void vh_map02_pcm_metrics_init(VhMap02PcmMetrics *metrics) {
    if(metrics) memset(metrics,0,sizeof *metrics);
}
int vh_map02_pcm_metrics_capture(VhMap02PcmMetrics *metrics,
    unsigned serial,unsigned scene,const int16_t *pcm,size_t frames) {
    if(!metrics || !pcm || !frames || frames>1024u)
        return -1;
    if(!((serial==1u && scene==2u) || (serial==2u && scene==1u)))
        return 0;
    const unsigned index=serial-1u, bit=1u<<index;
    if(metrics->captured_mask & bit) return 0;
    VhMap02PcmMetric result={0};
    result.serial=serial; result.scene=scene;result.frames=(unsigned)frames;
    uint64_t hash=UINT64_C(14695981039346656037);
    for(size_t i=0;i<frames*2u;i++) {
        const int32_t sample=pcm[i];
        const uint32_t abs_sample=sample<0 ? (uint32_t)(-sample):(uint32_t)sample;
        result.nonzero += sample!=0;
        if(abs_sample>result.peak) result.peak=abs_sample;
        result.sum_squares+=(uint64_t)((int64_t)sample*(int64_t)sample);
        const uint16_t raw=(uint16_t)pcm[i];
        hash=(hash^(uint8_t)raw)*UINT64_C(1099511628211);
        hash=(hash^(uint8_t)(raw>>8))*UINT64_C(1099511628211);
    }
    result.fnv1a64=hash;
    metrics->items[index]=result;
    metrics->captured_mask|=bit;
    return 1;
}
int vh_map02_pcm_metrics_encode(const VhMap02PcmMetrics *metrics,
    uint8_t packet[VH_MAP02_PCM_METRIC_PACKET_BYTES]) {
    if(!metrics || !packet || metrics->captured_mask!=3u)
        return -1;
    memset(packet,0,VH_MAP02_PCM_METRIC_PACKET_BYTES);
    memcpy(packet,"VHPCM01A",8);
    packet[8]=2u;
    for(unsigned i=0;i<2u;i++) {
        const VhMap02PcmMetric *m=&metrics->items[i];
        if(m->serial!=i+1u || m->scene!=(i==0 ? 2u:1u) ||
           !m->frames || m->frames>1024u ||
           !m->nonzero || m->nonzero>m->frames*2u ||
           !m->peak || m->peak>32768u ||
           m->sum_squares<m->nonzero ||
           m->sum_squares>(uint64_t)(m->frames*2u)*m->peak*m->peak)
            return -1;
        uint8_t *row=packet+ROW_START+i*ROW_BYTES;
        put_le(row,m->serial,4);row[4]=(uint8_t)m->scene;
        row[5]=1u; /* captured and valid */
        put_le(row+6,m->frames,2);
        put_le(row+8,m->nonzero,2);
        put_le(row+10,m->peak,2);
        put_le(row+12,m->sum_squares,8);
        put_le(row+20,m->fnv1a64,8);
    }
    put_le(packet+CRC_OFFSET,crc32_ieee(packet,CRC_OFFSET),4);
    return 2;
}
int vh_map02_pcm_metrics_draw(VhCanvas *canvas,const VhMap02PcmMetrics *metrics,
    uint32_t black,uint32_t white,uint32_t marker) {
    uint8_t packet[VH_MAP02_PCM_METRIC_PACKET_BYTES];
    if(vh_map02_pcm_metrics_encode(metrics,packet)!=2) return -1;
    return vh_audio_scene_optical_draw_packet(canvas,packet,black,white,marker);
}
