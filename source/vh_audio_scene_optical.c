#include "vh_audio_scene_optical.h"

#include <stddef.h>
#include <string.h>

/* 8-byte format tag, 1 count, 4 dropped, 64 fixed 14-byte rows,
 * 4-byte CRC32, 11 reserved zero bytes: exactly 924 bytes. */
enum { VH_SCENE_OPTICAL_ROW_START=13, VH_SCENE_OPTICAL_ROW_BYTES=14,
       VH_SCENE_OPTICAL_CRC_OFFSET=909 };
static const uint8_t magic[8]={'V','H','F','B','T','R','C','1'};

static void write_le(uint8_t *out,uint64_t value,unsigned count) {
    for (unsigned i=0;i<count;i++) {
        out[i]=(uint8_t)(value&255u);
        value>>=8u;
    }
}
static uint32_t crc32_ieee(const uint8_t *data,size_t size) {
    uint32_t crc=UINT32_C(0xffffffff);
    for (size_t i=0;i<size;i++) {
        crc^=data[i];
        for (unsigned b=0;b<8;b++)
            crc=(crc>>1u)^((crc&1u) ? UINT32_C(0xedb88320) : 0u);
    }
    return crc^UINT32_C(0xffffffff);
}
int vh_audio_scene_optical_encode(
    const VhAudioSceneTrace *trace,
    uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES]) {
    if (!trace || !packet) return -1;
    unsigned rows=atomic_load_explicit(&trace->reserved,memory_order_acquire);
    if (rows>VH_AUDIO_SCENE_TRACE_CAPACITY)
        rows=VH_AUDIO_SCENE_TRACE_CAPACITY;
    memset(packet,0,VH_SCENE_OPTICAL_PACKET_BYTES);
    memcpy(packet,magic,sizeof magic);
    packet[8]=(uint8_t)rows;
    write_le(packet+9,vh_audio_scene_trace_dropped(trace),4);
    for (unsigned i=0;i<rows;i++) {
        VhAudioSceneTraceSlot entry;
        if(vh_audio_scene_trace_snapshot(trace,i,&entry)!=1 ||
           entry.kind<VH_SCENE_TRACE_INPUT ||
           entry.kind>VH_SCENE_TRACE_SUBMIT_ERROR ||
           entry.scene>2u)
            return -1;
        const unsigned offset=VH_SCENE_OPTICAL_ROW_START+i*VH_SCENE_OPTICAL_ROW_BYTES;
        packet[offset]=(uint8_t)entry.kind;
        packet[offset+1]=(uint8_t)entry.scene;
        write_le(packet+offset+2,entry.serial,4);
        write_le(packet+offset+6,entry.monotonic_ns,8);
    }
    write_le(packet+VH_SCENE_OPTICAL_CRC_OFFSET,
             crc32_ieee(packet,VH_SCENE_OPTICAL_CRC_OFFSET),4);
    return (int)rows;
}
int vh_audio_scene_optical_draw(VhCanvas *canvas,
                                const VhAudioSceneTrace *trace,
                                uint32_t black,uint32_t white,
                                uint32_t marker) {
    if(!canvas || !canvas->pixels ||
       canvas->width < VH_SCENE_OPTICAL_LEFT+(int)VH_SCENE_OPTICAL_WIDTH ||
       canvas->height < VH_SCENE_OPTICAL_TOP+(int)VH_SCENE_OPTICAL_HEIGHT ||
       canvas->stride_pixels<(size_t)canvas->width) return -1;
    uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES];
    const int rows=vh_audio_scene_optical_encode(trace,packet);
    if(rows<0) return -1;
    vh_canvas_fill_rect(canvas,0,0,canvas->width,canvas->height,black);
    vh_canvas_fill_rect(canvas,VH_SCENE_OPTICAL_LEFT,VH_SCENE_OPTICAL_TOP,
                        VH_SCENE_OPTICAL_WIDTH,VH_SCENE_OPTICAL_HEIGHT,
                        marker);
    const int grid_x=VH_SCENE_OPTICAL_LEFT+VH_SCENE_OPTICAL_BORDER;
    const int grid_y=VH_SCENE_OPTICAL_TOP+VH_SCENE_OPTICAL_BORDER;
    vh_canvas_fill_rect(canvas,grid_x,grid_y,
                        VH_SCENE_OPTICAL_GRID_COLS*VH_SCENE_OPTICAL_MODULE,
                        VH_SCENE_OPTICAL_GRID_ROWS*VH_SCENE_OPTICAL_MODULE,
                        white);
    for(unsigned byte_index=0;byte_index<VH_SCENE_OPTICAL_PACKET_BYTES;
        byte_index++) {
        const uint8_t value=packet[byte_index];
        if(!value) continue;
        for(unsigned bit=0;bit<8;bit++) {
            if(!(value & (0x80u>>bit))) continue;
            const unsigned offset=byte_index*8u+bit;
            const unsigned col=offset%VH_SCENE_OPTICAL_GRID_COLS;
            const unsigned row=offset/VH_SCENE_OPTICAL_GRID_COLS;
            vh_canvas_fill_rect(canvas,
                grid_x+(int)(col*VH_SCENE_OPTICAL_MODULE),
                grid_y+(int)(row*VH_SCENE_OPTICAL_MODULE),
                VH_SCENE_OPTICAL_MODULE,VH_SCENE_OPTICAL_MODULE,black);
        }
    }
    return rows;
}
