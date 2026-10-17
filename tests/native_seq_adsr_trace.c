/* Copyright-free native SEQ block and SPU ADSR/loop cursor trace.
 * The separate Python test computes expected state via its own
 * block scheduler and ADSR/sample-position state machines.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vh_native_seq.h"

static VhNativeSeq seq;
static VhNativeSpu spu;
static int16_t sample[128u];
static int16_t buffer[128u*2u];
static uint8_t song[4096u];

static int resolve(void *ctx,unsigned program,unsigned note,
                   unsigned velocity,unsigned volume,unsigned pan,
                   VhSeqTone *out) {
    (void)ctx;(void)volume;(void)pan;
    /* Scheduler fixtures use program 0 implicitly; others set 7. */
    if((program!=0u && program!=7u) || note!=60u || !velocity) return -1;
    memset(out,0,sizeof(*out));
    out->pcm=sample;
    out->frames=128u;
    out->loop_start=16;
    out->loop_end=96;
    out->pitch_step=3072u;
    out->adsr1=0x000fu;
    out->adsr2=0x0020u;
    out->gain_left=1.0f;
    out->gain_right=1.0f;
    return 0;
}
static void test_seq(const char *filename,unsigned repeats,unsigned blocks) {
    FILE *input=fopen(filename,"rb");
    assert(input);
    const size_t bytes=fread(song,1u,sizeof(song),input);
    assert(!ferror(input) && bytes>0u && bytes<sizeof song);
    assert(fgetc(input)==EOF && !ferror(input));
    assert(fclose(input)==0);
    vh_native_spu_reset(&spu);
    assert(vh_native_seq_init(&seq,song,bytes,&spu,
                              resolve,NULL,repeats)==0);
    assert(blocks>0u && blocks<=1722u);
    for(unsigned block=0u;block<blocks;block++) {
        assert(vh_native_seq_advance_block(&seq)>=0);
        printf("S,%u,%llu,%llu,%u,%u,%u,%llu\n",
               block,(unsigned long long)seq.note_ons,
               (unsigned long long)seq.note_offs,seq.tempo,
               seq.cycles_completed,(unsigned)seq.playing,
               (unsigned long long)seq.dispatched_events);
        vh_native_spu_render(&spu,buffer,128u);
        vh_native_spu_render(&spu,buffer,128u);
        vh_native_spu_render(&spu,buffer,128u);
        vh_native_spu_render(&spu,buffer,128u);
    }
}
typedef struct {
    const char *name;
    uint16_t adsr1,adsr2;
    uint32_t pitch_step;
    int64_t loop_start,loop_end;
    unsigned chunks,off_chunk;
} VoiceCase;
static void test_voices(void) {
    const VoiceCase cases[]={
        {"release",0x000fu,0x0020u,0x0800u,8,48,36u,3u},
        {"slow",0x7e0fu,0x0000u,0x4000u,0,56,8u,4u},
        {"one_shot",0x000fu,0x0000u,0x1800u,-1,-1,8u,8u},
        {"fade",0x000fu,0x4000u,0x1000u,0,56,8u,8u},
    };
    for(size_t i=0u;i<sizeof cases/sizeof cases[0];i++) {
        const VoiceCase *v=&cases[i];
        vh_native_spu_reset(&spu);
        assert(vh_native_spu_note_on(
            &spu,0u,sample,56u,v->loop_start,v->loop_end,
            v->pitch_step,v->adsr1,v->adsr2,1.0f,1.0f)==0);
        for(unsigned chunk=0u;chunk<v->chunks;chunk++) {
            if(chunk==v->off_chunk) vh_native_spu_note_off(&spu,0u);
            vh_native_spu_render(&spu,buffer,128u);
            const VhNativeVoice *voice=&spu.voice[0];
            printf("V,%s,%u,%u,%u,%d,%d,%llu,%d,%d\n",
                   v->name,chunk,(unsigned)voice->adsr.phase,
                   (unsigned)voice->active,voice->adsr.level,
                   voice->adsr.counter,
                   (unsigned long long)voice->phase,
                   voice->looped,(int)(voice->phase>>12));
        }
    }
}
int main(int argc,char **argv) {
    for(unsigned i=0u;i<128u;i++)
        sample[i]=(int16_t)((int)i*193-11900);
    if(argc==2 && strcmp(argv[1],"voice")==0) {
        test_voices();
        return 0;
    }
    if((argc==4 || argc==5) && strcmp(argv[1],"seq")==0) {
        char *end=NULL;
        const unsigned long repeats=strtoul(argv[3],&end,10);
        assert(end && !*end && repeats<=64u);
        unsigned blocks=12u;
        if(argc==5) {
            char *last=NULL;
            const unsigned long requested=strtoul(argv[4],&last,10);
            assert(last && !*last && requested>=1u && requested<=1722u);
            blocks=(unsigned)requested;
        }
        test_seq(argv[2],(unsigned)repeats,blocks);
        return 0;
    }
    fprintf(stderr,"usage: native_seq_adsr_trace voice | seq <file> <repeats> [blocks]\n");
    return 2;
}
