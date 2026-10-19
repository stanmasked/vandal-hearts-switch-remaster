/* Diagnostic-only guest DSP replay at identical musical block boundaries.
 * Never uses the real audout worker, PS1 assets, or guest PCM monitor time. */
#include "vh_guest_sync_studio_c.h"
#include "vh_audio_scene_optical.h"
#include "platform_input.h"
#include "vh_game_music_mailbox.h"
#include "vh_music_scene.h"
#include <stddef.h>
#include <string.h>

#define HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0
enum { PRE_BLOCKS=64, TAIL_BLOCKS=48, CRC_OFFSET=909 };
static const uint8_t field_seq[]={
    HDR,0,0xc0,7,0,0x90,60,100,
    0x87,0x68,0x80,60,0,0,0xff,0x2f
};
static const uint8_t selected_seq[]={
    HDR,0,0xc0,9,0x87,0x68,0xff,0x2f
};

/* Static, independent; no large SPU work areas on libnx stack. */
static VhNativeSpu wet_spu, reset_spu;
static VhMusicScene wet, reset;
static int16_t synth_pcm[128];
static int16_t wet_pcm[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t reset_pcm[VH_AUDIO_BLOCK_FRAMES*2u];

static uint64_t hash_block(uint64_t h,const int16_t *pcm) {
    for(size_t i=0;i<VH_AUDIO_BLOCK_FRAMES*2u;i++) {
        const uint16_t v=(uint16_t)pcm[i];
        h=(h^(uint8_t)v)*UINT64_C(1099511628211);
        h=(h^(uint8_t)(v>>8))*UINT64_C(1099511628211);
    }
    return h;
}
static unsigned nonzero(const int16_t *pcm) {
    unsigned count=0;
    for(unsigned i=0;i<VH_AUDIO_BLOCK_FRAMES*2u;i++)
        count+=(pcm[i]!=0);
    return count;
}
static int resolver(void *ctx,unsigned program,unsigned note,
                    unsigned velocity,unsigned volume,unsigned pan,
                    VhSeqTone *tone) {
    (void)ctx;(void)velocity;(void)volume;(void)pan;
    if(!tone || program!=7u || note!=60u) return -1;
    memset(tone,0,sizeof *tone);
    tone->pcm=synth_pcm;tone->frames=128u;
    tone->loop_start=0;tone->loop_end=128;
    tone->pitch_step=4096u;tone->adsr1=15u;
    tone->gain_left=0.75f;tone->gain_right=0.4f;
    tone->reverb_send=1u;
    return 0;
}
#define NEED(expr) do { if(!(expr)) return (unsigned)__LINE__; } while(0)
static unsigned replay(VhGuestSyncStudioC *out) {
    memset(out,0,sizeof *out);
    out->initial_hash=UINT64_C(14695981039346656037);
    out->wet_hash=UINT64_C(14695981039346656037);
    out->reset_hash=UINT64_C(14695981039346656037);
    vh_guest_native_48k_init(&out->native48);
    for(unsigned i=0;i<128u;i++)
        synth_pcm[i]=(int16_t)(11000+(int)i*17);
    vh_native_spu_reset(&wet_spu);vh_native_spu_reset(&reset_spu);
    NEED(vh_native_spu_set_interpolation(&wet_spu,VH_SPU_GAUSSIAN)==0);
    NEED(vh_native_spu_set_interpolation(&reset_spu,VH_SPU_GAUSSIAN)==0);
    NEED(vh_native_spu_set_reverb(&wet_spu,1,0.5f)==0);
    NEED(vh_native_spu_set_reverb(&reset_spu,1,0.5f)==0);
    vh_music_scene_init(&wet,&wet_spu);
    vh_music_scene_init(&reset,&reset_spu);
    NEED(vh_music_scene_set_reverb_continuity(&wet,1)==0);
    NEED(reset.keep_reverb_across_cues==0);
    VhGameState game={1,2,1,2,6,3,0};
    NEED(vh_game_music_for_state(&game)==VH_GAME_MUSIC_FIELD);
    const VhMusicCue initial={VH_GAME_MUSIC_FIELD+1u,
                              field_seq,sizeof field_seq,0,resolver,NULL};
    const VhMusicCue no_note={VH_GAME_MUSIC_HERO_SELECTED+1u,
                              selected_seq,sizeof selected_seq,0,resolver,NULL};
    NEED(vh_music_scene_request(&wet,&initial,0)==0);
    NEED(vh_music_scene_request(&reset,&initial,0)==0);
    for(unsigned i=0;i<PRE_BLOCKS;i++) {
        NEED(vh_music_scene_render(&wet,wet_pcm)==0);
        NEED(vh_music_scene_render(&reset,reset_pcm)==0);
        NEED(memcmp(wet_pcm,reset_pcm,sizeof wet_pcm)==0);
        out->initial_hash=hash_block(out->initial_hash,wet_pcm);
        NEED(vh_guest_native_48k_observe(&out->native48,wet_pcm,reset_pcm,0,i)==0);
    }
    NEED(wet.seq.note_ons==1u && reset.seq.note_ons==1u);
    out->pre_note_ons=(uint32_t)wet.seq.note_ons;
    NEED(memcmp(&wet_spu.reverb,&reset_spu.reverb,
                sizeof wet_spu.reverb)==0);
    NEED(vh_process_input(&game,VH_INPUT_CONFIRM,8,6,2)==0);
    NEED(vh_game_music_for_state(&game)==VH_GAME_MUSIC_HERO_SELECTED);
    NEED(vh_music_scene_request(&wet,&no_note,0)==0);
    NEED(vh_music_scene_request(&reset,&no_note,0)==0);
    NEED(wet.active.id==reset.active.id);
    NEED(wet.seq.note_ons==0u && reset.seq.note_ons==0u);
    out->next_note_ons=(uint32_t)wet.seq.note_ons;
    for(unsigned i=0;i<VH_NATIVE_MUSIC_VOICES;i++) {
        NEED(wet_spu.voice[i].active==0 && reset_spu.voice[i].active==0);
        NEED(wet_spu.voice[i].pcm!=synth_pcm);
        NEED(reset_spu.voice[i].pcm!=synth_pcm);
    }
    NEED(memcmp(&wet_spu.reverb,&reset_spu.reverb,
                sizeof wet_spu.reverb)!=0);
    for(unsigned i=0;i<TAIL_BLOCKS;i++) {
        NEED(vh_music_scene_render(&wet,wet_pcm)==0);
        NEED(vh_music_scene_render(&reset,reset_pcm)==0);
        out->wet_nonzero+=nonzero(wet_pcm);
        out->reset_nonzero+=nonzero(reset_pcm);
        out->different_blocks+=(memcmp(wet_pcm,reset_pcm,sizeof wet_pcm)!=0);
        out->wet_hash=hash_block(out->wet_hash,wet_pcm);
        out->reset_hash=hash_block(out->reset_hash,reset_pcm);
        NEED(vh_guest_native_48k_observe(&out->native48,wet_pcm,reset_pcm,1,i)==0);
        NEED(wet.stage==reset.stage);
        NEED(wet.blocks_rendered==reset.blocks_rendered);
        NEED(wet.seq.note_ons==0u && reset.seq.note_ons==0u);
        NEED(wet.seq.note_offs==reset.seq.note_offs);
        NEED(wet.seq.blocks_advanced==reset.seq.blocks_advanced);
    }
    out->pre_blocks=PRE_BLOCKS;out->post_blocks=TAIL_BLOCKS;
    NEED(out->reset_nonzero==0u && out->wet_nonzero>0u);
    NEED(out->different_blocks==TAIL_BLOCKS);
    NEED(out->wet_hash!=out->reset_hash);
    NEED(out->native48.prefix_frames>=PRE_BLOCKS*555u);
    NEED(out->native48.tail_frames>=TAIL_BLOCKS*555u);
    NEED(out->native48.different_pages==TAIL_BLOCKS);
    NEED(out->native48.wet_nonzero>0u);
    /* Only one interpolated stereo frame may bridge the old cue. */
    NEED(out->native48.reset_first_page_nonzero<=2u);
    NEED(out->native48.reset_later_nonzero==0u);
    NEED(out->native48.wet_hash!=out->native48.reset_hash);
    NEED(vh_music_scene_request(&wet,NULL,0)==0);
    NEED(vh_music_scene_request(&reset,NULL,0)==0);
    NEED(vh_music_scene_render(&wet,wet_pcm)==0);
    NEED(vh_music_scene_render(&reset,reset_pcm)==0);
    NEED(nonzero(wet_pcm)==0 && nonzero(reset_pcm)==0);
    for(unsigned i=0;i<VH_REV_SAMPLES;i++) {
        NEED(wet_spu.reverb.work[i]==0);
        NEED(reset_spu.reverb.work[i]==0);
    }
    NEED(vh_music_scene_detach(&wet)==0);
    NEED(vh_music_scene_detach(&reset)==0);
    return 0;
}
int vh_guest_sync_studio_c_run(VhGuestSyncStudioC *out) {
    if(!out) return -1;
    VhGuestSyncStudioC first, second;
    const unsigned one=replay(&first);
    if(one) { memset(out,0,sizeof *out);out->failure_line=one;return -1; }
    const unsigned two=replay(&second);
    if(two) { memset(out,0,sizeof *out);out->failure_line=two;return -1; }
    if(first.initial_hash!=second.initial_hash ||
       first.wet_hash!=second.wet_hash ||
       first.reset_hash!=second.reset_hash ||
       first.different_blocks!=second.different_blocks ||
       first.wet_nonzero!=second.wet_nonzero ||
       first.reset_nonzero!=second.reset_nonzero ||
       first.pre_blocks!=second.pre_blocks ||
       first.post_blocks!=second.post_blocks ||
       first.pre_note_ons!=second.pre_note_ons ||
       first.next_note_ons!=second.next_note_ons ||
       first.native48.prefix_hash!=second.native48.prefix_hash ||
       first.native48.wet_hash!=second.native48.wet_hash ||
       first.native48.reset_hash!=second.native48.reset_hash ||
       first.native48.prefix_frames!=second.native48.prefix_frames ||
       first.native48.tail_frames!=second.native48.tail_frames ||
       first.native48.different_pages!=second.native48.different_pages ||
       first.native48.wet_nonzero!=second.native48.wet_nonzero ||
       first.native48.reset_first_page_nonzero!=second.native48.reset_first_page_nonzero ||
       first.native48.reset_later_nonzero!=second.native48.reset_later_nonzero) {
        memset(out,0,sizeof *out);out->failure_line=(uint32_t)__LINE__;
        return -1;
    }
    *out=first;
    out->verified_roundtrips=2u;
    out->native48.verified_roundtrips=2u;
    return 0;
}
static void put_le(uint8_t *dst,uint64_t value,unsigned n) {
    for(unsigned i=0;i<n;i++) {dst[i]=(uint8_t)value;value>>=8;}
}
static uint32_t crc32_ieee(const uint8_t *data,size_t n) {
    uint32_t crc=UINT32_C(0xffffffff);
    for(size_t i=0;i<n;i++) {
        crc ^= data[i];
        for(unsigned b=0;b<8;b++)
            crc=(crc>>1)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    return crc^UINT32_C(0xffffffff);
}
int vh_guest_sync_studio_c_encode(const VhGuestSyncStudioC *v,
    uint8_t packet[924]) {
    if(!v || !packet) return -1;
    memset(packet,0,VH_SCENE_OPTICAL_PACKET_BYTES);
    memcpy(packet,"VHSYNC01",8);
    packet[8]=1u; /* version */
    packet[9]=(uint8_t)(v->failure_line ? 1u : 0u);
    if(!v->failure_line && v->verified_roundtrips==2u)
        packet[10]=15u; /* pre identical; same clock; deterministic; reset silent */
    put_le(packet+12,v->pre_blocks,4);
    put_le(packet+16,v->post_blocks,4);
    put_le(packet+20,v->different_blocks,4);
    put_le(packet+24,v->wet_nonzero,4);
    put_le(packet+28,v->reset_nonzero,4);
    put_le(packet+32,v->initial_hash,8);
    put_le(packet+40,v->wet_hash,8);
    put_le(packet+48,v->reset_hash,8);
    put_le(packet+56,v->pre_note_ons,4);
    put_le(packet+60,v->next_note_ons,4);
    put_le(packet+64,v->verified_roundtrips,4);
    put_le(packet+68,v->failure_line,4);
    put_le(packet+CRC_OFFSET,crc32_ieee(packet,CRC_OFFSET),4);
    return 0;
}
int vh_guest_sync_studio_c_draw(VhCanvas *canvas,
    const VhGuestSyncStudioC *v,
    uint32_t black,uint32_t white,uint32_t marker) {
    uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES];
    if(vh_guest_sync_studio_c_encode(v,packet)) return -1;
    return vh_audio_scene_optical_draw_packet(canvas,packet,black,white,marker);
}
