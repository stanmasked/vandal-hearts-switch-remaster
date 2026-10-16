/* Export generated native C SEQ->SPU->48k resampler signal to diagnostic PCM WAV.
 * No copyrighted audio, Switch hardware or external fixture.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_native_seq.h"
#include "vh_audio_resample.h"

#define BLOCKS 128u
static VhNativeSeq seq;
static VhNativeSpu spu;
static VhAudioResample resampler;
static int16_t pcm[112], source[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
static const uint8_t song[] = {
    'p','Q','E','S',0,0,0,0,0x01,0xe0,0x07,0xa1,0x20,0,0,
    0,0xc0,7,0,0xb0,10,64,
    0,0x90,60,100,0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f,
};
static int lookup(void *ctx,unsigned program,unsigned note,unsigned velocity,
                  unsigned volume,unsigned pan,VhSeqTone *tone) {
    (void)ctx;
    if(program!=7 || note!=60 || !velocity || volume>127 || pan>127) return -1;
    memset(tone,0,sizeof *tone);
    tone->pcm=pcm; tone->frames=112; tone->loop_end=112;
    tone->pitch_step=4096; tone->adsr1=15;
    tone->gain_left=0.72f; tone->gain_right=0.4f;
    tone->reverb_send=1;
    return 0;
}
static int put16(FILE *f,uint16_t x) {
    return fputc(x&255,f)!=EOF && fputc(x>>8,f)!=EOF;
}
static int put32(FILE *f,uint32_t x) {
    return put16(f,(uint16_t)x) && put16(f,(uint16_t)(x>>16));
}
int main(int argc,char **argv) {
    if(argc!=2) { fprintf(stderr,"usage: %s NEW_OUTPUT.wav\n",argv[0]); return 2; }
    for(unsigned i=0;i<112;i++) pcm[i]=(int16_t)((int)(i*431)%24000-12000);
    vh_native_spu_reset(&spu);
    vh_audio_resample_reset(&resampler);
    if(vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN)!=0 ||
       vh_native_spu_set_reverb(&spu,1,0.5f)!=0 ||
       vh_native_seq_init(&seq,song,sizeof song,&spu,lookup,NULL,0)!=0) return 3;
    FILE *f=fopen(argv[1],"wbx");
    if(!f) { perror("open exclusive WAV"); return 4; }
    int ok = fwrite("RIFF",1,4,f)==4 && put32(f,0) &&
             fwrite("WAVEfmt ",1,8,f)==8 &&
             put32(f,16) && put16(f,1) && put16(f,2) &&
             put32(f,48000) && put32(f,48000*4) &&
             put16(f,4) && put16(f,16) &&
             fwrite("data",1,4,f)==4 && put32(f,0);
    uint32_t frames=0;
    for(unsigned b=0;b<BLOCKS && ok;b++) {
        if(vh_native_seq_advance_block(&seq)<0) {ok=0;break;}
        vh_native_spu_render(&spu,source,VH_AUDIO_BLOCK_FRAMES);
        size_t n=vh_audio_resample_process(&resampler,source,
                 VH_AUDIO_BLOCK_FRAMES,output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        if(n<555 || n>559 || frames+n > UINT32_MAX/4u-36u) {ok=0;break;}
        for(size_t i=0;i<n*2 && ok;i++) ok=put16(f,(uint16_t)output[i]);
        frames+=(uint32_t)n;
    }
    if(ok && fseek(f,4,SEEK_SET)==0) ok=put32(f,36+frames*4u);
    else ok=0;
    if(ok && fseek(f,40,SEEK_SET)==0) ok=put32(f,frames*4u);
    else ok=0;
    if(fclose(f)!=0) ok=0;
    if(!ok) { remove(argv[1]); return 5; }
    printf("native PCM WAV: %u frames, 48000 Hz, stereo, %u blocks\n",frames,BLOCKS);
    return 0;
}
