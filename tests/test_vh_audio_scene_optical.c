#include "vh_audio_scene_optical.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define W 1280
#define H 720
#define MARKER UINT32_C(0xff00ff)
#define BLACK UINT32_C(0x000000)
#define WHITE UINT32_C(0xffffff)

static uint32_t portable_crc(const uint8_t *p,size_t n) {
    uint32_t c=UINT32_C(0xffffffff);
    for(size_t i=0;i<n;i++) {
        c^=p[i];
        for(unsigned bit=0;bit<8;bit++)
            c=(c>>1u)^((c&1u) ? UINT32_C(0xedb88320) : 0);
    }
    return c^UINT32_C(0xffffffff);
}
static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8u)|
           ((uint32_t)p[2]<<16u)|((uint32_t)p[3]<<24u);
}
static uint64_t le64(const uint8_t *p) {
    uint64_t v=0;
    for(unsigned i=0;i<8;i++)v|=(uint64_t)p[i]<<(i*8u);
    return v;
}
static uint32_t sample(const VhCanvas *canvas,int x,int y) {
    return canvas->pixels[(size_t)y*canvas->stride_pixels+(size_t)x];
}
int main(void) {
    VhAudioSceneTrace log;
    vh_audio_scene_trace_init(&log);
    assert(vh_audio_scene_trace_record(
        &log,VH_SCENE_TRACE_INPUT,0x12345678u,2u,
        UINT64_C(0x1122334455667788))==1);
    assert(vh_audio_scene_trace_record(
        &log,VH_SCENE_TRACE_POST,0x12345678u,2u,
        UINT64_C(0x1122334455668811))==1);
    uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES];
    assert(vh_audio_scene_optical_encode(&log,packet)==2);
    assert(!memcmp(packet,"VHFBTRC1",8));
    assert(packet[8]==2);
    assert(le32(packet+9)==0);
    assert(packet[13]==VH_SCENE_TRACE_INPUT && packet[14]==2);
    assert(le32(packet+15)==0x12345678u);
    assert(le64(packet+19)==UINT64_C(0x1122334455667788));
    assert(packet[27]==VH_SCENE_TRACE_POST);
    assert(le32(packet+909)==portable_crc(packet,909));
    for(unsigned i=41;i<909;i++)assert(packet[i]==0);
    for(unsigned i=913;i<924;i++)assert(packet[i]==0);

    uint32_t *pixels=calloc((size_t)W*H,sizeof(uint32_t));
    assert(pixels);
    VhCanvas canvas={pixels,W,W,H};
    assert(vh_audio_scene_optical_draw(
        &canvas,&log,BLACK,WHITE,MARKER)==2);
    assert(sample(&canvas,0,0)==BLACK);
    assert(sample(&canvas,VH_SCENE_OPTICAL_LEFT,
                  VH_SCENE_OPTICAL_TOP)==MARKER);
    assert(sample(&canvas,VH_SCENE_OPTICAL_LEFT+7,
                  VH_SCENE_OPTICAL_TOP+7)==WHITE);
    assert(sample(&canvas,VH_SCENE_OPTICAL_LEFT+7+3,
                  VH_SCENE_OPTICAL_TOP+7+3)==WHITE); /* magic 'V' starts 0 */
    assert(sample(&canvas,VH_SCENE_OPTICAL_LEFT+7+7+3,
                  VH_SCENE_OPTICAL_TOP+7+3)==BLACK); /* bit 6 = 1 */

    for(unsigned bit=0;bit<VH_SCENE_OPTICAL_PACKET_BYTES*8u;bit++) {
        const unsigned x=bit%VH_SCENE_OPTICAL_GRID_COLS;
        const unsigned y=bit/VH_SCENE_OPTICAL_GRID_COLS;
        const uint8_t mask=(uint8_t)(0x80u>>(bit%8u));
        const uint32_t expected=
            (packet[bit/8u]&mask) ? BLACK : WHITE;
        const uint32_t observed=sample(&canvas,
            VH_SCENE_OPTICAL_LEFT+7+(int)x*7+3,
            VH_SCENE_OPTICAL_TOP+7+(int)y*7+3);
        assert(observed==expected);
    }
    canvas.width=320;
    assert(vh_audio_scene_optical_draw(&canvas,&log,BLACK,WHITE,MARKER)==-1);
    assert(vh_audio_scene_optical_encode(NULL,packet)==-1);
    assert(vh_audio_scene_optical_encode(&log,NULL)==-1);
    free(pixels);

    for(unsigned i=2;i<VH_AUDIO_SCENE_TRACE_CAPACITY;i++) {
        assert(vh_audio_scene_trace_record(&log,
            VH_SCENE_TRACE_POST,i,1,i)==1);
    }
    assert(vh_audio_scene_trace_record(&log,
            VH_SCENE_TRACE_POST,100,1,100)==0);
    assert(vh_audio_scene_optical_encode(&log,packet)==64);
    assert(packet[8]==64 && le32(packet+9)==1);
    assert(le32(packet+909)==portable_crc(packet,909));
    puts("PASS: 924-byte guest optical CRC packet, 7392 pixel-bits and saturation");
    return 0;
}
