/* Asset-free first-page metrics fingerprint, bounds, CRC and ticket test. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_map02_pcm_metrics.h"

static uint32_t crc32_ieee(const uint8_t *data, size_t len) {
    uint32_t crc=UINT32_C(0xffffffff);
    for(size_t i=0;i<len;i++) {
        crc ^= data[i];
        for(unsigned bit=0;bit<8;bit++)
            crc=(crc>>1u)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    return crc^UINT32_C(0xffffffff);
}
static uint32_t read_le32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
           ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
int main(void) {
    VhMap02PcmMetrics metrics;
    uint8_t packet[VH_MAP02_PCM_METRIC_PACKET_BYTES];
    const int16_t selected[8]={0,1,-2,32767,-32768,0,3,0};
    const int16_t field[8]={2,2,0,0,-4,0,0,0};
    vh_map02_pcm_metrics_init(&metrics);
    assert(vh_map02_pcm_metrics_encode(&metrics,packet)==-1);
    assert(vh_map02_pcm_metrics_capture(&metrics,9,2,selected,4)==0);
    assert(vh_map02_pcm_metrics_capture(&metrics,1,2,selected,4)==1);
    assert(vh_map02_pcm_metrics_capture(&metrics,1,2,field,4)==0);
    assert(metrics.items[0].nonzero==5);
    assert(metrics.items[0].peak==32768);
    assert(vh_map02_pcm_metrics_capture(&metrics,2,1,field,4)==1);
    assert(metrics.items[1].nonzero==3);
    assert(metrics.items[1].peak==4);
    assert(vh_map02_pcm_metrics_encode(&metrics,packet)==2);
    assert(!memcmp(packet,"VHPCM01A",8));
    assert(packet[8]==2 && packet[9]==0);
    assert(read_le32(packet+12)==1u);
    assert(read_le32(packet+40)==2u);
    assert(packet[16]==2 && packet[44]==1);
    assert(read_le32(packet+909)==crc32_ieee(packet,909));
    assert(vh_map02_pcm_metrics_capture(&metrics,1,1,field,0)==-1);
    puts("PASS: generated first-page ticket 1/2 PCM metrics are deterministic, bounded, CRC32 protected");
    return 0;
}
