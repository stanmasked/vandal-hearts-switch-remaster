/* v65: synthetic-only instrumented producer of GPU event JSONL.
 * This is a smoke-test of the observation hook ABI, NOT a working PS1
 * emulator and NOT a physical retail capture. It reads a synthetic RAM
 * slice, walks its DMA2 linked list and passes ordered words to the same
 * C hook API an instrumented emulator would use at its actual GPU port.
 */
#include "map02_v65_gpu_probe.h"
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_RAM (4u*1024u*1024u)
#define MAX_NODES 4096u
#define MAX_GP0_WORDS 65536u

static uint32_t le32(const unsigned char *p) {
    return ((uint32_t)p[0])|((uint32_t)p[1]<<8)|
           ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static int parse_u32(const char *s,uint32_t *out) {
    char *end=NULL;
    errno=0;
    unsigned long v=strtoul(s,&end,0);
    if (errno || !s[0] || !end || *end || v>0xfffffffful) return -1;
    *out=(uint32_t)v;
    return 0;
}

static int extract(const unsigned char *ram,size_t size,uint32_t base,
                   uint32_t head,uint32_t *words,size_t *length) {
    uint32_t seen[MAX_NODES];
    size_t nodes=0;
    size_t count=0;
    uint32_t address=head;
    while (1) {
        if (nodes==MAX_NODES || address<base || ((address-base)&3u)) return -1;
        for(size_t i=0;i<nodes;i++)if(seen[i]==address)return -1;
        seen[nodes++]=address;
        size_t offset=(size_t)(address-base);
        if (offset>size || size-offset<4) return -1;
        uint32_t tag=le32(ram+offset);
        size_t n=(size_t)(tag>>24);
        uint32_t next=tag&0xffffffu;
        if (n>(size-offset-4)/4 || count+n>MAX_GP0_WORDS) return -1;
        for(size_t j=0;j<n;j++) words[count++]=le32(ram+offset+4+4*j);
        if(next==0xffffffu) break;
        address=next;
    }
    if(!count)return -1;
    *length=count;
    return 0;
}

int main(int argc,char **argv) {
    if(argc!=8) {
        fprintf(stderr,"usage: synthetic_probe_driver RAM_FILE OUTPUT_JSONL BASE HEAD0 HEAD1 HEAD2 HEAD3\n");
        return 2;
    }
    uint32_t base=0;
    uint32_t heads[4]={0};
    if(parse_u32(argv[3],&base))return 2;
    for(size_t i=0;i<4;i++)if(parse_u32(argv[4+(int)i],&heads[i]))return 2;
    FILE *in=fopen(argv[1],"rb");
    if(!in)return 2;
    if(fseek(in,0,SEEK_END)!=0) {fclose(in);return 2;}
    long length=ftell(in);
    if(length<=0 || length>(long)MAX_RAM || length%4) {fclose(in);return 2;}
    rewind(in);
    unsigned char *ram=(unsigned char*)malloc((size_t)length);
    uint32_t *words=(uint32_t*)malloc(sizeof(uint32_t)*MAX_GP0_WORDS);
    if(!ram || !words) {
        free(ram);free(words);fclose(in);return 2;
    }
    if(fread(ram,1,(size_t)length,in)!=(size_t)length) {
        free(ram);free(words);fclose(in);return 2;
    }
    fclose(in);
    FILE *out=fopen(argv[2],"wb");
    if(!out) {free(ram);free(words);return 2;}
    int error=vh65_probe_begin(out,"synthetic");
    uint64_t tick=100;
    for(size_t frame=0;frame<4 && !error;frame++) {
        if(frame==2 || frame==3) {
            uint32_t gp1=(frame==2) ? 0x00000000u : 0x01000000u;
            error=vh65_probe_gp1_write(out,tick++,(unsigned int)frame,gp1);
        }
        size_t count=0;
        if(extract(ram,(size_t)length,base,heads[frame],words,&count)) {
            error=-1;break;
        }
        error=vh65_probe_dma2_submit(out,tick++,(unsigned int)frame,
                                     heads[frame],words,count);
    }
    if(fclose(out)!=0) error=-1;
    free(ram);
    free(words);
    return error ? 1 : 0;
}
