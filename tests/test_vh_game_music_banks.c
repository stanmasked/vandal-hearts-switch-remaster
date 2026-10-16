/* Two preloaded user-owned music banks and gameplay scene switches:
 * every input file is a generated fixture in a temporary directory.
 */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "vh_game_music_banks.h"

#define VH_BYTES (32u+128u*16u+512u+512u)
#define SEQ_HDR 'p','Q','E','S',0,0,0,0,1,0xe0,7,0xa1,0x20,0,0
static const uint8_t music_field[] = {
    SEQ_HDR,0,0xc0,7,0,0x90,60,100,0x81,0x70,0x80,60,0,
    0,0xff,0x2f
};
static const uint8_t music_selected[] = {
    SEQ_HDR,0,0xc0,7,0,0x90,67,110,0x81,0x70,0x80,67,0,
    0,0xff,0x2f
};
static char root[]="/tmp/vh-game-banks-XXXXXX";
static char path[512];
static uint8_t vh[VH_BYTES], vb[48];
static VhNativeSpu spu;
static VhMusicScene director;
static int16_t output[512*2];

static void write16(size_t at,unsigned value) {
    vh[at]=(uint8_t)value;
    vh[at+1]=(uint8_t)(value>>8);
}
static void fixture(unsigned variant) {
    memset(vh,0,sizeof vh);
    memset(vb,0,sizeof vb);
    memcpy(vh,"pBAV",4);
    write16(18,8); /* packed list contains program #7 */
    write16(20,1);
    write16(22,1);
    vh[24]=127;
    const size_t prog=32+7*16u;
    vh[prog]=1;
    vh[prog+1]=127;
    vh[prog+4]=64;
    const size_t tone=32+128*16u;
    vh[tone+1]=4; /* EON */
    vh[tone+2]=127;
    vh[tone+3]=64;
    vh[tone+4]=60;
    vh[tone+6]=40;
    vh[tone+7]=100;
    write16(tone+16,15);
    write16(tone+20,7);
    write16(tone+22,1);
    write16(tone+512,2);
    write16(tone+514,4);
    vb[16]=2; vb[17]=4;
    vb[32]=2; vb[33]=3;
    for(size_t i=18;i<32;i++)vb[i]=variant?0x44:0x22;
    for(size_t i=34;i<48;i++)vb[i]=variant?0xdd:0xee;
}
static void file(const char *scene,const char *name,
                 const void *bytes,size_t count) {
    assert(snprintf(path,sizeof path,"%s/%s/%s",root,scene,name)>0);
    FILE *f=fopen(path,"wb");
    assert(f);
    assert(fwrite(bytes,1,count,f)==count);
    assert(!fclose(f));
}
static void remove_file(const char *scene,const char *name) {
    assert(snprintf(path,sizeof path,"%s/%s/%s",root,scene,name)>0);
    assert(unlink(path)==0);
}
static void files(const char *scene, unsigned variant) {
    fixture(variant);
    file(scene,"music.seq",variant?music_selected:music_field,
         variant?sizeof music_selected:sizeof music_field);
    file(scene,"music.vh",vh,sizeof vh);
    file(scene,"music.vb",vb,sizeof vb);
}
static void cleanup_scene(const char *scene) {
    remove_file(scene,"music.seq");
    remove_file(scene,"music.vh");
    remove_file(scene,"music.vb");
}

int main(void) {
    assert(mkdtemp(root)!=NULL);
    assert(snprintf(path,sizeof path,"%s/field",root)>0);
    assert(mkdir(path,0700)==0);
    assert(snprintf(path,sizeof path,"%s/selected",root)>0);
    assert(mkdir(path,0700)==0);
    VhGameMusicBanks *pack=NULL;
    assert(vh_game_music_banks_load(&pack,root)==VH_AUDIO_ASSET_MISSING);
    assert(pack==NULL);

    files("field",0);
    assert(vh_game_music_banks_load(&pack,root)==VH_AUDIO_ASSET_ERROR);
    assert(pack==NULL); /* no implicit synthetic fallback for one bank */

    files("selected",1);
    assert(vh_game_music_banks_load(&pack,root)==VH_AUDIO_ASSET_OK);
    assert(pack!=NULL);
    assert(pack->field.bank.active && pack->selected.bank.active);
    assert(pack->field.bank.samples[1].pcm !=
           pack->selected.bank.samples[1].pcm);
    assert(pack->field.bank.samples[1].pcm[0] !=
           pack->selected.bank.samples[1].pcm[0]);
    assert(pack->field.vb_size+pack->selected.vb_size <=
           VH_GAME_MUSIC_MAX_TOTAL_VB_BYTES);
    assert(pack->field_audit.note_events==1u);
    assert(pack->selected_audit.note_events==1u);
    assert(pack->field_audit.resolved_notes==1u);
    assert(pack->selected_audit.resolved_notes==1u);
    assert(!pack->field_audit.has_missing &&
           !pack->selected_audit.has_missing);
    assert(pack->field_fallback_notes==0u &&
           pack->selected_fallback_notes==0u);

    VhMusicCue a={0},b={0};
    assert(vh_game_music_banks_cue(pack,VH_GAME_MUSIC_FIELD,&a)==0);
    assert(vh_game_music_banks_cue(
        pack,VH_GAME_MUSIC_HERO_SELECTED,&b)==0);
    assert(a.id==1 && b.id==2 && a.seq!=b.seq && a.context!=b.context);
    assert(a.resolver==vh_native_vab_resolve);
    assert(b.resolver==vh_native_vab_resolve);
    assert(vh_game_music_banks_cue(pack,33,&a)==-1);
    assert(vh_game_music_banks_load(&pack,root)==VH_AUDIO_ASSET_ERROR);

    vh_native_spu_reset(&spu);
    assert(vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN)==0);
    assert(vh_native_spu_set_reverb(&spu,1,0.5f)==0);
    vh_music_scene_init(&director,&spu);
    assert(vh_music_scene_request(&director,&a,0)==0);
    assert(vh_music_scene_render(&director,output)==0);
    assert(spu.voice[0].active);
    const int16_t *old_pcm=spu.voice[0].pcm;
    assert(old_pcm==pack->field.bank.samples[1].pcm);
    assert(vh_music_scene_request(&director,&b,2)==0);
    assert(vh_music_scene_render(&director,output)==0);
    assert(vh_music_scene_render(&director,output)==0);
    assert(director.stage==VH_MUSIC_SWITCH_PENDING);
    assert(spu.voice[0].pcm==old_pcm); /* old memory remains live */
    assert(vh_music_scene_render(&director,output)==0);
    assert(director.active.id==2);
    assert(spu.voice[0].pcm==pack->selected.bank.samples[1].pcm);
    for(unsigned i=0;i<6u;i++)
        assert(vh_music_scene_render(&director,output)==0);
    assert(director.stage==VH_MUSIC_PLAYING && director.switches==2);

    /* Explicitly stop audio and all borrowed pointers before freeing. */
    assert(vh_music_scene_request(&director,NULL,0)==0);
    assert(!spu.voice[0].active);
    vh_game_music_banks_close(&pack);
    assert(pack==NULL);
    vh_game_music_banks_close(&pack);

    /* A corrupt selected VH must invalidate BOTH scenes atomically. */
    fixture(1);
    vh[0]='X';
    file("selected","music.vh",vh,sizeof vh);
    assert(vh_game_music_banks_load(&pack,root)==VH_AUDIO_ASSET_ERROR);
    assert(pack==NULL);
    files("selected",1);
    remove_file("selected","music.seq");
    assert(vh_game_music_banks_load(&pack,root)==VH_AUDIO_ASSET_ERROR);
    assert(pack==NULL);
    file("selected","music.seq",music_selected,sizeof music_selected);
    /* A structurally valid song asking for a different program remains
     * playable through the documented global VH fallback, but the
     * preload compatibility report must flag the different timbre.
     */
    uint8_t mismatch[sizeof music_selected];
    memcpy(mismatch,music_selected,sizeof mismatch);
    mismatch[17]=9; /* original program-change payload was #7 */
    file("selected","music.seq",mismatch,sizeof mismatch);
    assert(vh_game_music_banks_load(&pack,root)==VH_AUDIO_ASSET_OK);
    assert(pack->selected_audit.note_events==1u);
    assert(pack->selected_audit.resolved_notes==1u);
    assert(pack->selected_fallback_notes==1u);
    assert(pack->field_fallback_notes==0u);
    vh_game_music_banks_close(&pack);
    file("selected","music.seq",music_selected,sizeof music_selected);
    cleanup_scene("field");
    cleanup_scene("selected");
    assert(snprintf(path,sizeof path,"%s/field",root)>0);
    assert(rmdir(path)==0);
    assert(snprintf(path,sizeof path,"%s/selected",root)>0);
    assert(rmdir(path)==0);
    assert(rmdir(root)==0);
    puts("two preloaded scene banks, atomic fallback, cross-bank PCM switch: PASS");
    return 0;
}
