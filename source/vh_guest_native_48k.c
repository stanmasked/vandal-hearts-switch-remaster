/* Generated-only exact-clock 44.1-kHz SPU to native 48-kHz output test. */
#include "vh_guest_sync_studio_c.h"
#include "vh_audio_scene_optical.h"
#include "vh_audio_resample.h"
#include "vh_audio_output_ramp.h"
#include "vh_audio_stream.h"
#include <string.h>

static VhAudioResample wet_converter, reset_converter;
static VhAudioOutputRamp wet_ramp, reset_ramp;
static int16_t wet_page[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
static int16_t reset_page[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];

static uint64_t fingerprint(uint64_t h,const int16_t *pcm,size_t frames) {
    for(size_t i=0;i<frames*2u;i++) {
        const uint16_t n=(uint16_t)pcm[i];
        h=(h^(uint8_t)n)*UINT64_C(1099511628211);
        h=(h^(uint8_t)(n>>8))*UINT64_C(1099511628211);
    }
    return h;
}
static unsigned nonzero(const int16_t *pcm,size_t frames) {
    unsigned n=0;
    for(size_t i=0;i<frames*2u;i++) n+=(pcm[i]!=0);
    return n;
}
/* Integer output-clock oracle, independent of converter counters.
 * A completed input prefix can emit output ticks through the last
 * available source frame, but not a fractional look-ahead beyond it. */
static uint32_t expected_native_frames(unsigned complete_blocks) {
    if(!complete_blocks) return 0u;
    const uint64_t end=(uint64_t)complete_blocks*VH_AUDIO_BLOCK_FRAMES;
    return (uint32_t)(((end-1u)*VH_NATIVE_AUDOUT_RATE)/
                      VH_AUDIO_SAMPLE_RATE+1u);
}
void vh_guest_native_48k_init(VhGuestNative48k *result) {
    if(!result) return;
    memset(result,0,sizeof *result);
    result->prefix_hash=UINT64_C(14695981039346656037);
    result->wet_hash=UINT64_C(14695981039346656037);
    result->reset_hash=UINT64_C(14695981039346656037);
    vh_audio_resample_reset(&wet_converter);
    vh_audio_resample_reset(&reset_converter);
    vh_audio_output_ramp_arm(&wet_ramp);
    vh_audio_output_ramp_arm(&reset_ramp);
}
int vh_guest_native_48k_observe(VhGuestNative48k *result,
    const int16_t *wet_pcm,const int16_t *reset_pcm,
    unsigned tail,unsigned tail_index) {
    if(!result || !wet_pcm || !reset_pcm || (tail!=0u && tail!=1u) ||
       tail_index>=(tail ? 48u : 64u)) return -1;
    const unsigned block=(tail ? 64u : 0u)+tail_index;
    const uint32_t before=expected_native_frames(block);
    const uint32_t after=expected_native_frames(block+1u);
    const uint64_t source_before=(uint64_t)block*VH_AUDIO_BLOCK_FRAMES;
    const uint64_t tick_before=(uint64_t)before*VH_AUDIO_SAMPLE_RATE;
    /* Forbid skipped, duplicated, reordered and early post-switch blocks,
     * even when their final total number of frames could appear valid. */
    if((uint64_t)result->prefix_frames+result->tail_frames!=before ||
       wet_converter.input_frames!=source_before ||
       reset_converter.input_frames!=source_before ||
       wet_converter.next_output_tick!=tick_before ||
       reset_converter.next_output_tick!=tick_before) return -1;
    const size_t w=vh_audio_resample_process(&wet_converter,wet_pcm,
        VH_AUDIO_BLOCK_FRAMES,wet_page,VH_AUDIO_RESAMPLE_MAX_FRAMES);
    const size_t d=vh_audio_resample_process(&reset_converter,reset_pcm,
        VH_AUDIO_BLOCK_FRAMES,reset_page,VH_AUDIO_RESAMPLE_MAX_FRAMES);
    if(!w || w!=d || w!=(size_t)(after-before) ||
       w>VH_AUDIO_RESAMPLE_MAX_FRAMES ||
       vh_audio_output_ramp_apply(&wet_ramp,wet_page,w) ||
       vh_audio_output_ramp_apply(&reset_ramp,reset_page,d))
        return -1;
    if(!tail) {
        if(memcmp(wet_page,reset_page,w*2u*sizeof(int16_t))) return -1;
        result->prefix_frames+=(uint32_t)w;
        result->prefix_hash=fingerprint(result->prefix_hash,wet_page,w);
    } else {
        result->tail_frames+=(uint32_t)w;
        result->different_pages+=memcmp(wet_page,reset_page,
                                        w*2u*sizeof(int16_t))!=0;
        result->wet_nonzero+=nonzero(wet_page,w);
        const unsigned count=nonzero(reset_page,w);
        if(tail_index==0u) result->reset_first_page_nonzero=count;
        else result->reset_later_nonzero+=count;
        result->wet_hash=fingerprint(result->wet_hash,wet_page,w);
        result->reset_hash=fingerprint(result->reset_hash,reset_page,w);
    }
    return 0;
}
static void store_le(uint8_t *p,uint64_t n,unsigned bytes) {
    for(unsigned i=0;i<bytes;i++){p[i]=(uint8_t)n;n>>=8;}
}
static uint32_t crc32_ieee(const uint8_t *data,size_t size) {
    uint32_t crc=UINT32_C(0xffffffff);
    for(size_t i=0;i<size;i++) {
        crc^=data[i];
        for(unsigned j=0;j<8;j++)
            crc=(crc>>1u)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    return crc^UINT32_C(0xffffffff);
}
int vh_guest_native_48k_encode(const VhGuestSyncStudioC *metric,
    uint8_t packet[924]) {
    if(!metric || !packet) return -1;
    const VhGuestNative48k *v=&metric->native48;
    memset(packet,0,924);
    memcpy(packet,"VH48K001",8);
    packet[8]=1u;
    packet[9]=(uint8_t)(metric->failure_line!=0u);
    if(!metric->failure_line && v->verified_roundtrips==2u)packet[10]=15u;
    store_le(packet+12,v->prefix_frames,4);
    store_le(packet+16,v->tail_frames,4);
    store_le(packet+20,v->different_pages,4);
    store_le(packet+24,v->wet_nonzero,4);
    store_le(packet+28,v->reset_first_page_nonzero,4);
    store_le(packet+32,v->reset_later_nonzero,4);
    store_le(packet+40,v->prefix_hash,8);
    store_le(packet+48,v->wet_hash,8);
    store_le(packet+56,v->reset_hash,8);
    store_le(packet+64,v->verified_roundtrips,4);
    store_le(packet+909,crc32_ieee(packet,909),4);
    return 0;
}
int vh_guest_native_48k_draw(VhCanvas *canvas,
    const VhGuestSyncStudioC *metric,
    uint32_t black,uint32_t white,uint32_t marker) {
    uint8_t packet[924];
    if(vh_guest_native_48k_encode(metric,packet)) return -1;
    return vh_audio_scene_optical_draw_packet(canvas,packet,black,white,marker);
}
